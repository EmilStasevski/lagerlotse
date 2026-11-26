"""Deterministic generator for synthetic wholesale data.

Everything here is invented: company names are made-up word stems, products are generic
catalogue items. The same seed always yields the same rows, so `task data` is reproducible.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

# The dataset's "today". Fixed so that the data, the tests and the hash never drift.
DATA_START = date(2025, 1, 2)
AS_OF = date(2026, 11, 20)

Row = dict[str, Any]


@dataclass
class Dataset:
    meta: list[Row] = field(default_factory=list)
    suppliers: list[Row] = field(default_factory=list)
    products: list[Row] = field(default_factory=list)
    customers: list[Row] = field(default_factory=list)
    orders: list[Row] = field(default_factory=list)
    order_lines: list[Row] = field(default_factory=list)
    stock: list[Row] = field(default_factory=list)
    purchase_orders: list[Row] = field(default_factory=list)
    purchase_order_lines: list[Row] = field(default_factory=list)

    def tables(self) -> list[tuple[str, list[Row]]]:
        """Tables in insert order (parents before children)."""
        return [
            ("dataset_meta", self.meta),
            ("suppliers", self.suppliers),
            ("products", self.products),
            ("customers", self.customers),
            ("orders", self.orders),
            ("order_lines", self.order_lines),
            ("stock", self.stock),
            ("purchase_orders", self.purchase_orders),
            ("purchase_order_lines", self.purchase_order_lines),
        ]


# --- word lists (invented names only) -------------------------------------------------

SUPPLIER_NAMES = [
    ("Kabelwerk Ostrand GmbH", "DE"),
    ("Polytec Varnhalt AG", "DE"),
    ("Brennwald Befestigungstechnik GmbH", "DE"),
    ("Alpenfix Handels GmbH", "AT"),
    ("Moravtec s.r.o.", "CZ"),
    ("Wisłoplast Sp. z o.o.", "PL"),
    ("Tecnofasce S.r.l.", "IT"),
    ("Silverbay Industrial Co., Ltd.", "TW"),
    ("Eastgate Fastening Co., Ltd.", "CN"),
    ("Kerlinger Werkzeuge GmbH", "DE"),
]
LEAD_TIME_BY_COUNTRY = {"DE": (5, 12), "AT": (7, 14), "CZ": (8, 16), "PL": (8, 16), "IT": (10, 18)}
LEAD_TIME_OVERSEAS = (35, 50)

CUSTOMER_STEMS = [
    "Alvenhoff",
    "Brekenau",
    "Dorstweg",
    "Ellerkamp",
    "Fennrich",
    "Gaustedt",
    "Hollmerath",
    "Iversand",
    "Jallwitz",
    "Kornbeck",
    "Lindsahl",
    "Marwedel",
    "Norrkamp",
    "Osterhain",
    "Pellwang",
    "Quernau",
    "Rastmeyer",
    "Sellwitz",
    "Tannfeld",
    "Ulmerhof",
    "Varnholt",
    "Wendrich",
    "Zellmar",
    "Bruckstedt",
    "Hagenroth",
    "Kessenich",
    "Morbach-Nord",
    "Riedholm",
]
SEGMENTS = {
    "Elektroinstallation": ["Elektro", "Elektrotechnik", "Gebäudetechnik"],
    "Schaltschrankbau": ["Schaltanlagen", "Steuerungsbau", "Schaltschrankbau"],
    "Maschinenbau": ["Maschinenbau", "Anlagenbau", "Sondermaschinen"],
    "Fahrzeugbau": ["Fahrzeugtechnik", "Karosseriebau", "Nutzfahrzeuge"],
    "Industrie-Instandhaltung": ["Industrieservice", "Instandhaltung", "Werksservice"],
    "Handel": ["Elektrogroßhandel", "Fachhandel", "Handelsgesellschaft"],
}
LEGAL_FORMS = ["GmbH", "GmbH", "GmbH & Co. KG", "KG", "e.K.", "AG"]
CITIES = [
    "Bielefeld",
    "Dortmund",
    "Kassel",
    "Hannover",
    "Paderborn",
    "Münster",
    "Osnabrück",
    "Göttingen",
    "Hamm",
    "Siegen",
    "Erfurt",
    "Leipzig",
    "Würzburg",
    "Mannheim",
    "Ulm",
    "Augsburg",
    "Bremen",
    "Kiel",
    "Magdeburg",
    "Koblenz",
]


@dataclass
class _ProductSpec:
    name: str
    category: str
    unit: str
    cost: float
    moq: int
    max_qty: int  # typical maximum quantity per order line


def _catalogue(rng: random.Random) -> list[_ProductSpec]:
    specs: list[_ProductSpec] = []
    for kind, factor in [("Standard", 1.0), ("UV-beständig", 1.3), ("hitzebeständig", 1.8)]:
        for width, length in [
            (2.5, 100),
            (3.6, 140),
            (3.6, 200),
            (4.8, 200),
            (4.8, 300),
            (7.6, 370),
            (7.6, 450),
            (9.0, 780),
        ]:
            for color in ["natur", "schwarz"]:
                cost = (0.6 + width * length / 450) * factor
                specs.append(
                    _ProductSpec(
                        f"Kabelbinder {kind} {width:.1f} x {length} mm, {color}".replace(".", ","),
                        "Kabelbinder",
                        "Beutel (100 St.)",
                        cost,
                        10,
                        300,
                    )
                )
    for width, length in [(4.6, 200), (4.6, 360), (7.9, 300), (7.9, 680)]:
        specs.append(
            _ProductSpec(
                f"Kabelbinder Edelstahl {width:.1f} x {length} mm".replace(".", ","),
                "Kabelbinder",
                "Beutel (100 St.)",
                4.0 + length / 60,
                5,
                60,
            )
        )
    for nw in [7, 10, 13, 17, 23, 29, 36, 48]:
        for material, factor in [("PA6", 1.6), ("PP", 1.0)]:
            for slit in ["geschlitzt", "ungeschlitzt"]:
                specs.append(
                    _ProductSpec(
                        f"Wellrohr {material} NW {nw}, {slit}, schwarz",
                        "Kabelschutz",
                        "Rolle (50 m)",
                        (8 + nw * 1.1) * factor,
                        5,
                        120,
                    )
                )
    for nw in [10, 16, 25, 40]:
        specs.append(
            _ProductSpec(
                f"Spiralschlauch PE {nw} mm, transparent",
                "Kabelschutz",
                "Rolle (25 m)",
                6 + nw * 0.5,
                5,
                80,
            )
        )
        specs.append(
            _ProductSpec(
                f"Geflechtschlauch PET {nw} mm, schwarz",
                "Kabelschutz",
                "Rolle (50 m)",
                12 + nw * 0.9,
                5,
                60,
            )
        )
    for size in ["M12", "M16", "M20", "M25", "M32", "M40", "M50", "M63"]:
        mm = int(size[1:])
        specs.append(
            _ProductSpec(
                f"Kabelverschraubung Polyamid {size}, grau",
                "Verschraubungen",
                "Packung (10 St.)",
                1.5 + mm * 0.12,
                10,
                200,
            )
        )
        specs.append(
            _ProductSpec(
                f"Kabelverschraubung Messing vernickelt {size}",
                "Verschraubungen",
                "Packung (10 St.)",
                6 + mm * 0.6,
                5,
                80,
            )
        )
    for item, cost in [
        ("Befestigungssockel schraubbar 19 x 19 mm", 2.2),
        ("Klebesockel 28 x 28 mm", 3.1),
        ("Spreizanker für Kabelbinder", 2.8),
        ("Kantenclip 1-3 mm", 3.4),
        ("Rohrschelle für Wellrohr NW 17", 3.9),
        ("Rohrschelle für Wellrohr NW 29", 5.2),
        ("Senkkopfschraube 4 x 25 mm", 1.4),
        ("Nylondübel 6 x 30 mm", 1.1),
        ("Nageldübel 6 x 40 mm", 1.9),
        ("Montageplatte selbstklebend", 4.6),
    ]:
        specs.append(
            _ProductSpec(f"{item}, Packung 100", "Befestigung", "Packung (100 St.)", cost, 10, 200)
        )
    for item, cost in [
        ("Kabelbinderzange automatisch", 38),
        ("Abisolierzange 0,2-6 mm²", 21),
        ("Crimpzange Aderendhülsen", 34),
        ("Seitenschneider 160 mm", 12),
        ("Wellrohrschneider bis NW 48", 17),
        ("Kabelmesser mit Hakenklinge", 9),
        ("Schraubendreher-Set VDE, 7-teilig", 26),
        ("Heißluftgebläse 2000 W", 44),
    ]:
        specs.append(_ProductSpec(item, "Werkzeug", "Stück", cost, 5, 24))
    for item, cost in [
        ("Schrumpfschlauch 2:1 Sortiment", 7.5),
        ("Schrumpfschlauch 3:1 9 mm, 1 m", 1.6),
        ("Kabelmarkierer Clip 0-9, Box", 11),
        ("Beschriftungsband 12 mm, weiß", 8.2),
        ("Isolierband PVC 19 mm, schwarz", 0.7),
    ]:
        specs.append(_ProductSpec(item, "Kennzeichnung", "Stück", cost, 10, 200))
    rng.shuffle(specs)
    return specs


SKU_PREFIX = {
    "Kabelbinder": "KB",
    "Kabelschutz": "KS",
    "Verschraubungen": "VS",
    "Befestigung": "BF",
    "Werkzeug": "WZ",
    "Kennzeichnung": "KZ",
}
SUPPLIER_CATEGORIES = {
    "Kabelbinder": [0, 5, 7, 8],
    "Kabelschutz": [1, 3, 6],
    "Verschraubungen": [1, 4, 6],
    "Befestigung": [2, 3, 8],
    "Werkzeug": [9, 7],
    "Kennzeichnung": [1, 4],
}


def _money(value: float) -> Decimal:
    return Decimal(f"{value:.2f}")


def _workdays(start: date, end: date) -> list[date]:
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def _add_workdays(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _line_quantity(rng: random.Random, max_qty: int) -> int:
    """Long-tailed quantity: mostly small lines, sometimes large project orders."""
    return max(1, min(max_qty, round(rng.paretovariate(1.4) * max_qty / 12)))


def generate(seed: int, as_of: date = AS_OF) -> Dataset:
    rng = random.Random(seed)
    ds = Dataset()
    ds.meta = [
        {"key": "as_of", "value": as_of.isoformat()},
        {"key": "data_start", "value": DATA_START.isoformat()},
        {"key": "seed", "value": str(seed)},
    ]

    # Suppliers: lead time plus a hidden reliability used for delivery delays.
    reliability: dict[int, float] = {}
    for i, (name, country) in enumerate(SUPPLIER_NAMES, start=1):
        low, high = LEAD_TIME_BY_COUNTRY.get(country, LEAD_TIME_OVERSEAS)
        ds.suppliers.append(
            {
                "id": i,
                "supplier_no": f"L-{100 + i}",
                "name": name,
                "country": country,
                "lead_time_days": rng.randint(low, high),
            }
        )
        reliability[i] = rng.choice([0.04, 0.08, 0.12, 0.2, 0.35])

    # Products with a popularity weight and a sales window (slow movers stop selling).
    weight: dict[int, float] = {}
    sales_end: dict[int, date] = {}
    sales_start: dict[int, date] = {}
    max_qty: dict[int, int] = {}
    counters: dict[str, int] = {}
    for pid, spec in enumerate(_catalogue(rng), start=1):
        counters[spec.category] = counters.get(spec.category, 0) + 1
        supplier_idx = rng.choice(SUPPLIER_CATEGORIES[spec.category])
        cost = spec.cost * rng.uniform(0.85, 1.15)
        markup = rng.uniform(1.35, 2.1)
        ds.products.append(
            {
                "id": pid,
                "sku": f"{SKU_PREFIX[spec.category]}-{10000 + counters[spec.category]}",
                "name": spec.name,
                "category": spec.category,
                "unit": spec.unit,
                "supplier_id": supplier_idx + 1,
                "purchase_price": _money(cost),
                "list_price": _money(cost * markup),
                "min_order_qty": spec.moq,
                "active": True,
            }
        )
        weight[pid] = rng.paretovariate(1.3)
        max_qty[pid] = spec.max_qty
        sales_start[pid] = DATA_START
        sales_end[pid] = as_of
        roll = rng.random()
        if roll < 0.09:  # slow mover: demand stopped a while ago
            sales_end[pid] = as_of - timedelta(days=rng.randint(200, 500))
        elif roll < 0.12:  # new product
            sales_start[pid] = as_of - timedelta(days=rng.randint(60, 200))

    # Customers with a size weight and a negotiated discount.
    cust_weight: dict[int, float] = {}
    discount: dict[int, float] = {}
    used_names: set[str] = set()
    for cid in range(1, 161):
        segment = rng.choice(list(SEGMENTS))
        while True:
            name = (
                f"{rng.choice(CUSTOMER_STEMS)} {rng.choice(SEGMENTS[segment])} "
                f"{rng.choice(LEGAL_FORMS)}"
            )
            if name not in used_names:
                used_names.add(name)
                break
        cust_weight[cid] = min(rng.paretovariate(1.5), 12.0)
        discount[cid] = min(0.04 + cust_weight[cid] * 0.012, 0.15) if cust_weight[cid] > 2 else 0.0
        ds.customers.append(
            {
                "id": cid,
                "customer_no": f"K-{10000 + cid}",
                "name": name,
                "segment": segment,
                "city": rng.choice(CITIES),
                "created_on": DATA_START - timedelta(days=rng.randint(30, 2000)),
            }
        )

    product_ids = list(weight)
    customer_ids = list(cust_weight)
    cust_weights = [cust_weight[c] for c in customer_ids]

    # Customer orders on workdays, with mild seasonality and growth.
    total_days = (as_of - DATA_START).days
    line_id = 0
    for day in _workdays(DATA_START, as_of):
        season = 1.0 - 0.35 * (day.month == 8) - 0.3 * (day.month == 12 and day.day > 18)
        growth = 1.0 + 0.15 * (day - DATA_START).days / total_days
        n_orders = max(0, round(rng.gauss(11 * season * growth, 3)))
        live = [p for p in product_ids if sales_start[p] <= day <= sales_end[p]]
        live_weights = [weight[p] for p in live]
        for _ in range(n_orders):
            oid = len(ds.orders) + 1
            cid = rng.choices(customer_ids, cust_weights)[0]
            age = (as_of - day).days
            if age <= 2:
                status, shipped = "open", None
            elif rng.random() < 0.01:
                status, shipped = "cancelled", None
            else:
                status, shipped = "shipped", _add_workdays(day, rng.choice([1, 1, 2, 2, 3, 4]))
            ds.orders.append(
                {
                    "id": oid,
                    "order_no": f"AU-{day.year}-{oid:06d}",
                    "customer_id": cid,
                    "order_date": day,
                    "promised_date": _add_workdays(day, 2),
                    "shipped_date": shipped,
                    "status": status,
                }
            )
            n_lines = min(len(live), rng.choice([1, 1, 2, 2, 3, 3, 4, 5, 6]))
            chosen: set[int] = set()
            while len(chosen) < n_lines:
                chosen.add(rng.choices(live, live_weights)[0])
            for pid in sorted(chosen):
                product = ds.products[pid - 1]
                list_price = float(product["list_price"])
                line_id += 1
                ds.order_lines.append(
                    {
                        "id": line_id,
                        "order_id": oid,
                        "product_id": pid,
                        "quantity": _line_quantity(rng, max_qty[pid]),
                        "unit_price": _money(
                            list_price * (1 - discount[cid]) * rng.uniform(0.97, 1.03)
                        ),
                        "unit_cost": product["purchase_price"],
                    }
                )

    # Stock: derived from recent demand with a spread of coverage, so that some
    # products need reordering and slow movers tie up capital.
    window_start = as_of - timedelta(days=90)
    recent_units: dict[int, int] = dict.fromkeys(product_ids, 0)
    reserved: dict[int, int] = dict.fromkeys(product_ids, 0)
    orders_by_id = {o["id"]: o for o in ds.orders}
    for line in ds.order_lines:
        order = orders_by_id[line["order_id"]]
        if order["status"] == "cancelled":
            continue
        if order["order_date"] > window_start:
            recent_units[line["product_id"]] += line["quantity"]
        if order["status"] == "open":
            reserved[line["product_id"]] += line["quantity"]
    supplier_lead = {s["id"]: s["lead_time_days"] for s in ds.suppliers}
    lead_time = {p["id"]: supplier_lead[p["supplier_id"]] for p in ds.products}
    for pid in product_ids:
        daily = recent_units[pid] / 90
        if sales_end[pid] < as_of:
            on_hand = rng.randint(15, 250)
        else:
            # Coverage relative to the reorder horizon (lead time + 14 days safety):
            # a small share is below it and shows up as a reorder suggestion.
            horizon = lead_time[pid] + 14
            roll = rng.random()
            if roll < 0.07:
                coverage = horizon * rng.uniform(0, 0.9)
            elif roll < 0.9:
                coverage = horizon * rng.uniform(1.2, 3.0)
            else:
                coverage = horizon * rng.uniform(4, 8)
            on_hand = round(daily * coverage) + reserved[pid] if daily > 0 else rng.randint(5, 40)
        ds.stock.append(
            {"product_id": pid, "on_hand": on_hand, "reserved": min(on_hand, reserved[pid])}
        )

    # Purchase orders: each supplier is ordered from roughly every two weeks.
    po_line_id = 0
    for supplier in ds.suppliers:
        sid = supplier["id"]
        assortment = [p["id"] for p in ds.products if p["supplier_id"] == sid]
        if not assortment:
            continue
        day = DATA_START + timedelta(days=rng.randint(0, 10))
        while day <= as_of:
            live = [p for p in assortment if sales_start[p] <= day <= sales_end[p]]
            if day.weekday() < 5 and live:
                po_id = len(ds.purchase_orders) + 1
                expected = day + timedelta(days=supplier["lead_time_days"])
                if rng.random() < reliability[sid]:
                    received: date | None = expected + timedelta(days=rng.randint(1, 21))
                else:
                    received = expected - timedelta(days=rng.randint(0, 2))
                if received is not None and received > as_of:
                    received = None
                ds.purchase_orders.append(
                    {
                        "id": po_id,
                        "po_no": f"BE-{day.year}-{po_id:05d}",
                        "supplier_id": sid,
                        "order_date": day,
                        "expected_date": expected,
                        "received_date": received,
                        "status": "received" if received else "open",
                    }
                )
                n_lines = min(len(live), rng.randint(2, 8))
                for pid in sorted(rng.sample(live, n_lines)):
                    product = ds.products[pid - 1]
                    po_line_id += 1
                    ds.purchase_order_lines.append(
                        {
                            "id": po_line_id,
                            "po_id": po_id,
                            "product_id": pid,
                            "quantity": product["min_order_qty"] * rng.randint(1, 6),
                            "unit_cost": product["purchase_price"],
                        }
                    )
            day += timedelta(days=rng.randint(10, 18))

    _check(ds)
    return ds


def _check(ds: Dataset) -> None:
    """Cheap sanity checks so a broken generator fails loudly instead of seeding nonsense."""
    assert ds.orders and ds.order_lines and ds.purchase_orders
    assert all(not math.isnan(float(p["list_price"])) for p in ds.products)
    assert len({p["sku"] for p in ds.products}) == len(ds.products)
