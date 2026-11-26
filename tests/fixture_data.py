"""Tiny, hand-checkable dataset for tool tests. Expected values in the tests are computed by
hand from these rows (see comments), not by running the code under test.

Reference date: 2026-06-30. Demand window (90 days): 2026-04-02 to 2026-06-30.

Orders (revenue / gross margin):
  O1 C1 2026-01-15 shipped   P1 100 x 4.00 (cost 2)  = 400 / 200; P2 10 x 15.00 (cost 10) = 150 / 50
  O2 C2 2026-02-10 shipped   P3   5 x 30.00 (cost 20) = 150 / 50
  O3 C1 2026-04-20 shipped   P1  45 x 4.00            = 180 / 90
  O4 C3 2026-05-05 cancelled P2 100 x 15.00           (excluded everywhere)
  O5 C2 2026-06-10 shipped   P2  18 x 14.00           = 252 / 72
  O6 C3 2026-06-29 open      P1   9 x 4.00            =  36 / 18   (reserves 9 x P1)
  O7 C3 2025-06-01 shipped   P4  10 x 8.00 (cost 5)   =  80 / 30   (P4's last sale)
"""

from datetime import date
from decimal import Decimal as D

from lagerlotse.data.generator import Dataset

AS_OF = date(2026, 6, 30)


def fixture_dataset() -> Dataset:
    ds = Dataset()
    ds.meta = [{"key": "as_of", "value": AS_OF.isoformat()}]
    ds.suppliers = [
        {
            "id": 1,
            "supplier_no": "L-101",
            "name": "Testlieferant Nord GmbH",
            "country": "DE",
            "lead_time_days": 10,
        },
        {
            "id": 2,
            "supplier_no": "L-102",
            "name": "Testlieferant Fern Ltd.",
            "country": "TW",
            "lead_time_days": 40,
        },
    ]
    product = {"unit": "Stück", "active": True}
    ds.products = [
        {
            "id": 1,
            "sku": "KB-1",
            "name": "Kabelbinder A",
            "category": "Kabelbinder",
            "supplier_id": 1,
            "purchase_price": D("2.00"),
            "list_price": D("4.00"),
            "min_order_qty": 10,
            **product,
        },
        {
            "id": 2,
            "sku": "KS-1",
            "name": "Wellrohr B",
            "category": "Kabelschutz",
            "supplier_id": 1,
            "purchase_price": D("10.00"),
            "list_price": D("15.00"),
            "min_order_qty": 5,
            **product,
        },
        {
            "id": 3,
            "sku": "WZ-1",
            "name": "Zange C",
            "category": "Werkzeug",
            "supplier_id": 2,
            "purchase_price": D("20.00"),
            "list_price": D("30.00"),
            "min_order_qty": 5,
            **product,
        },
        {
            "id": 4,
            "sku": "BF-1",
            "name": "Sockel D",
            "category": "Befestigung",
            "supplier_id": 2,
            "purchase_price": D("5.00"),
            "list_price": D("8.00"),
            "min_order_qty": 10,
            **product,
        },
    ]
    ds.customers = [
        {
            "id": i,
            "customer_no": f"K-{i}",
            "name": f"Testkunde {i} GmbH",
            "segment": "Elektroinstallation",
            "city": "Bielefeld",
            "created_on": date(2024, 1, 1),
        }
        for i in (1, 2, 3)
    ]
    orders = [
        (1, 1, date(2026, 1, 15), "shipped"),
        (2, 2, date(2026, 2, 10), "shipped"),
        (3, 1, date(2026, 4, 20), "shipped"),
        (4, 3, date(2026, 5, 5), "cancelled"),
        (5, 2, date(2026, 6, 10), "shipped"),
        (6, 3, date(2026, 6, 29), "open"),
        (7, 3, date(2025, 6, 1), "shipped"),
    ]
    ds.orders = [
        {
            "id": oid,
            "order_no": f"AU-{oid}",
            "customer_id": cid,
            "order_date": d,
            "promised_date": d,
            "shipped_date": d if status == "shipped" else None,
            "status": status,
        }
        for oid, cid, d, status in orders
    ]
    lines = [
        (1, 1, 100, "4.00", "2.00"),
        (1, 2, 10, "15.00", "10.00"),
        (2, 3, 5, "30.00", "20.00"),
        (3, 1, 45, "4.00", "2.00"),
        (4, 2, 100, "15.00", "10.00"),
        (5, 2, 18, "14.00", "10.00"),
        (6, 1, 9, "4.00", "2.00"),
        (7, 4, 10, "8.00", "5.00"),
    ]
    ds.order_lines = [
        {
            "id": i,
            "order_id": o,
            "product_id": p,
            "quantity": q,
            "unit_price": D(price),
            "unit_cost": D(cost),
        }
        for i, (o, p, q, price, cost) in enumerate(lines, start=1)
    ]
    ds.stock = [
        {"product_id": 1, "on_hand": 20, "reserved": 9},
        {"product_id": 2, "on_hand": 40, "reserved": 0},
        {"product_id": 3, "on_hand": 3, "reserved": 0},
        {"product_id": 4, "on_hand": 50, "reserved": 0},
    ]
    pos = [
        (1, 1, date(2026, 1, 5), date(2026, 1, 15), date(2026, 1, 20)),  # 5 days late
        (2, 1, date(2026, 3, 1), date(2026, 3, 11), date(2026, 3, 10)),  # on time
        (3, 2, date(2026, 2, 1), date(2026, 3, 13), date(2026, 3, 25)),  # 12 days late
        (4, 2, date(2026, 5, 1), date(2026, 6, 10), None),  # open, 20 days overdue
        (5, 1, date(2026, 6, 25), date(2026, 7, 5), None),  # open, not yet due
    ]
    ds.purchase_orders = [
        {
            "id": i,
            "po_no": f"BE-{i}",
            "supplier_id": s,
            "order_date": od,
            "expected_date": ed,
            "received_date": rd,
            "status": "received" if rd else "open",
        }
        for i, s, od, ed, rd in pos
    ]
    po_lines = [
        (1, 1, 100, "2.00"),
        (2, 2, 20, "10.00"),
        (3, 3, 10, "20.00"),
        (4, 3, 10, "20.00"),
        (5, 2, 10, "10.00"),
    ]
    ds.purchase_order_lines = [
        {"id": i, "po_id": po, "product_id": p, "quantity": q, "unit_cost": D(c)}
        for i, (po, p, q, c) in enumerate(po_lines, start=1)
    ]
    return ds
