"""Run the evaluation set in tests/eval/questions.yaml against the agent.

    task eval                          # all questions -> results/eval.json
    task eval -- --ids a01,m03         # subset -> results/eval-partial.json
    task eval -- --category adversarial --max-cost 0.5

Expected figures are computed by SQL from the YAML file, independently of the tool code.
Costs real money (ANTHROPIC_API_KEY); the run stops once --max-cost USD is reached.
"""

import argparse
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from sqlalchemy import Connection, create_engine, text

from lagerlotse.agent.agent import Agent, AgentAnswer, Usage
from lagerlotse.agent.verifier import contains_figure
from lagerlotse.config import Settings, get_settings
from lagerlotse.data.queries import get_as_of

QUESTIONS_FILE = Path("tests/eval/questions.yaml")
RESULTS_DIR = Path("results")

Category = Literal["answerable", "multi_step", "out_of_scope", "adversarial"]

# Order lines of all orders that are not cancelled; prepended to every expected-figure query.
SALES_CTE = """sales AS (
    SELECT o.id AS order_id, o.order_date, o.customer_id, l.product_id, l.quantity,
           l.quantity * l.unit_price AS revenue, l.quantity * l.unit_cost AS cost,
           l.quantity * (l.unit_price - l.unit_cost) AS margin
    FROM orders o JOIN order_lines l ON l.order_id = o.id
    WHERE o.status <> 'cancelled')"""


class Figure(BaseModel):
    label: str
    sql: str


class Question(BaseModel):
    id: str
    category: Category
    question: str
    expected_tools: list[str] = Field(default_factory=list)
    expected_text: list[str] = Field(default_factory=list)
    expected_figures: list[Figure] = Field(default_factory=list)


class QuestionResult(BaseModel):
    id: str
    category: Category
    question: str
    passed: bool
    failures: list[str]
    answer: str
    status: str
    tools_called: list[str]
    verification_status: str
    unverified_numbers: list[str]
    expected_figures: dict[str, Decimal]
    usage: Usage
    cost_usd: float
    seconds: float


class CategorySummary(BaseModel):
    passed: int
    total: int


class EvalSummary(BaseModel):
    passed: int
    total: int
    pass_rate_pct: float
    by_category: dict[str, CategorySummary]
    answers_with_numbers: int
    answers_verified: int
    tool_selection_correct: int
    cost_usd: float
    avg_cost_usd: float
    avg_seconds: float


class EvalRun(BaseModel):
    model: str
    effort: str
    started_at: datetime
    dataset_as_of: str
    complete: bool
    summary: EvalSummary
    results: list[QuestionResult]


def load_questions(path: Path = QUESTIONS_FILE) -> list[Question]:
    return [Question.model_validate(q) for q in yaml.safe_load(path.read_text(encoding="utf-8"))]


def expected_value(conn: Connection, sql: str) -> Decimal:
    query = sql.strip()
    if query[:4].upper() == "WITH":
        query = f"WITH {SALES_CTE}, {query[4:].lstrip()}"
    else:
        query = f"WITH {SALES_CTE} {query}"
    value = conn.execute(text(query)).scalar_one()
    if value is None:
        raise ValueError(f"Expected-figure query returned NULL: {sql}")
    return Decimal(value)


def tools_ok(question: Question, called: list[str]) -> bool:
    if question.category == "out_of_scope":
        return not called
    return set(question.expected_tools) <= set(called)


def score(question: Question, answer: AgentAnswer, expected: dict[str, Decimal]) -> list[str]:
    """Return the reasons a question failed; empty means passed."""
    called = [c.name for c in answer.tool_calls]
    failures = []
    if answer.status not in ("answered", "refused"):
        failures.append(f"Status {answer.status}")
    if not tools_ok(question, called):
        wanted = ", ".join(question.expected_tools) or "keine"
        failures.append(f"Tools: erwartet {wanted}, aufgerufen {', '.join(called) or 'keine'}")
    for label, value in expected.items():
        if not contains_figure(answer.answer, value):
            failures.append(f"Zahl fehlt: {label} = {value}")
    for snippet in question.expected_text:
        if snippet.lower() not in answer.answer.lower():
            failures.append(f"Text fehlt: {snippet}")
    if answer.verification.status == "unverified":
        missing = ", ".join(m.text for m in answer.verification.mismatches)
        failures.append(f"Ungeprüfte Zahlen: {missing}")
    return failures


def summarize(results: list[QuestionResult], questions: dict[str, Question]) -> EvalSummary:
    by_category: dict[str, CategorySummary] = {}
    for r in results:
        entry = by_category.setdefault(r.category, CategorySummary(passed=0, total=0))
        entry.total += 1
        entry.passed += r.passed
    with_numbers = [r for r in results if r.verification_status != "no_numbers"]
    total = len(results) or 1
    cost = sum(r.cost_usd for r in results)
    return EvalSummary(
        passed=sum(r.passed for r in results),
        total=len(results),
        pass_rate_pct=round(100 * sum(r.passed for r in results) / total, 1),
        by_category=by_category,
        answers_with_numbers=len(with_numbers),
        answers_verified=sum(r.verification_status == "verified" for r in with_numbers),
        tool_selection_correct=sum(tools_ok(questions[r.id], r.tools_called) for r in results),
        cost_usd=round(cost, 4),
        avg_cost_usd=round(cost / total, 4),
        avg_seconds=round(sum(r.seconds for r in results) / total, 1),
    )


def run(questions: list[Question], settings: Settings, max_cost: float) -> EvalRun:
    engine = create_engine(settings.reader_database_url)
    agent = Agent(engine, settings=settings)
    with engine.connect() as conn:
        as_of = get_as_of(conn).isoformat()
        expected = {
            q.id: {f.label: expected_value(conn, f.sql) for f in q.expected_figures}
            for q in questions
        }
    started = datetime.now(UTC)
    results: list[QuestionResult] = []
    spent = 0.0
    for q in questions:
        if spent >= max_cost:
            print(f"Kostengrenze ${max_cost:.2f} erreicht, Abbruch.")
            break
        t0 = time.monotonic()
        answer = agent.ask(q.question)
        seconds = time.monotonic() - t0
        cost = answer.usage.cost_usd(settings)
        spent += cost
        failures = score(q, answer, expected[q.id])
        results.append(QuestionResult(
            id=q.id, category=q.category, question=q.question, passed=not failures,
            failures=failures, answer=answer.answer, status=answer.status,
            tools_called=[c.name for c in answer.tool_calls],
            verification_status=answer.verification.status,
            unverified_numbers=[m.text for m in answer.verification.mismatches],
            expected_figures=expected[q.id], usage=answer.usage, cost_usd=round(cost, 5),
            seconds=round(seconds, 1),
        ))  # fmt: skip
        mark = "OK  " if not failures else "FAIL"
        print(f"{mark} {q.id:<4} ${cost:.4f} {seconds:5.1f}s  {'; '.join(failures)}")
    return EvalRun(
        model=settings.model,
        effort=settings.effort,
        started_at=started,
        dataset_as_of=as_of,
        complete=len(results) == len(questions),
        summary=summarize(results, {q.id: q for q in questions}),
        results=results,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluation des Assistenten")
    parser.add_argument("--ids", help="Kommagetrennte Fragen-IDs, z. B. a01,m03")
    parser.add_argument("--category", help="Nur diese Kategorie")
    parser.add_argument("--max-cost", type=float, default=3.0, help="Abbruch ab so vielen USD")
    args = parser.parse_args()

    questions = load_questions()
    subset = bool(args.ids or args.category)
    if args.ids:
        wanted = set(args.ids.split(","))
        questions = [q for q in questions if q.id in wanted]
    if args.category:
        questions = [q for q in questions if q.category == args.category]

    result = run(questions, get_settings(), args.max_cost)
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / ("eval-partial.json" if subset or not result.complete else "eval.json")
    out.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    s = result.summary
    print(f"\n{s.passed}/{s.total} bestanden ({s.pass_rate_pct} %), Modell {result.model}")
    for category, c in s.by_category.items():
        print(f"  {category:<13} {c.passed}/{c.total}")
    print(f"Antworten mit Zahlen geprüft: {s.answers_verified}/{s.answers_with_numbers}")
    print(f"Kosten ${s.cost_usd:.4f} (Ø ${s.avg_cost_usd:.4f}), Ø {s.avg_seconds} s je Frage")
    print(f"Ergebnis: {out}")


if __name__ == "__main__":
    main()
