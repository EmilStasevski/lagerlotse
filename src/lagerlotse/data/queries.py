"""Read-only query functions. These are the agent's tools, the report's data source and the
reference for the dashboard.

Conventions:
- Revenue ("Umsatz") is the net order value (quantity x net unit price) of all orders that are
  not cancelled, assigned by order date. Gross margin ("Rohertrag") is revenue minus purchase
  cost at time of sale.
- "Today" is the dataset's reference date (`dataset_meta.as_of`), not the system clock.
- Every figure carries its unit in the field name (`_eur`, `_pct`, `_units`, `_days`).
- Docstrings are German because the model reads them as tool descriptions.
"""

import math
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Connection, text

DEMAND_WINDOW_DAYS = 90
SAFETY_DAYS = 14
TARGET_EXTRA_DAYS = 30


class ToolError(Exception):
    """Invalid input that the model can fix, e.g. an unknown category. Message is German."""


# --- shared models -------------------------------------------------------------------------


class Period(BaseModel):
    start: date
    end: date


class DateRangeInput(BaseModel):
    start_date: date = Field(description="Erster Tag des Zeitraums (einschließlich), ISO-Datum")
    end_date: date = Field(description="Letzter Tag des Zeitraums (einschließlich), ISO-Datum")

    @model_validator(mode="after")
    def _check_range(self) -> "DateRangeInput":
        if self.start_date > self.end_date:
            raise ValueError("start_date muss vor oder gleich end_date liegen")
        return self

    @property
    def period(self) -> Period:
        return Period(start=self.start_date, end=self.end_date)


def _round(value: Decimal, places: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    return _round(100 * part / whole, 1) if whole else Decimal("0.0")


def get_as_of(conn: Connection) -> date:
    value = conn.execute(text("SELECT value FROM dataset_meta WHERE key = 'as_of'")).scalar_one()
    return date.fromisoformat(value)


def _check_value(conn: Connection, column: str, table: str, value: str | None, label: str) -> None:
    if value is None:
        return
    found = conn.execute(text(f"SELECT 1 FROM {table} WHERE {column} = :v"), {"v": value}).first()
    if found is None:
        options = conn.execute(
            text(f"SELECT DISTINCT {column} FROM {table} ORDER BY 1 LIMIT 20")
        ).scalars()
        raise ToolError(
            f"Unbekannte {label} '{value}'. Gültige Werte (Auszug): {', '.join(options)}"
        )


def _check_category(conn: Connection, category: str | None) -> None:
    _check_value(conn, "category", "products", category, "Kategorie")


def _check_sku(conn: Connection, sku: str | None) -> None:
    _check_value(conn, "sku", "products", sku, "Artikelnummer")


def _check_supplier(conn: Connection, supplier_no: str | None) -> None:
    _check_value(conn, "supplier_no", "suppliers", supplier_no, "Lieferantennummer")


# --- 1. top_customers ----------------------------------------------------------------------


class TopCustomersInput(DateRangeInput):
    limit: int = Field(5, ge=1, le=50, description="Anzahl Kunden (1-50)")


class CustomerRevenue(BaseModel):
    rank: int
    customer_no: str
    name: str
    segment: str
    city: str
    revenue_eur: Decimal
    order_count: int
    share_of_total_pct: Decimal


class TopCustomersResult(BaseModel):
    period: Period
    total_revenue_eur: Decimal
    customers_with_orders: int
    customers: list[CustomerRevenue]


def top_customers(conn: Connection, params: TopCustomersInput) -> TopCustomersResult:
    """Kunden mit dem höchsten Umsatz in einem Zeitraum.

    Umsatz = Netto-Auftragswert aller nicht stornierten Aufträge nach Auftragsdatum.
    Liefert Rang, Kundennummer, Name, Umsatz in EUR, Anzahl Aufträge und Anteil am
    Gesamtumsatz des Zeitraums in Prozent.
    """
    bounds = {"start": params.start_date, "end": params.end_date}
    total, count = conn.execute(
        text("""
            SELECT coalesce(sum(l.quantity * l.unit_price), 0), count(DISTINCT o.customer_id)
            FROM orders o JOIN order_lines l ON l.order_id = o.id
            WHERE o.status <> 'cancelled' AND o.order_date BETWEEN :start AND :end
        """),
        bounds,
    ).one()
    rows = conn.execute(
        text("""
            SELECT c.customer_no, c.name, c.segment, c.city,
                   sum(l.quantity * l.unit_price) AS revenue,
                   count(DISTINCT o.id) AS orders
            FROM orders o
            JOIN order_lines l ON l.order_id = o.id
            JOIN customers c ON c.id = o.customer_id
            WHERE o.status <> 'cancelled' AND o.order_date BETWEEN :start AND :end
            GROUP BY c.id
            ORDER BY revenue DESC, c.customer_no
            LIMIT :limit
        """),
        {**bounds, "limit": params.limit},
    ).all()
    return TopCustomersResult(
        period=params.period,
        total_revenue_eur=_round(total, 2),
        customers_with_orders=count,
        customers=[
            CustomerRevenue(
                rank=i,
                customer_no=r.customer_no,
                name=r.name,
                segment=r.segment,
                city=r.city,
                revenue_eur=_round(r.revenue, 2),
                order_count=r.orders,
                share_of_total_pct=_pct(r.revenue, total),
            )
            for i, r in enumerate(rows, start=1)
        ],
    )


# --- 2. revenue_by_period ------------------------------------------------------------------


class RevenueByPeriodInput(DateRangeInput):
    granularity: Literal["month", "quarter", "year"] = Field(
        "month", description="Aufteilung: month, quarter oder year"
    )
    category: str | None = Field(None, description="Optional: nur diese Produktkategorie")


class PeriodRevenue(BaseModel):
    period_label: str
    period_start: date
    revenue_eur: Decimal
    gross_margin_eur: Decimal
    margin_pct: Decimal
    order_count: int


class RevenueByPeriodResult(BaseModel):
    period: Period
    granularity: str
    category: str | None
    total_revenue_eur: Decimal
    total_gross_margin_eur: Decimal
    total_margin_pct: Decimal
    periods: list[PeriodRevenue]


_LABEL_FORMAT = {"month": "YYYY-MM", "quarter": 'YYYY-"Q"Q', "year": "YYYY"}
_STEP = {"month": "1 month", "quarter": "3 months", "year": "1 year"}


def revenue_by_period(conn: Connection, params: RevenueByPeriodInput) -> RevenueByPeriodResult:
    """Umsatz, Rohertrag und Marge je Monat, Quartal oder Jahr, optional für eine Kategorie.

    Umsatz = Netto-Auftragswert aller nicht stornierten Aufträge nach Auftragsdatum.
    Rohertrag = Umsatz minus Einkaufspreis. Marge in Prozent = Rohertrag / Umsatz.
    Angebrochene Perioden am Rand zählen nur die Tage innerhalb des Zeitraums.
    """
    _check_category(conn, params.category)
    rows = conn.execute(
        text("""
            WITH buckets AS (
                SELECT generate_series(date_trunc(:g, CAST(:start AS date)),
                                       CAST(:end AS date), CAST(:step AS interval))::date AS b
            ),
            sales AS (
                SELECT date_trunc(:g, o.order_date)::date AS b,
                       sum(l.quantity * l.unit_price) AS revenue,
                       sum(l.quantity * (l.unit_price - l.unit_cost)) AS margin,
                       count(DISTINCT o.id) AS orders
                FROM orders o
                JOIN order_lines l ON l.order_id = o.id
                JOIN products p ON p.id = l.product_id
                WHERE o.status <> 'cancelled' AND o.order_date BETWEEN :start AND :end
                  AND (CAST(:category AS text) IS NULL OR p.category = :category)
                GROUP BY 1
            )
            SELECT to_char(b.b, :fmt) AS label, b.b AS start,
                   coalesce(s.revenue, 0) AS revenue, coalesce(s.margin, 0) AS margin,
                   coalesce(s.orders, 0) AS orders
            FROM buckets b LEFT JOIN sales s USING (b)
            ORDER BY b.b
        """),
        {
            "g": params.granularity,
            "start": params.start_date,
            "end": params.end_date,
            "category": params.category,
            "fmt": _LABEL_FORMAT[params.granularity],
            "step": _STEP[params.granularity],
        },
    ).all()
    total_revenue = sum((r.revenue for r in rows), Decimal(0))
    total_margin = sum((r.margin for r in rows), Decimal(0))
    return RevenueByPeriodResult(
        period=params.period,
        granularity=params.granularity,
        category=params.category,
        total_revenue_eur=_round(total_revenue, 2),
        total_gross_margin_eur=_round(total_margin, 2),
        total_margin_pct=_pct(total_margin, total_revenue),
        periods=[
            PeriodRevenue(
                period_label=r.label,
                period_start=r.start,
                revenue_eur=_round(r.revenue, 2),
                gross_margin_eur=_round(r.margin, 2),
                margin_pct=_pct(r.margin, r.revenue),
                order_count=r.orders,
            )
            for r in rows
        ],
    )


# --- 3. product_margin ---------------------------------------------------------------------


class ProductMarginInput(DateRangeInput):
    category: str | None = Field(None, description="Optional: nur diese Produktkategorie")
    sku: str | None = Field(None, description="Optional: nur dieser Artikel (Artikelnummer)")
    sort_by: Literal["margin_eur", "margin_pct", "revenue_eur"] = Field(
        "margin_eur", description="Sortierung nach Rohertrag, Marge in Prozent oder Umsatz"
    )
    order: Literal["highest", "lowest"] = Field("highest", description="highest oder lowest")
    limit: int = Field(10, ge=1, le=50, description="Anzahl Artikel (1-50)")


class ProductMarginRow(BaseModel):
    sku: str
    name: str
    category: str
    unit: str
    units_sold: int
    revenue_eur: Decimal
    cost_eur: Decimal
    margin_eur: Decimal
    margin_pct: Decimal


class ProductMarginResult(BaseModel):
    period: Period
    sort_by: str
    order: str
    products_with_sales: int
    products: list[ProductMarginRow]


def product_margin(conn: Connection, params: ProductMarginInput) -> ProductMarginResult:
    """Umsatz, Einkaufskosten, Rohertrag und Marge je Artikel in einem Zeitraum.

    Sortierbar nach Rohertrag (margin_eur), Marge in Prozent (margin_pct) oder Umsatz,
    höchste oder niedrigste zuerst. Optional gefiltert nach Kategorie oder Artikelnummer.
    Mengen sind Verkaufseinheiten (Feld unit, z. B. Beutel mit 100 Stück).
    """
    _check_category(conn, params.category)
    _check_sku(conn, params.sku)
    rows = conn.execute(
        text("""
            SELECT p.sku, p.name, p.category, p.unit,
                   sum(l.quantity) AS units,
                   sum(l.quantity * l.unit_price) AS revenue,
                   sum(l.quantity * l.unit_cost) AS cost
            FROM orders o
            JOIN order_lines l ON l.order_id = o.id
            JOIN products p ON p.id = l.product_id
            WHERE o.status <> 'cancelled' AND o.order_date BETWEEN :start AND :end
              AND (CAST(:category AS text) IS NULL OR p.category = :category)
              AND (CAST(:sku AS text) IS NULL OR p.sku = :sku)
            GROUP BY p.id
        """),
        {
            "start": params.start_date,
            "end": params.end_date,
            "category": params.category,
            "sku": params.sku,
        },
    ).all()
    result = [
        ProductMarginRow(
            sku=r.sku,
            name=r.name,
            category=r.category,
            unit=r.unit,
            units_sold=r.units,
            revenue_eur=_round(r.revenue, 2),
            cost_eur=_round(r.cost, 2),
            margin_eur=_round(r.revenue - r.cost, 2),
            margin_pct=_pct(r.revenue - r.cost, r.revenue),
        )
        for r in rows
    ]
    result.sort(key=lambda r: r.sku)
    result.sort(key=lambda r: getattr(r, params.sort_by), reverse=params.order == "highest")
    return ProductMarginResult(
        period=params.period,
        sort_by=params.sort_by,
        order=params.order,
        products_with_sales=len(result),
        products=result[: params.limit],
    )


# --- 4. stock_coverage ---------------------------------------------------------------------


class StockCoverageInput(BaseModel):
    category: str | None = Field(None, description="Optional: nur diese Produktkategorie")
    sku: str | None = Field(None, description="Optional: nur dieser Artikel (Artikelnummer)")
    max_coverage_days: int | None = Field(
        None, ge=0, description="Optional: nur Artikel mit Reichweite bis zu so vielen Tagen"
    )
    limit: int = Field(20, ge=1, le=100, description="Anzahl Artikel (1-100)")


class StockCoverageRow(BaseModel):
    sku: str
    name: str
    category: str
    unit: str
    on_hand_units: int
    reserved_units: int
    available_units: int
    avg_daily_demand_units: Decimal
    coverage_days: Decimal | None  # None: no demand in the window


class StockCoverageResult(BaseModel):
    as_of: date
    demand_window: Period
    demand_window_days: int
    matching_products: int
    products: list[StockCoverageRow]


def _demand_window(as_of: date) -> Period:
    return Period(start=as_of - timedelta(days=DEMAND_WINDOW_DAYS - 1), end=as_of)


_STOCK_SQL = """
    SELECT p.id, p.sku, p.name, p.category, p.unit, p.purchase_price, p.min_order_qty,
           s.supplier_no, s.name AS supplier_name, s.lead_time_days,
           st.on_hand, st.reserved,
           coalesce(d.units, 0) AS demand_units,
           coalesce(po.units, 0) AS open_po_units
    FROM products p
    JOIN suppliers s ON s.id = p.supplier_id
    JOIN stock st ON st.product_id = p.id
    LEFT JOIN (
        SELECT l.product_id, sum(l.quantity) AS units
        FROM orders o JOIN order_lines l ON l.order_id = o.id
        WHERE o.status <> 'cancelled' AND o.order_date BETWEEN :wstart AND :wend
        GROUP BY 1
    ) d ON d.product_id = p.id
    LEFT JOIN (
        SELECT pl.product_id, sum(pl.quantity) AS units
        FROM purchase_orders po JOIN purchase_order_lines pl ON pl.po_id = po.id
        WHERE po.status = 'open'
        GROUP BY 1
    ) po ON po.product_id = p.id
    WHERE p.active
      AND (CAST(:category AS text) IS NULL OR p.category = :category)
      AND (CAST(:sku AS text) IS NULL OR p.sku = :sku)
      AND (CAST(:supplier_no AS text) IS NULL OR s.supplier_no = :supplier_no)
"""


def _stock_rows(
    conn: Connection, as_of: date, category: str | None, sku: str | None, supplier_no: str | None
) -> list:  # type: ignore[type-arg]
    window = _demand_window(as_of)
    return list(
        conn.execute(
            text(_STOCK_SQL),
            {
                "wstart": window.start,
                "wend": window.end,
                "category": category,
                "sku": sku,
                "supplier_no": supplier_no,
            },
        ).all()
    )


def stock_coverage(conn: Connection, params: StockCoverageInput) -> StockCoverageResult:
    """Lagerreichweite je Artikel: wie viele Tage reicht der verfügbare Bestand?

    Verfügbar = Lagerbestand minus für offene Aufträge reservierte Menge.
    Tagesbedarf = verkaufte Menge der letzten 90 Tage / 90.
    Reichweite in Tagen = verfügbar / Tagesbedarf (leer, wenn kein Bedarf).
    Sortiert nach kürzester Reichweite. Mengen sind Verkaufseinheiten (Feld unit).
    """
    _check_category(conn, params.category)
    _check_sku(conn, params.sku)
    as_of = get_as_of(conn)
    rows: list[StockCoverageRow] = []
    for r in _stock_rows(conn, as_of, params.category, params.sku, None):
        daily = Decimal(r.demand_units) / DEMAND_WINDOW_DAYS
        available = r.on_hand - r.reserved
        coverage = _round(available / daily, 1) if daily else None
        if params.max_coverage_days is not None and (
            coverage is None or coverage > params.max_coverage_days
        ):
            continue
        rows.append(
            StockCoverageRow(
                sku=r.sku,
                name=r.name,
                category=r.category,
                unit=r.unit,
                on_hand_units=r.on_hand,
                reserved_units=r.reserved,
                available_units=available,
                avg_daily_demand_units=_round(daily, 2),
                coverage_days=coverage,
            )
        )
    rows.sort(key=lambda r: (r.coverage_days is None, r.coverage_days or 0, r.sku))
    return StockCoverageResult(
        as_of=as_of,
        demand_window=_demand_window(as_of),
        demand_window_days=DEMAND_WINDOW_DAYS,
        matching_products=len(rows),
        products=rows[: params.limit],
    )


# --- 5. slow_movers ------------------------------------------------------------------------


class SlowMoversInput(BaseModel):
    min_days_without_sale: int = Field(
        180, ge=30, le=730, description="Mindestanzahl Tage ohne Verkauf (30-730)"
    )
    limit: int = Field(20, ge=1, le=100, description="Anzahl Artikel (1-100)")


class SlowMoverRow(BaseModel):
    sku: str
    name: str
    category: str
    unit: str
    last_sale_date: date | None
    days_since_last_sale: int | None
    on_hand_units: int
    stock_value_eur: Decimal


class SlowMoversResult(BaseModel):
    as_of: date
    min_days_without_sale: int
    product_count: int
    total_stock_value_eur: Decimal
    products: list[SlowMoverRow]


def slow_movers(conn: Connection, params: SlowMoversInput) -> SlowMoversResult:
    """Ladenhüter: Artikel mit Lagerbestand, die seit mindestens N Tagen nicht verkauft wurden.

    Lagerwert = Bestand x Einkaufspreis. Sortiert nach Lagerwert, höchster zuerst.
    product_count und total_stock_value_eur beziehen sich auf alle Treffer, nicht nur
    auf die ausgegebenen Zeilen.
    """
    as_of = get_as_of(conn)
    rows = conn.execute(
        text("""
            SELECT p.sku, p.name, p.category, p.unit, ls.last_sale,
                   CAST(:as_of AS date) - ls.last_sale AS days,
                   st.on_hand, st.on_hand * p.purchase_price AS value
            FROM products p
            JOIN stock st ON st.product_id = p.id
            LEFT JOIN (
                SELECT l.product_id, max(o.order_date) AS last_sale
                FROM orders o JOIN order_lines l ON l.order_id = o.id
                WHERE o.status <> 'cancelled' AND o.order_date <= :as_of
                GROUP BY 1
            ) ls ON ls.product_id = p.id
            WHERE st.on_hand > 0
              AND (ls.last_sale IS NULL OR CAST(:as_of AS date) - ls.last_sale >= :min_days)
            ORDER BY value DESC, p.sku
        """),
        {"as_of": as_of, "min_days": params.min_days_without_sale},
    ).all()
    return SlowMoversResult(
        as_of=as_of,
        min_days_without_sale=params.min_days_without_sale,
        product_count=len(rows),
        total_stock_value_eur=_round(sum((r.value for r in rows), Decimal(0)), 2),
        products=[
            SlowMoverRow(
                sku=r.sku,
                name=r.name,
                category=r.category,
                unit=r.unit,
                last_sale_date=r.last_sale,
                days_since_last_sale=r.days,
                on_hand_units=r.on_hand,
                stock_value_eur=_round(r.value, 2),
            )
            for r in rows[: params.limit]
        ],
    )


# --- 6. open_purchase_orders ---------------------------------------------------------------


class OpenPurchaseOrdersInput(BaseModel):
    supplier_no: str | None = Field(
        None, description="Optional: nur dieser Lieferant (z. B. L-101)"
    )
    sku: str | None = Field(None, description="Optional: nur Bestellungen mit diesem Artikel")
    only_overdue: bool = Field(
        False, description="Nur Bestellungen mit überschrittenem Liefertermin"
    )


class OpenPurchaseOrderRow(BaseModel):
    po_no: str
    supplier_no: str
    supplier_name: str
    order_date: date
    expected_date: date
    days_overdue: int
    line_count: int
    total_value_eur: Decimal


class OpenPurchaseOrdersResult(BaseModel):
    as_of: date
    order_count: int
    overdue_count: int
    total_value_eur: Decimal
    purchase_orders: list[OpenPurchaseOrderRow]


def open_purchase_orders(
    conn: Connection, params: OpenPurchaseOrdersInput
) -> OpenPurchaseOrdersResult:
    """Offene Einkaufsbestellungen bei Lieferanten, noch nicht eingegangen.

    days_overdue = Tage seit dem erwarteten Liefertermin (0, wenn noch nicht fällig).
    Optional gefiltert nach Lieferantennummer, Artikelnummer oder nur überfällige.
    """
    _check_supplier(conn, params.supplier_no)
    _check_sku(conn, params.sku)
    as_of = get_as_of(conn)
    rows = conn.execute(
        text("""
            SELECT po.po_no, s.supplier_no, s.name AS supplier_name, po.order_date,
                   po.expected_date,
                   greatest(0, CAST(:as_of AS date) - po.expected_date) AS overdue,
                   count(*) AS lines, sum(pl.quantity * pl.unit_cost) AS value
            FROM purchase_orders po
            JOIN suppliers s ON s.id = po.supplier_id
            JOIN purchase_order_lines pl ON pl.po_id = po.id
            WHERE po.status = 'open'
              AND (CAST(:supplier_no AS text) IS NULL OR s.supplier_no = :supplier_no)
              AND (CAST(:sku AS text) IS NULL OR po.id IN (
                    SELECT pl2.po_id FROM purchase_order_lines pl2
                    JOIN products p ON p.id = pl2.product_id WHERE p.sku = :sku))
            GROUP BY po.id, s.id
            ORDER BY po.expected_date, po.po_no
        """),
        {"as_of": as_of, "supplier_no": params.supplier_no, "sku": params.sku},
    ).all()
    result = [
        OpenPurchaseOrderRow(
            po_no=r.po_no,
            supplier_no=r.supplier_no,
            supplier_name=r.supplier_name,
            order_date=r.order_date,
            expected_date=r.expected_date,
            days_overdue=r.overdue,
            line_count=r.lines,
            total_value_eur=_round(r.value, 2),
        )
        for r in rows
        if not params.only_overdue or r.overdue > 0
    ]
    return OpenPurchaseOrdersResult(
        as_of=as_of,
        order_count=len(result),
        overdue_count=sum(1 for r in result if r.days_overdue > 0),
        total_value_eur=sum((r.total_value_eur for r in result), Decimal("0.00")),
        purchase_orders=result,
    )


# --- 7. late_deliveries --------------------------------------------------------------------


class LateDeliveriesInput(DateRangeInput):
    pass


class SupplierDeliveryRow(BaseModel):
    supplier_no: str
    supplier_name: str
    deliveries_received: int
    late_deliveries: int
    late_share_pct: Decimal
    avg_delay_days_when_late: Decimal | None
    max_delay_days: int | None
    open_overdue_orders: int


class LateDeliveriesResult(BaseModel):
    period: Period
    as_of: date
    deliveries_received: int
    late_deliveries: int
    late_share_pct: Decimal
    on_time_share_pct: Decimal
    suppliers: list[SupplierDeliveryRow]


def late_deliveries(conn: Connection, params: LateDeliveriesInput) -> LateDeliveriesResult:
    """Liefertreue der Lieferanten: verspätete Wareneingänge in einem Zeitraum.

    Betrachtet Einkaufsbestellungen, deren erwarteter Liefertermin im Zeitraum liegt.
    Verspätet = Wareneingang nach dem erwarteten Termin; on_time_share_pct ist der pünktliche
    Anteil. Zusätzlich je Lieferant die
    Zahl der offenen, bereits überfälligen Bestellungen. Sortiert nach Verspätungsquote.
    """
    as_of = get_as_of(conn)
    rows = conn.execute(
        text("""
            SELECT s.supplier_no, s.name,
                   count(*) FILTER (WHERE po.status = 'received') AS received,
                   count(*) FILTER (WHERE po.received_date > po.expected_date) AS late,
                   avg(po.received_date - po.expected_date)
                       FILTER (WHERE po.received_date > po.expected_date) AS avg_delay,
                   max(po.received_date - po.expected_date)
                       FILTER (WHERE po.received_date > po.expected_date) AS max_delay,
                   count(*) FILTER (WHERE po.status = 'open' AND po.expected_date < :as_of)
                       AS open_overdue
            FROM purchase_orders po
            JOIN suppliers s ON s.id = po.supplier_id
            WHERE po.expected_date BETWEEN :start AND :end
            GROUP BY s.id
        """),
        {"start": params.start_date, "end": params.end_date, "as_of": as_of},
    ).all()
    suppliers = [
        SupplierDeliveryRow(
            supplier_no=r.supplier_no,
            supplier_name=r.name,
            deliveries_received=r.received,
            late_deliveries=r.late,
            late_share_pct=_pct(Decimal(r.late), Decimal(r.received)),
            avg_delay_days_when_late=None if r.avg_delay is None else _round(r.avg_delay, 1),
            max_delay_days=r.max_delay,
            open_overdue_orders=r.open_overdue,
        )
        for r in rows
    ]
    suppliers.sort(key=lambda r: (-r.late_share_pct, r.supplier_no))
    received = sum(r.deliveries_received for r in suppliers)
    late = sum(r.late_deliveries for r in suppliers)
    return LateDeliveriesResult(
        period=params.period,
        as_of=as_of,
        deliveries_received=received,
        late_deliveries=late,
        late_share_pct=_pct(Decimal(late), Decimal(received)),
        on_time_share_pct=_pct(Decimal(received - late), Decimal(received)),
        suppliers=suppliers,
    )


# --- 8. reorder_suggestions ----------------------------------------------------------------


class ReorderSuggestionsInput(BaseModel):
    category: str | None = Field(None, description="Optional: nur diese Produktkategorie")
    supplier_no: str | None = Field(
        None, description="Optional: nur dieser Lieferant (z. B. L-101)"
    )
    limit: int = Field(30, ge=1, le=100, description="Anzahl Vorschläge (1-100)")


class ReorderRow(BaseModel):
    sku: str
    name: str
    category: str
    unit: str
    supplier_no: str
    supplier_name: str
    available_units: int
    open_po_units: int
    avg_daily_demand_units: Decimal
    coverage_days: Decimal
    lead_time_days: int
    reorder_point_units: int
    suggested_qty_units: int
    est_cost_eur: Decimal


class ReorderSuggestionsResult(BaseModel):
    as_of: date
    demand_window: Period
    demand_window_days: int
    safety_days: int
    target_extra_days: int
    suggestion_count: int
    total_est_cost_eur: Decimal
    suggestions: list[ReorderRow]


def reorder_suggestions(
    conn: Connection, params: ReorderSuggestionsInput
) -> ReorderSuggestionsResult:
    """Nachbestellvorschläge auf Basis von Bedarf, Bestand, offenen Bestellungen und Lieferzeit.

    Tagesbedarf = verkaufte Menge der letzten 90 Tage / 90.
    Meldebestand = Tagesbedarf x (Lieferzeit + 14 Tage Sicherheit), aufgerundet.
    Vorschlag, wenn verfügbarer Bestand + offene Bestellmenge unter dem Meldebestand liegt.
    Bestellmenge deckt Lieferzeit + 14 + 30 Tage, aufgerundet auf die Mindestbestellmenge.
    Geschätzte Kosten = Bestellmenge x Einkaufspreis. Sortiert nach kürzester Reichweite.
    """
    _check_category(conn, params.category)
    _check_supplier(conn, params.supplier_no)
    as_of = get_as_of(conn)
    suggestions: list[ReorderRow] = []
    for r in _stock_rows(conn, as_of, params.category, None, params.supplier_no):
        if r.demand_units == 0:
            continue
        daily = Decimal(r.demand_units) / DEMAND_WINDOW_DAYS
        available = r.on_hand - r.reserved
        position = available + r.open_po_units
        reorder_point = math.ceil(daily * (r.lead_time_days + SAFETY_DAYS))
        if position >= reorder_point:
            continue
        target = math.ceil(daily * (r.lead_time_days + SAFETY_DAYS + TARGET_EXTRA_DAYS))
        qty = math.ceil((target - position) / r.min_order_qty) * r.min_order_qty
        suggestions.append(
            ReorderRow(
                sku=r.sku,
                name=r.name,
                category=r.category,
                unit=r.unit,
                supplier_no=r.supplier_no,
                supplier_name=r.supplier_name,
                available_units=available,
                open_po_units=r.open_po_units,
                avg_daily_demand_units=_round(daily, 2),
                coverage_days=_round(available / daily, 1),
                lead_time_days=r.lead_time_days,
                reorder_point_units=reorder_point,
                suggested_qty_units=qty,
                est_cost_eur=_round(qty * r.purchase_price, 2),
            )
        )
    suggestions.sort(key=lambda r: (r.coverage_days, r.sku))
    return ReorderSuggestionsResult(
        as_of=as_of,
        demand_window=_demand_window(as_of),
        demand_window_days=DEMAND_WINDOW_DAYS,
        safety_days=SAFETY_DAYS,
        target_extra_days=TARGET_EXTRA_DAYS,
        suggestion_count=len(suggestions),
        total_est_cost_eur=sum((s.est_cost_eur for s in suggestions), Decimal("0.00")),
        suggestions=suggestions[: params.limit],
    )
