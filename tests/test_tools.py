"""Tool registry: specs for the API and safe execution of model-provided input."""

from sqlalchemy import Connection

from lagerlotse.agent.tools import TOOLS, run_tool, tool_specs

PLANNED = {
    "top_customers", "revenue_by_period", "product_margin", "stock_coverage", "slow_movers",
    "open_purchase_orders", "late_deliveries", "reorder_suggestions",
}  # fmt: skip


def test_all_planned_tools_are_registered_with_german_descriptions() -> None:
    assert set(TOOLS) == PLANNED
    for spec in tool_specs():
        assert spec["description"], spec["name"]
        assert spec["input_schema"]["type"] == "object"


def test_run_tool_returns_json_ready_output(conn: Connection) -> None:
    call = run_tool(conn, "top_customers", {"start_date": "2026-01-01", "end_date": "2026-06-30"})
    assert call.error is None and call.output is not None
    assert call.output["total_revenue_eur"] == "1168.00"


def test_run_tool_reports_invalid_input(conn: Connection) -> None:
    call = run_tool(conn, "top_customers", {"start_date": "gestern", "end_date": "2026-06-30"})
    assert call.output is None
    assert call.error is not None and "start_date" in call.error


def test_run_tool_reports_unknown_values_and_tools(conn: Connection) -> None:
    call = run_tool(conn, "reorder_suggestions", {"category": "Schrauben"})
    assert call.error is not None and "Unbekannte Kategorie" in call.error
    assert run_tool(conn, "drop_tables", {}).error == "Unbekanntes Tool 'drop_tables'."
