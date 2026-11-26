"""Dashboard SQL runs on the read-only role and agrees with the agent's tools."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import create_engine, text

from lagerlotse.data import queries as q

SPEC: dict[str, Any] = yaml.safe_load(Path("dashboards/metabase.yaml").read_text(encoding="utf-8"))


def scalar(reader_url: str, name: str) -> Decimal:
    card = next(c for c in SPEC["cards"] if c["name"] == name)
    with create_engine(reader_url).connect() as conn:
        return Decimal(conn.execute(text(card["sql"])).scalar_one())


def test_every_card_runs_on_the_reader_role(reader_url: str) -> None:
    engine = create_engine(reader_url)
    with engine.connect() as conn:
        for card in SPEC["cards"]:
            result = conn.execute(text(card["sql"]))
            columns = list(result.keys())
            if card["display"] in ("line", "bar"):
                assert card["dimension"] in columns, card["name"]
                assert set(card["metrics"]) <= set(columns), card["name"]
    engine.dispose()


def test_cards_match_tools(reader_url: str) -> None:
    engine = create_engine(reader_url)
    with engine.connect() as conn:
        ytd = q.revenue_by_period(
            conn, q.RevenueByPeriodInput(start_date=date(2026, 1, 1), end_date=date(2026, 6, 30))
        )
        slow = q.slow_movers(conn, q.SlowMoversInput())
    engine.dispose()
    assert scalar(reader_url, "Umsatz laufendes Jahr (EUR)") == ytd.total_revenue_eur
    assert scalar(reader_url, "Marge laufendes Jahr (%)") == ytd.total_margin_pct
    name = "Lagerwert Ladenhüter, 180 Tage ohne Verkauf (EUR)"
    assert scalar(reader_url, name) == slow.total_stock_value_eur
