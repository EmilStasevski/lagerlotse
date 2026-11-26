"""Generator determinism and the read-only database role."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from lagerlotse.data.generator import generate


def test_generator_is_deterministic() -> None:
    first, second = generate(7), generate(7)
    assert first.tables() == second.tables()
    assert generate(8).order_lines != first.order_lines


def test_generator_has_slow_movers_and_reorder_candidates() -> None:
    ds = generate(42)
    sold_recently = {line["product_id"] for line in ds.order_lines[-2000:]}
    assert any(p["id"] not in sold_recently for p in ds.products)
    assert any(po["status"] == "open" for po in ds.purchase_orders)


def test_reader_role_cannot_write(reader_url: str) -> None:
    engine = create_engine(reader_url)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM products")).scalar_one() == 4
        assert conn.execute(text("SHOW statement_timeout")).scalar_one() == "5s"
        with pytest.raises(DBAPIError, match="read-only"):
            conn.execute(text("UPDATE products SET list_price = 1"))
    engine.dispose()
