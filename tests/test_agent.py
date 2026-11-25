"""Agent loop with a scripted fake client: no API calls, no cost."""

from types import SimpleNamespace as NS
from typing import Any

import pytest
from sqlalchemy import Engine

from lagerlotse.agent.agent import Agent, Turn
from lagerlotse.config import Settings


def usage(inp: int = 100, out: int = 20) -> NS:
    return NS(input_tokens=inp, output_tokens=out, cache_read_input_tokens=0,
              cache_creation_input_tokens=0)  # fmt: skip


def tool_use(name: str, inp: dict[str, Any], id_: str = "tu_1") -> NS:
    return NS(type="tool_use", name=name, input=inp, id=id_)


def text(t: str) -> NS:
    return NS(type="text", text=t)


class FakeClient:
    def __init__(self, responses: list[NS]) -> None:
        self.responses = responses
        self.requests: list[dict[str, Any]] = []
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kwargs: Any) -> NS:
        self.requests.append(kwargs)
        return self.responses.pop(0)


SETTINGS = Settings(model="test-model", price_input_per_mtok=2.0, price_output_per_mtok=10.0)


def make_agent(engine: Engine, responses: list[NS], **overrides: Any) -> tuple[Agent, FakeClient]:
    client = FakeClient(responses)
    settings = SETTINGS.model_copy(update=overrides)
    return Agent(engine, client=client, settings=settings), client


def test_tool_round_trip_and_verified_answer(engine: Engine) -> None:
    agent, client = make_agent(engine, [
        NS(stop_reason="tool_use", usage=usage(),
           content=[tool_use("top_customers",
                             {"start_date": "2026-01-01", "end_date": "2026-06-30", "limit": 1})]),
        NS(stop_reason="end_turn", usage=usage(),
           content=[text("Im 1. Halbjahr 2026 lag Testkunde 1 GmbH mit 730,00 € vorn "
                         "(62,5 % von 1.168,00 €).")]),
    ])  # fmt: skip
    result = agent.ask("Wer war im ersten Halbjahr 2026 der beste Kunde?")

    assert result.status == "answered"
    assert [c.name for c in result.tool_calls] == ["top_customers"]
    assert result.verification.status == "verified", result.verification.mismatches
    assert result.usage.requests == 2
    assert result.usage.cost_usd(SETTINGS) == pytest.approx((200 * 2 + 40 * 10) / 1e6)

    first, second = client.requests
    assert "Stichtag der Daten ist 30.06.2026 (Dienstag)" in first["system"]
    assert first["model"] == "test-model" and first["fallbacks"] == "default"
    assert {t["name"] for t in first["tools"]} >= {"top_customers", "reorder_suggestions"}
    tool_result = second["messages"][-1]["content"][0]
    assert tool_result["tool_use_id"] == "tu_1" and "1168.00" in tool_result["content"]


def test_invented_number_is_flagged(engine: Engine) -> None:
    agent, _ = make_agent(engine, [
        NS(stop_reason="end_turn", usage=usage(),
           content=[text("Der Umsatz lag bei etwa 2.000 €.")]),
    ])  # fmt: skip
    result = agent.ask("Wie hoch war der Umsatz?")
    assert result.verification.status == "unverified"


def test_tool_errors_are_returned_to_the_model(engine: Engine) -> None:
    agent, client = make_agent(engine, [
        NS(stop_reason="tool_use", usage=usage(),
           content=[tool_use("reorder_suggestions", {"category": "Schrauben"})]),
        NS(stop_reason="end_turn", usage=usage(), content=[text("Die Kategorie gibt es nicht.")]),
    ])  # fmt: skip
    result = agent.ask("Nachbestellen für Schrauben?")
    tool_result = client.requests[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True
    assert "Unbekannte Kategorie" in tool_result["content"]
    assert result.verification.status == "no_numbers"


def test_round_limit_stops_the_loop(engine: Engine) -> None:
    looping = [
        NS(stop_reason="tool_use", usage=usage(), content=[tool_use("slow_movers", {}, f"t{i}")])
        for i in range(3)
    ]
    agent, client = make_agent(engine, looping, max_tool_rounds=2)
    result = agent.ask("Ladenhüter?")
    assert result.status == "incomplete"
    assert len(client.requests) == 3


def test_refusal_and_settings_without_fallback(engine: Engine) -> None:
    agent, client = make_agent(
        engine,
        [NS(stop_reason="refusal", usage=usage(), content=[])],
        refusal_fallback=False,
    )
    result = agent.ask("...")
    assert result.status == "refused" and result.answer
    assert "fallbacks" not in client.requests[0]


def test_follow_up_uses_history_for_context_and_verification(engine: Engine) -> None:
    first_call = make_agent(engine, [
        NS(stop_reason="tool_use", usage=usage(),
           content=[tool_use("slow_movers", {})]),
        NS(stop_reason="end_turn", usage=usage(), content=[text("BF-1 hat 250,00 € Lagerwert.")]),
    ])[0].ask("Ladenhüter?")  # fmt: skip
    history = [Turn(question=first_call.question, answer=first_call.answer,
                    tool_calls=first_call.tool_calls)]  # fmt: skip

    agent, client = make_agent(engine, [
        NS(stop_reason="end_turn", usage=usage(),
           content=[text("Wie gesagt: 250,00 € seit dem 01.06.2025 ohne Verkauf.")]),
    ])  # fmt: skip
    result = agent.ask("Und seit wann?", history)
    assert [m["role"] for m in client.requests[0]["messages"]] == ["user", "assistant", "user"]
    assert result.verification.status == "verified", result.verification.mismatches


def test_missing_model_is_a_clear_error(engine: Engine) -> None:
    with pytest.raises(RuntimeError, match="LAGERLOTSE_MODEL"):
        Agent(engine, client=FakeClient([]), settings=SETTINGS.model_copy(update={"model": ""}))
