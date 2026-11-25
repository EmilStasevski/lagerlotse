"""Agent loop: Claude picks tools from the allowlist, we run them read-only, the verifier checks
every number in the final answer.

A manual loop instead of the SDK's beta tool runner, because every tool call is recorded for
the verifier and runs on its own read-only connection (see docs/DECISIONS.md 009).

Privacy: only tool names, outcome and token counts are logged, never questions, prompts,
tool results or answers.
"""

import json
import logging
from typing import Any, Literal, Protocol

import anthropic
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from lagerlotse.agent.prompts import system_prompt
from lagerlotse.agent.tools import ToolCall, run_tool, tool_specs
from lagerlotse.agent.verifier import Verification, verify_answer
from lagerlotse.config import Settings, get_settings
from lagerlotse.data.queries import get_as_of

log = logging.getLogger(__name__)

MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"

Status = Literal["answered", "refused", "incomplete", "error"]


class Usage(BaseModel):
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def add(self, usage: Any) -> None:
        self.requests += 1
        self.input_tokens += usage.input_tokens or 0
        self.output_tokens += usage.output_tokens or 0
        self.cache_read_input_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_creation_input_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0

    def cost_usd(self, settings: Settings) -> float:
        """Estimate from configured prices: cache writes 1.25x, cache reads 0.1x input price."""
        weighted_input = (
            self.input_tokens
            + 1.25 * self.cache_creation_input_tokens
            + 0.1 * self.cache_read_input_tokens
        )
        return (
            weighted_input * settings.price_input_per_mtok
            + self.output_tokens * settings.price_output_per_mtok
        ) / 1_000_000


class Turn(BaseModel):
    """A finished question/answer pair, used as context for follow-up questions."""

    question: str
    answer: str
    tool_calls: list[ToolCall] = Field(default_factory=list)


class AgentAnswer(BaseModel):
    question: str
    answer: str
    status: Status
    tool_calls: list[ToolCall]
    verification: Verification
    usage: Usage
    model: str


class MessagesClient(Protocol):
    """The part of the Anthropic client we use; lets tests pass a scripted fake."""

    @property
    def beta(self) -> Any: ...


class Agent:
    def __init__(
        self,
        engine: Engine,
        client: MessagesClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if not self.settings.model:
            raise RuntimeError("LAGERLOTSE_MODEL ist nicht gesetzt (siehe .env.example).")
        self.engine = engine
        self.client: MessagesClient = client or anthropic.Anthropic(
            api_key=self.settings.anthropic_api_key.get_secret_value() or None
        )
        with engine.connect() as conn:
            self.as_of = get_as_of(conn)
        self.system = system_prompt(self.as_of)
        self.tools = tool_specs()

    def _create(self, messages: list[dict[str, Any]]) -> Any:
        extra: dict[str, Any] = {}
        if self.settings.refusal_fallback:
            extra = {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        return self.client.beta.messages.create(
            model=self.settings.model,
            max_tokens=MAX_TOKENS,
            system=self.system,
            tools=self.tools,
            messages=messages,
            output_config={"effort": self.settings.effort},
            cache_control={"type": "ephemeral"},
            **extra,
        )

    def _run_tools(self, response: Any) -> tuple[list[ToolCall], list[dict[str, Any]]]:
        calls: list[ToolCall] = []
        results: list[dict[str, Any]] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            raw_input = block.input if isinstance(block.input, dict) else {}
            with self.engine.connect() as conn:
                call = run_tool(conn, block.name, raw_input)
            log.info("tool %s: %s", call.name, "error" if call.error else "ok")
            calls.append(call)
            if call.error is not None:
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": call.error,
                        "is_error": True,
                    }  # fmt: skip
                )
            else:
                content = json.dumps(call.output, ensure_ascii=False)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})
        return calls, results

    def ask(self, question: str, history: list[Turn] | None = None) -> AgentAnswer:
        history = history or []
        messages: list[dict[str, Any]] = []
        for turn in history:
            messages.append({"role": "user", "content": turn.question})
            messages.append({"role": "assistant", "content": turn.answer})
        messages.append({"role": "user", "content": question})

        usage = Usage()
        calls: list[ToolCall] = []
        status: Status = "incomplete"
        answer = ""
        try:
            for _ in range(self.settings.max_tool_rounds + 1):
                response = self._create(messages)
                usage.add(response.usage)
                if response.stop_reason in ("tool_use", "pause_turn"):
                    messages.append({"role": "assistant", "content": response.content})
                    if response.stop_reason == "tool_use":
                        new_calls, results = self._run_tools(response)
                        calls.extend(new_calls)
                        messages.append({"role": "user", "content": results})
                    continue
                answer = "\n\n".join(b.text for b in response.content if b.type == "text").strip()
                if response.stop_reason == "end_turn":
                    status = "answered"
                elif response.stop_reason == "refusal":
                    status = "refused"
                    answer = answer or "Diese Anfrage kann ich nicht beantworten."
                break
            else:
                answer = "Ich konnte die Frage nicht in wenigen Schritten beantworten."
        except anthropic.APIError as exc:
            log.warning("API error: %s", type(exc).__name__)
            status = "error"
            answer = "Der Assistent ist gerade nicht erreichbar. Bitte später erneut versuchen."
        log.info(
            "question done: status=%s tools=%d requests=%d in=%d out=%d cache_read=%d",
            status, len(calls), usage.requests, usage.input_tokens, usage.output_tokens,
            usage.cache_read_input_tokens,
        )  # fmt: skip

        context_calls = [c for turn in history for c in turn.tool_calls] + calls
        context_questions = " ".join([t.question for t in history] + [question])
        return AgentAnswer(
            question=question,
            answer=answer,
            status=status,
            tool_calls=calls,
            verification=verify_answer(answer, context_calls, context_questions, self.as_of),
            usage=usage,
            model=self.settings.model,
        )
