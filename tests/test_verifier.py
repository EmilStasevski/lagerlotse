"""Verifier tests: German number formats, rounding, units, dates and invented figures."""

from typing import Any

from lagerlotse.agent.tools import ToolCall
from lagerlotse.agent.verifier import verify_answer

TOP = ToolCall(
    name="top_customers",
    input={"start_date": "2026-07-01", "end_date": "2026-09-30", "limit": 3},
    output={
        "period": {"start": "2026-07-01", "end": "2026-09-30"},
        "total_revenue_eur": "1735597.34",
        "customers_with_orders": 152,
        "customers": [
            {"rank": 1, "customer_no": "K-10042", "name": "Wendrich Schaltschrankbau AG",
             "revenue_eur": "70501.02", "order_count": 61, "share_of_total_pct": "4.1"},
            {"rank": 2, "customer_no": "K-10007", "name": "Gaustedt Handelsgesellschaft KG",
             "revenue_eur": "59308.73", "order_count": 48, "share_of_total_pct": "3.4"},
        ],
    },
)  # fmt: skip
STOCK = ToolCall(
    name="stock_coverage",
    input={"sku": "KB-10003"},
    output={
        "as_of": "2026-11-20",
        "products": [
            {"sku": "KB-10003", "name": "Kabelbinder Standard 4,8 x 300 mm, schwarz",
             "available_units": 11, "avg_daily_demand_units": "0.60", "coverage_days": "18.3"}
        ],
    },
)  # fmt: skip


def check(answer: str, calls: list[ToolCall] | None = None, question: str = "") -> Any:
    return verify_answer(answer, calls if calls is not None else [TOP], question)


def test_exact_german_numbers_are_verified() -> None:
    result = check(
        "Im 3. Quartal 2026 (01.07.2026 bis 30.09.2026) lag Wendrich Schaltschrankbau AG "
        "mit 70.501,02 € vorn, das sind 4,1 % von insgesamt 1.735.597,34 €."
    )
    assert result.status == "verified", result.mismatches
    sources = {c.text: c.source for c in result.checks}
    assert sources["70.501,02 €"] == "top_customers.output.customers[0].revenue_eur"


def test_rounded_values_match_at_shown_precision() -> None:
    result = check("Gesamtumsatz rund 1,7 Mio. €, Spitzenkunde 70.501 € bzw. 70,5 Tsd. €.")
    assert result.status == "verified", result.mismatches


def test_invented_number_is_flagged() -> None:
    result = check("Wendrich Schaltschrankbau AG hatte 72.000 € Umsatz.")
    assert result.status == "unverified"
    assert [c.text for c in result.mismatches] == ["72.000 €"]


def test_wrong_rounding_is_flagged() -> None:
    # 1.735.597,34 rounded to one decimal in millions is 1,7, not 1,8.
    assert check("Umsatz: 1,8 Mio. €").status == "unverified"


def test_unit_mismatch_is_flagged() -> None:
    # 61 is an order count, not a percentage.
    result = check("Der Anteil liegt bei 61 %.")
    assert result.status == "unverified"


def test_identifiers_and_list_markers_are_not_figures() -> None:
    result = check("1. Wendrich Schaltschrankbau AG (K-10042)\n2. Gaustedt (K-10007)")
    assert result.status == "no_numbers"


def test_numbers_from_question_and_names_are_allowed() -> None:
    result = check(
        "Für Kabelbinder Standard 4,8 x 300 mm reicht der Bestand von 11 Einheiten "
        "noch 18 Tage (Tagesbedarf 0,6).",
        [STOCK],
        question="Wie lange reicht KB-10003?",
    )
    assert result.status == "verified", result.mismatches


def test_unknown_date_is_flagged() -> None:
    result = check("Stand: 15.10.2026.", [STOCK])
    assert result.status == "unverified"
    assert check("Stand: 20. November 2026.", [STOCK]).status == "verified"


def test_list_count_is_allowed() -> None:
    assert check("Es wurden 2 Kunden ausgegeben.").status == "verified"


def test_no_tool_calls_means_numbers_are_unverified() -> None:
    assert check("Der Umsatz lag bei 500 €.", []).status == "unverified"


def test_contains_figure() -> None:
    from decimal import Decimal

    from lagerlotse.agent.verifier import contains_figure

    answer = "Umsatz 2025: 7.172.638,55 € (rund 7,2 Mio. €), Marge 40,8 %."
    assert contains_figure(answer, Decimal("7172638.55"))
    assert contains_figure(answer, Decimal("40.8"))
    assert not contains_figure(answer, Decimal("7300000"))
    assert not contains_figure("Stand 20.11.2026", Decimal("20"))


def test_table_rank_column_is_layout() -> None:
    table = "| Rang | Kunde | Umsatz |\n|---|---|---|\n| 1 | Wendrich | 70.501,02 € |\n"
    assert check(table).status == "verified"
    assert check("| Wendrich | 7 |").status == "unverified"  # not the first column


def test_reference_date_and_nearby_years_are_known() -> None:
    from datetime import date

    answer = "Stand 20.11.2026: Für 2027 habe ich keine Daten."
    assert verify_answer(answer, [], as_of=date(2026, 11, 20)).status == "verified"
    assert verify_answer(answer, []).status == "unverified"
    assert verify_answer("Im Jahr 2040", [], as_of=date(2026, 11, 20)).status == "unverified"
