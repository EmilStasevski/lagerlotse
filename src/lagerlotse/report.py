"""Weekly reorder report (Markdown and HTML), built from the same tools the agent uses.

Run with `task report`. Writes `reports/nachbestellung-<Stichtag>.md` and `.html`.
"""

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, StrictUndefined
from pydantic import BaseModel
from sqlalchemy import Connection, create_engine

from lagerlotse import formatting
from lagerlotse.agent.tools import ToolCall, run_tool
from lagerlotse.config import get_settings
from lagerlotse.data.queries import get_as_of

DELIVERY_LOOKBACK_DAYS = 90


class WeeklyReport(BaseModel):
    as_of: date
    calls: list[ToolCall]

    def output(self, tool: str) -> dict[str, Any]:
        for call in self.calls:
            if call.name == tool:
                if call.output is None:
                    raise RuntimeError(f"{tool} failed: {call.error}")
                return call.output
        raise KeyError(tool)


def build_report(conn: Connection) -> WeeklyReport:
    as_of = get_as_of(conn)
    lookback = (as_of - timedelta(days=DELIVERY_LOOKBACK_DAYS - 1)).isoformat()
    requests: list[tuple[str, dict[str, Any]]] = [
        ("reorder_suggestions", {"limit": 100}),
        ("open_purchase_orders", {"only_overdue": True}),
        ("late_deliveries", {"start_date": lookback, "end_date": as_of.isoformat()}),
        ("slow_movers", {"limit": 10}),
    ]
    return WeeklyReport(as_of=as_of, calls=[run_tool(conn, n, i) for n, i in requests])


def _env() -> Environment:
    env = Environment(
        loader=PackageLoader("lagerlotse", "templates"),
        undefined=StrictUndefined,
        autoescape=lambda name: bool(name and name.endswith(".html.j2")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(
        eur=formatting.eur, pct=formatting.pct, num=formatting.number, datum=formatting.datum
    )
    return env


def render(report: WeeklyReport, fmt: str) -> str:
    template = _env().get_template(f"report.{fmt}.j2")
    return template.render(
        as_of=report.as_of,
        reorder=report.output("reorder_suggestions"),
        overdue=report.output("open_purchase_orders"),
        deliveries=report.output("late_deliveries"),
        slow=report.output("slow_movers"),
    )


def write_report(report: WeeklyReport, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for fmt in ("md", "html"):
        path = out_dir / f"nachbestellung-{report.as_of.isoformat()}.{fmt}"
        path.write_text(render(report, fmt), encoding="utf-8")
        paths.append(path)
    return paths


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("reports")
    engine = create_engine(get_settings().reader_database_url)
    with engine.connect() as conn:
        report = build_report(conn)
    for path in write_report(report, out_dir):
        print(f"geschrieben: {path}")


if __name__ == "__main__":
    main()
