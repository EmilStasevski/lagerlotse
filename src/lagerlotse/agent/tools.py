"""Allowlist of tools the agent may call. Each tool is a typed query function; its German
docstring is the description the model sees, its pydantic input model is the JSON schema."""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import Connection

from lagerlotse.data import queries as q


@dataclass(frozen=True)
class Tool:
    name: str
    input_model: type[BaseModel]
    func: Callable[[Connection, Any], BaseModel]

    @property
    def description(self) -> str:
        return inspect.cleandoc(self.func.__doc__ or "")

    def spec(self) -> dict[str, Any]:
        """Tool definition in the format of the Anthropic Messages API."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
        }


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool("top_customers", q.TopCustomersInput, q.top_customers),
        Tool("revenue_by_period", q.RevenueByPeriodInput, q.revenue_by_period),
        Tool("product_margin", q.ProductMarginInput, q.product_margin),
        Tool("stock_coverage", q.StockCoverageInput, q.stock_coverage),
        Tool("slow_movers", q.SlowMoversInput, q.slow_movers),
        Tool("open_purchase_orders", q.OpenPurchaseOrdersInput, q.open_purchase_orders),
        Tool("late_deliveries", q.LateDeliveriesInput, q.late_deliveries),
        Tool("reorder_suggestions", q.ReorderSuggestionsInput, q.reorder_suggestions),
    ]
}


class ToolCall(BaseModel):
    """One executed tool call: what was asked and what came back (JSON-ready)."""

    name: str
    input: dict[str, Any]
    output: dict[str, Any] | None = None
    error: str | None = None


def tool_specs() -> list[dict[str, Any]]:
    return [tool.spec() for tool in TOOLS.values()]


def run_tool(conn: Connection, name: str, raw_input: dict[str, Any]) -> ToolCall:
    """Validate the input and run the tool. Errors the model can fix are returned, not raised."""
    tool = TOOLS.get(name)
    if tool is None:
        return ToolCall(name=name, input=raw_input, error=f"Unbekanntes Tool '{name}'.")
    try:
        params = tool.input_model.model_validate(raw_input)
    except ValidationError as exc:
        details = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        return ToolCall(name=name, input=raw_input, error=f"Ungültige Eingabe: {details}")
    try:
        result = tool.func(conn, params)
    except q.ToolError as exc:
        return ToolCall(name=name, input=raw_input, error=str(exc))
    return ToolCall(name=name, input=raw_input, output=result.model_dump(mode="json"))
