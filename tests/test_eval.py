"""Evaluation set structure and scoring, without API calls."""

from collections import Counter
from decimal import Decimal

from lagerlotse.agent.agent import AgentAnswer, Usage
from lagerlotse.agent.eval import Question, load_questions, score
from lagerlotse.agent.tools import TOOLS, ToolCall
from lagerlotse.agent.verifier import verify_answer


def test_question_set_is_well_formed() -> None:
    questions = load_questions()
    assert len(questions) >= 40
    assert len({q.id for q in questions}) == len(questions)
    assert set(Counter(q.category for q in questions)) == {
        "answerable", "multi_step", "out_of_scope", "adversarial",
    }  # fmt: skip
    for q in questions:
        assert set(q.expected_tools) <= set(TOOLS), q.id
        if q.category == "out_of_scope":
            assert not q.expected_tools and not q.expected_figures, q.id


def answer(text: str, tools: list[ToolCall], status: str = "answered") -> AgentAnswer:
    return AgentAnswer(
        question="", answer=text, status=status,  # type: ignore[arg-type]
        tool_calls=tools, verification=verify_answer(text, tools), usage=Usage(), model="m",
    )  # fmt: skip


CALL = ToolCall(name="slow_movers", input={}, output={"total_stock_value_eur": "22337.04"})
Q = Question(id="t", category="answerable", question="?", expected_tools=["slow_movers"])


def test_score_passes_with_figure_tools_and_verification() -> None:
    assert score(Q, answer("Lagerwert 22.337,04 €.", [CALL]), {"Wert": Decimal("22337.04")}) == []


def test_score_lists_each_failure() -> None:
    failures = score(Q, answer("Lagerwert 30.000 €.", []), {"Wert": Decimal("22337.04")})
    assert len(failures) == 3  # wrong tools, figure missing, unverified number


def test_out_of_scope_must_not_call_tools() -> None:
    q = Question(id="o", category="out_of_scope", question="Wetter?")
    assert score(q, answer("Dazu habe ich keine Daten.", []), {}) == []
    assert score(q, answer("Dazu habe ich keine Daten.", [CALL]), {})
