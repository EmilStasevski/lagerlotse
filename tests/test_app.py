"""Web app with a fake agent: pages, chat fragment, verification display, login, escaping."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from lagerlotse.agent.agent import AgentAnswer, Turn, Usage
from lagerlotse.agent.tools import ToolCall
from lagerlotse.agent.verifier import verify_answer
from lagerlotse.api.app import create_app
from lagerlotse.config import Settings

CALL = ToolCall(name="slow_movers", input={"limit": 5}, output={"total_stock_value_eur": "250.00"})


class FakeAgent:
    def __init__(self, answer: str = "Ladenhüter binden 250,00 € Lagerwert.") -> None:
        self.answer = answer
        self.histories: list[list[Turn]] = []

    def ask(self, question: str, history: list[Turn] | None = None) -> AgentAnswer:
        self.histories.append(list(history or []))
        return AgentAnswer(
            question=question, answer=self.answer, status="answered", tool_calls=[CALL],
            verification=verify_answer(self.answer, [CALL]), usage=Usage(), model="fake",
        )  # fmt: skip


@pytest.fixture
def make_client(engine: Engine) -> Callable[..., tuple[TestClient, FakeAgent]]:
    def make(answer: str | None = None, key: str = "") -> tuple[TestClient, FakeAgent]:
        agent = FakeAgent(answer) if answer else FakeAgent()
        settings = Settings(model="fake", app_key=SecretStr(key))
        return TestClient(create_app(settings, engine=engine, agent=agent)), agent

    return make


def test_chat_page_and_verified_answer(
    make_client: Callable[..., tuple[TestClient, FakeAgent]],
) -> None:
    client, agent = make_client()
    page = client.get("/")
    assert page.status_code == 200
    assert "Datenstand 30.06.2026" in page.text
    assert "lagerlotse_session" in page.cookies

    fragment = client.post("/frage", data={"frage": "Ladenhüter?"})
    assert fragment.status_code == 200
    assert "250,00 €" in fragment.text
    assert "Alle 1 Zahlen sind durch Abfrage-Ergebnisse belegt" in fragment.text
    assert "slow_movers" in fragment.text

    client.post("/frage", data={"frage": "Und welche genau?"})
    assert [t.question for t in agent.histories[1]] == ["Ladenhüter?"]
    assert "Ladenhüter?" in client.get("/").text  # earlier turns survive a reload


def test_unverified_number_is_marked(
    make_client: Callable[..., tuple[TestClient, FakeAgent]],
) -> None:
    client, _ = make_client("Es sind etwa 900,00 € gebunden.")
    fragment = client.post("/frage", data={"frage": "Wie viel?"}).text
    assert "<mark" in fragment and "900,00 €</mark>" in fragment
    assert "Ungeprüft: 1 von 1 Zahlen ohne Beleg" in fragment


def test_model_html_is_escaped(make_client: Callable[..., tuple[TestClient, FakeAgent]]) -> None:
    client, _ = make_client("<script>alert(1)</script> | a |\n|---|\n| b |")
    fragment = client.post("/frage", data={"frage": "x"}).text
    assert "<script>alert" not in fragment
    assert "&lt;script&gt;" in fragment


def test_question_length_is_limited(
    make_client: Callable[..., tuple[TestClient, FakeAgent]],
) -> None:
    client, _ = make_client()
    assert client.post("/frage", data={"frage": "x" * 501}).status_code == 422


def test_new_conversation_clears_history(
    make_client: Callable[..., tuple[TestClient, FakeAgent]],
) -> None:
    client, agent = make_client()
    client.get("/")
    client.post("/frage", data={"frage": "Erste Frage"})
    client.post("/neu")
    client.post("/frage", data={"frage": "Zweite Frage"})
    assert agent.histories[-1] == []


def test_login_with_shared_key(make_client: Callable[..., tuple[TestClient, FakeAgent]]) -> None:
    client, _ = make_client(key="geheim")
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/anmelden"
    htmx = client.post("/frage", data={"frage": "x"}, headers={"HX-Request": "true"})
    assert htmx.status_code == 401 and htmx.headers["hx-redirect"] == "/anmelden"

    assert client.post("/anmelden", data={"key": "falsch"}).status_code == 401
    assert (
        client.post("/anmelden", data={"key": "geheim"}, follow_redirects=False).status_code == 303
    )
    assert client.get("/").status_code == 200
    assert "geheim" not in client.cookies.get("lagerlotse_auth", "")

    other, _ = make_client(key="geheim")
    assert other.get("/bericht", headers={"X-API-Key": "geheim"}).status_code == 200


def test_report_pages_and_health(make_client: Callable[..., tuple[TestClient, FakeAgent]]) -> None:
    client, _ = make_client()
    report = client.get("/bericht")
    assert report.status_code == 200 and "Nachbestellvorschlag, Stichtag 30.06.2026" in report.text
    assert "zurück zum Assistenten" in report.text
    markdown = client.get("/bericht.md")
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "| KB-1 |" in markdown.text
    assert client.get("/healthz").text == "ok"
