"""Tool tests against the fixture dataset. Expected values are computed by hand, see
tests/fixture_data.py."""

from datetime import date
from decimal import Decimal as D

import pytest
from sqlalchemy import Connection

from lagerlotse.data import queries as q

H1 = {"start_date": date(2026, 1, 1), "end_date": date(2026, 6, 30)}


def test_top_customers(conn: Connection) -> None:
    result = q.top_customers(conn, q.TopCustomersInput(**H1, limit=2))
    # C1: 400+150+180 = 730, C2: 150+252 = 402, C3: 36 (open order counts, cancelled not)
    assert result.total_revenue_eur == D("1168.00")
    assert result.customers_with_orders == 3
    assert [(c.customer_no, c.revenue_eur, c.order_count) for c in result.customers] == [
        ("K-1", D("730.00"), 2),
        ("K-2", D("402.00"), 2),
    ]
    assert [c.share_of_total_pct for c in result.customers] == [D("62.5"), D("34.4")]


def test_top_customers_empty_period(conn: Connection) -> None:
    result = q.top_customers(
        conn, q.TopCustomersInput(start_date=date(2020, 1, 1), end_date=date(2020, 12, 31))
    )
    assert result.total_revenue_eur == D("0.00")
    assert result.customers == []


def test_date_range_must_be_ordered() -> None:
    with pytest.raises(ValueError):
        q.TopCustomersInput(start_date=date(2026, 2, 1), end_date=date(2026, 1, 1))


def test_revenue_by_quarter(conn: Connection) -> None:
    result = q.revenue_by_period(conn, q.RevenueByPeriodInput(**H1, granularity="quarter"))
    assert [
        (p.period_label, p.revenue_eur, p.gross_margin_eur, p.margin_pct, p.order_count)
        for p in result.periods
    ] == [
        ("2026-Q1", D("700.00"), D("300.00"), D("42.9"), 2),
        ("2026-Q2", D("468.00"), D("180.00"), D("38.5"), 3),
    ]
    assert result.total_revenue_eur == D("1168.00")
    assert result.total_gross_margin_eur == D("480.00")
    assert result.total_margin_pct == D("41.1")


def test_revenue_by_month_includes_empty_months(conn: Connection) -> None:
    result = q.revenue_by_period(conn, q.RevenueByPeriodInput(**H1, category="Kabelschutz"))
    revenue = {p.period_label: p.revenue_eur for p in result.periods}
    assert len(revenue) == 6
    assert revenue["2026-01"] == D("150.00")
    assert revenue["2026-05"] == D("0.00")  # only the cancelled order
    assert revenue["2026-06"] == D("252.00")


def test_unknown_category_lists_valid_values(conn: Connection) -> None:
    with pytest.raises(q.ToolError, match="Kabelbinder"):
        q.revenue_by_period(conn, q.RevenueByPeriodInput(**H1, category="Schrauben"))


def test_product_margin_sorting(conn: Connection) -> None:
    result = q.product_margin(conn, q.ProductMarginInput(**H1))
    # P1: 154 units, 616 revenue, 308 cost; P2: 28 units, 402 / 280; P3: 5 units, 150 / 100
    assert [
        (p.sku, p.units_sold, p.revenue_eur, p.margin_eur, p.margin_pct) for p in result.products
    ] == [
        ("KB-1", 154, D("616.00"), D("308.00"), D("50.0")),
        ("KS-1", 28, D("402.00"), D("122.00"), D("30.3")),
        ("WZ-1", 5, D("150.00"), D("50.00"), D("33.3")),
    ]
    lowest = q.product_margin(
        conn, q.ProductMarginInput(**H1, sort_by="margin_pct", order="lowest", limit=1)
    )
    assert lowest.products_with_sales == 3
    assert [p.sku for p in lowest.products] == ["KS-1"]


def test_stock_coverage(conn: Connection) -> None:
    result = q.stock_coverage(conn, q.StockCoverageInput())
    assert result.as_of == date(2026, 6, 30)
    assert result.demand_window == q.Period(start=date(2026, 4, 2), end=date(2026, 6, 30))
    rows = {r.sku: r for r in result.products}
    # P1: demand 45+9 = 54 / 90 = 0.6 per day, available 20-9 = 11, coverage 18.3 days
    assert rows["KB-1"].available_units == 11
    assert rows["KB-1"].avg_daily_demand_units == D("0.60")
    assert rows["KB-1"].coverage_days == D("18.3")
    # P2: demand 18 / 90 = 0.2 per day (cancelled order ignored), coverage 40 / 0.2 = 200
    assert rows["KS-1"].coverage_days == D("200.0")
    assert rows["WZ-1"].coverage_days is None
    assert [r.sku for r in result.products][:2] == ["KB-1", "KS-1"]


def test_stock_coverage_threshold(conn: Connection) -> None:
    result = q.stock_coverage(conn, q.StockCoverageInput(max_coverage_days=30))
    assert [r.sku for r in result.products] == ["KB-1"]


def test_slow_movers(conn: Connection) -> None:
    result = q.slow_movers(conn, q.SlowMoversInput())
    # P4: last sale 2025-06-01, 394 days before 2026-06-30, 50 x 5.00 = 250.00
    assert [
        (r.sku, r.last_sale_date, r.days_since_last_sale, r.stock_value_eur)
        for r in result.products
    ] == [("BF-1", date(2025, 6, 1), 394, D("250.00"))]
    assert result.total_stock_value_eur == D("250.00")
    # P3: last sale 2026-02-10 = 140 days ago, 3 x 20.00 = 60.00
    wider = q.slow_movers(conn, q.SlowMoversInput(min_days_without_sale=120))
    assert wider.product_count == 2
    assert wider.total_stock_value_eur == D("310.00")


def test_open_purchase_orders(conn: Connection) -> None:
    result = q.open_purchase_orders(conn, q.OpenPurchaseOrdersInput())
    assert [(r.po_no, r.days_overdue, r.total_value_eur) for r in result.purchase_orders] == [
        ("BE-4", 20, D("200.00")),
        ("BE-5", 0, D("100.00")),
    ]
    assert result.total_value_eur == D("300.00")
    assert result.overdue_count == 1
    overdue = q.open_purchase_orders(conn, q.OpenPurchaseOrdersInput(only_overdue=True))
    assert [r.po_no for r in overdue.purchase_orders] == ["BE-4"]
    by_sku = q.open_purchase_orders(conn, q.OpenPurchaseOrdersInput(sku="KS-1"))
    assert [r.po_no for r in by_sku.purchase_orders] == ["BE-5"]


def test_unknown_supplier(conn: Connection) -> None:
    with pytest.raises(q.ToolError, match="L-101"):
        q.open_purchase_orders(conn, q.OpenPurchaseOrdersInput(supplier_no="L-999"))


def test_late_deliveries(conn: Connection) -> None:
    result = q.late_deliveries(conn, q.LateDeliveriesInput(**H1))
    rows = {r.supplier_no: r for r in result.suppliers}
    # L-101: BE-1 late by 5, BE-2 on time. L-102: BE-3 late by 12, BE-4 open and overdue.
    assert (
        rows["L-101"].deliveries_received,
        rows["L-101"].late_deliveries,
        rows["L-101"].late_share_pct,
        rows["L-101"].avg_delay_days_when_late,
    ) == (2, 1, D("50.0"), D("5.0"))
    assert (
        rows["L-102"].deliveries_received,
        rows["L-102"].late_share_pct,
        rows["L-102"].max_delay_days,
        rows["L-102"].open_overdue_orders,
    ) == (1, D("100.0"), 12, 1)
    assert [r.supplier_no for r in result.suppliers] == ["L-102", "L-101"]
    assert (result.deliveries_received, result.late_deliveries, result.late_share_pct) == (
        3,
        2,
        D("66.7"),
    )


def test_reorder_suggestions(conn: Connection) -> None:
    result = q.reorder_suggestions(conn, q.ReorderSuggestionsInput())
    # P1: 0.6/day, lead 10 + safety 14 -> reorder point ceil(14.4) = 15; position 11 < 15.
    #     target ceil(0.6 x 54) = 33, need 22, rounded up to MOQ 10 -> 30, cost 60.00.
    # P2: reorder point ceil(4.8) = 5, position 40 + 10 open = 50 -> no suggestion.
    assert [
        (r.sku, r.reorder_point_units, r.suggested_qty_units, r.est_cost_eur)
        for r in result.suggestions
    ] == [("KB-1", 15, 30, D("60.00"))]
    assert result.total_est_cost_eur == D("60.00")


def test_reorder_suggestions_supplier_filter(conn: Connection) -> None:
    result = q.reorder_suggestions(conn, q.ReorderSuggestionsInput(supplier_no="L-102"))
    assert result.suggestions == []
