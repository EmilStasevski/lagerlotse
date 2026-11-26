"""Web app: one chat page and one report page. Server-rendered HTML with htmx, no JS build.

Run with `task up` (Docker) or `task app` (local, with reload).

Access: if LAGERLOTSE_APP_KEY is set, every page needs a login with that shared key
(cookie) or an `X-API-Key` header. Conversations live in memory only, per browser session,
and are never written to disk or logs.
"""

import hashlib
import hmac
import logging
import secrets
import threading
from collections import OrderedDict
from datetime import date
from typing import Annotated, Protocol

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt
from markupsafe import Markup, escape
from sqlalchemy import Engine, create_engine, text

from lagerlotse import formatting
from lagerlotse.agent.agent import Agent, AgentAnswer, Turn
from lagerlotse.agent.prompts import CAPABILITIES
from lagerlotse.config import Settings, get_settings
from lagerlotse.data.queries import get_as_of
from lagerlotse.report import build_report, render

log = logging.getLogger(__name__)

SESSION_COOKIE = "lagerlotse_session"
AUTH_COOKIE = "lagerlotse_auth"
MAX_QUESTION_CHARS = 500
MAX_TURNS = 6
MAX_SESSIONS = 500

EXAMPLE_QUESTIONS = [
    "Welche fünf Kunden hatten im letzten Quartal den höchsten Umsatz?",
    "Was sollten wir diese Woche nachbestellen?",
    "Welche Ladenhüter binden das meiste Kapital?",
    "Wie pünktlich haben unsere Lieferanten dieses Jahr geliefert?",
    "Wie wird das Wetter morgen?",
]

_markdown = MarkdownIt("commonmark", {"html": False}).enable("table")


class AgentLike(Protocol):
    def ask(self, question: str, history: list[Turn] | None = None) -> AgentAnswer: ...


class ConversationStore:
    """In-memory conversations per browser session; oldest sessions are dropped first."""

    def __init__(self, max_sessions: int = MAX_SESSIONS, max_turns: int = MAX_TURNS) -> None:
        self._data: OrderedDict[str, list[AgentAnswer]] = OrderedDict()
        self._lock = threading.Lock()
        self.max_sessions = max_sessions
        self.max_turns = max_turns

    def get(self, session_id: str) -> list[AgentAnswer]:
        with self._lock:
            return list(self._data.get(session_id, []))

    def history(self, session_id: str) -> list[Turn]:
        """Earlier turns as context for a follow-up question."""
        return [
            Turn(question=a.question, answer=a.answer, tool_calls=a.tool_calls)
            for a in self.get(session_id)
        ]

    def append(self, session_id: str, turn: AgentAnswer) -> None:
        with self._lock:
            turns = self._data.pop(session_id, [])
            turns = [*turns, turn][-self.max_turns :]
            self._data[session_id] = turns
            while len(self._data) > self.max_sessions:
                self._data.popitem(last=False)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._data.pop(session_id, None)


def render_answer(result: AgentAnswer) -> Markup:
    """Markdown to HTML (raw HTML disabled) with unverified numbers highlighted."""
    html = _markdown.render(result.answer)
    for miss in result.verification.mismatches:
        needle = str(escape(miss.text))
        if needle in html:
            title = "Diese Zahl stammt aus keinem Tool-Ergebnis"
            html = html.replace(needle, f'<mark title="{title}">{needle}</mark>', 1)
    return Markup(html)  # noqa: S704 - produced by markdown-it with html=False


def _auth_token(key: str) -> str:
    return hmac.new(key.encode(), b"lagerlotse-auth", hashlib.sha256).hexdigest()


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    agent: AgentLike | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or create_engine(settings.reader_database_url, pool_pre_ping=True)
    app_key = settings.app_key.get_secret_value()
    if not app_key:
        log.warning("LAGERLOTSE_APP_KEY ist leer: Web-App ohne Anmeldung (nur lokal verwenden).")
    store = ConversationStore()
    templates = Jinja2Templates(directory=str(_templates_dir()))
    templates.env.filters["datum"] = formatting.datum
    templates.env.globals["render_answer"] = render_answer
    app = FastAPI(title="Lagerlotse", docs_url=None, redoc_url=None, openapi_url=None)
    agent_holder: dict[str, AgentLike] = {}

    def get_agent() -> AgentLike:
        if agent is not None:
            return agent
        if "agent" not in agent_holder:
            agent_holder["agent"] = Agent(engine, settings=settings)
        return agent_holder["agent"]

    def require_auth(request: Request) -> None:
        if not app_key:
            return
        header = request.headers.get("x-api-key", "")
        cookie = request.cookies.get(AUTH_COOKIE, "")
        if secrets.compare_digest(header, app_key) or secrets.compare_digest(
            cookie, _auth_token(app_key)
        ):
            return
        if request.headers.get("hx-request"):
            raise HTTPException(status_code=401, headers={"HX-Redirect": "/anmelden"})
        raise HTTPException(status_code=303, headers={"Location": "/anmelden"})

    Auth = Annotated[None, Depends(require_auth)]

    def session_id(request: Request) -> tuple[str, bool]:
        """Return the browser's session id and whether it is new (cookie must be set)."""
        sid = request.cookies.get(SESSION_COOKIE)
        return (sid, False) if sid else (secrets.token_urlsafe(16), True)

    def with_session(request: Request, response: Response, sid: str, new: bool) -> Response:
        if new:
            response.set_cookie(
                SESSION_COOKIE, sid, httponly=True, samesite="strict",
                secure=request.url.scheme == "https",
            )  # fmt: skip
        return response

    def as_of() -> date:
        with engine.connect() as conn:
            return get_as_of(conn)

    @app.get("/healthz", response_class=PlainTextResponse)
    def healthz() -> str:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"

    @app.get("/anmelden", response_class=HTMLResponse)
    def login_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "login.html", {"error": False})

    @app.post("/anmelden", response_class=HTMLResponse)
    def login(request: Request, key: Annotated[str, Form()]) -> Response:
        if app_key and secrets.compare_digest(key, app_key):
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(
                AUTH_COOKIE, _auth_token(app_key), httponly=True, samesite="strict",
                max_age=60 * 60 * 12, secure=request.url.scheme == "https",
            )  # fmt: skip
            return response
        return templates.TemplateResponse(request, "login.html", {"error": True}, status_code=401)

    @app.get("/", response_class=HTMLResponse)
    def chat_page(request: Request, _: Auth) -> Response:
        sid, new = session_id(request)
        page = templates.TemplateResponse(
            request,
            "chat.html",
            {
                "turns": store.get(sid),
                "examples": EXAMPLE_QUESTIONS,
                "capabilities": CAPABILITIES,
                "as_of": as_of(),
            },
        )
        return with_session(request, page, sid, new)

    @app.post("/frage", response_class=HTMLResponse)
    def ask(
        request: Request,
        frage: Annotated[str, Form(max_length=MAX_QUESTION_CHARS)],
        _: Auth,
    ) -> Response:
        sid, new = session_id(request)
        question = frage.strip()
        if not question:
            return HTMLResponse("")
        result = get_agent().ask(question, store.history(sid))
        store.append(sid, result)
        fragment = templates.TemplateResponse(
            request, "_turn.html", {"q": question, "r": result, "html": render_answer(result)}
        )
        return with_session(request, fragment, sid, new)

    @app.post("/neu")
    def new_conversation(request: Request, _: Auth) -> RedirectResponse:
        sid = request.cookies.get(SESSION_COOKIE)
        if sid:
            store.clear(sid)
        return RedirectResponse("/", status_code=303)

    @app.get("/bericht", response_class=HTMLResponse)
    def report_page(_: Auth) -> HTMLResponse:
        with engine.connect() as conn:
            report = build_report(conn)
        html = render(report, "html").replace(
            "<body>", '<body><p><a href="/">← zurück zum Assistenten</a></p>', 1
        )
        return HTMLResponse(html)

    @app.get("/bericht.md", response_class=PlainTextResponse)
    def report_markdown(_: Auth) -> PlainTextResponse:
        with engine.connect() as conn:
            report = build_report(conn)
        return PlainTextResponse(render(report, "md"), media_type="text/markdown; charset=utf-8")

    return app


def _templates_dir() -> object:
    from importlib.resources import files

    return files("lagerlotse.api").joinpath("templates")


def app_factory() -> FastAPI:
    """Entry point for uvicorn: `uvicorn --factory lagerlotse.api.app:app_factory`."""
    logging.basicConfig(level=logging.INFO)
    return create_app()
