"""Deterministic check that every number in an answer comes from a tool result.

The model writes prose, tools produce numbers. This module extracts numbers (German format,
e.g. "1.234,56 €", "12,5 %", "1,2 Mio. €") and dates from the answer and looks for each one
among the tool inputs and outputs and the user's question. A number matches when the tool
value, rounded to the precision shown in the answer, equals it, and the units do not
agree: a number written with "€", "%" or "Tage" only matches a tool field with that unit.

Anything that cannot be matched makes the answer "unverified". The UI shows that state; it
never hides it.
"""

import re
from collections.abc import Iterator
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel

from lagerlotse.agent.tools import ToolCall

Unit = Literal["eur", "pct", "days", "units"]

MONTHS = {
    "januar": 1, "februar": 2, "märz": 3, "april": 4, "mai": 5, "juni": 6, "juli": 7,
    "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}  # fmt: skip
_MONTH_RE = "|".join(MONTHS)

DATE_PATTERNS = [
    re.compile(r"(?<!\d)(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})(?!\d)"),
    re.compile(r"(?<![\d.])(?P<d>\d{1,2})\.(?P<m>\d{1,2})\.(?P<y>\d{4})(?!\d)"),
    re.compile(rf"(?<![\d.])(?P<d>\d{{1,2}})\.\s*(?P<mn>{_MONTH_RE})(?:\s+(?P<y>\d{{4}}))?", re.I),
]
# Ordinals that name a period ("3. Quartal") and Markdown list markers are not figures.
IGNORED_PATTERNS = [
    re.compile(r"(?<![\d.,])[1-4]\.\s*(?:Quartal|Halbjahr)", re.I),
    re.compile(r"^\s*\d{1,2}[.)]\s", re.M),
]
NUMBER_RE = re.compile(
    r"""
    (?<![\w.,])(?<!\w-)                      # not part of an identifier like KB-10001
    (?P<num>\d{1,3}(?:\.\d{3})+(?:,\d+)?     # 1.234.567,89
           |\d+(?:,\d+)?)                    # 1234,5 / 12
    (?![\w-]|[.,]\d)
    (?:\s*(?P<scale>Mio\.?|Millionen|Mrd\.?|Tsd\.?|Tausend)(?!\w))?
    (?:\s*(?P<unit>€|EUR\b|Euro\b|%|Prozent\b|Tage?n?\b))?
    """,
    re.X,
)
SCALES = {"mio": Decimal(10) ** 6, "millionen": Decimal(10) ** 6, "mrd": Decimal(10) ** 9,
          "tsd": Decimal(10) ** 3, "tausend": Decimal(10) ** 3}  # fmt: skip
TOOL_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
TOOL_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class NumberCheck(BaseModel):
    text: str
    value: Decimal
    unit: Unit | None
    matched: bool
    source: str | None = None  # where the number was found, e.g. "top_customers.total_revenue_eur"


class Verification(BaseModel):
    status: Literal["verified", "unverified", "no_numbers"]
    checks: list[NumberCheck]

    @property
    def mismatches(self) -> list[NumberCheck]:
        return [c for c in self.checks if not c.matched]


class _Known(BaseModel):
    value: Decimal
    unit: Unit | None
    source: str


# --- collecting known figures from tool calls --------------------------------------------


def _unit_from_field(field: str) -> Unit | None:
    """Units follow the naming convention of the tool models (see data/queries.py)."""
    tokens = field.split("_")
    if "eur" in tokens:
        return "eur"
    if "pct" in tokens:
        return "pct"
    if "days" in tokens:
        return "days"
    if "units" in tokens:
        return "units"
    return None


def _walk(value: Any, path: str, field: str) -> Iterator[tuple[str, str, Any]]:
    """Yield (path, field name, leaf value) for all leaves; list lengths count as leaves."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}", key)
    elif isinstance(value, list):
        yield f"{path}.<Anzahl>", "", len(value)
        for i, child in enumerate(value):
            yield from _walk(child, f"{path}[{i}]", field)
    else:
        yield path, field, value


def _collect(calls: list[ToolCall], question: str) -> tuple[list[_Known], set[date]]:
    known: list[_Known] = []
    dates: set[date] = set()
    for call in calls:
        for part, data in (("input", call.input), ("output", call.output or {})):
            for path, field, leaf in _walk(data, f"{call.name}.{part}", ""):
                if isinstance(leaf, bool) or leaf is None:
                    continue
                if isinstance(leaf, int | float):
                    known.append(
                        _Known(value=Decimal(str(leaf)), unit=_unit_from_field(field), source=path)
                    )
                elif isinstance(leaf, str) and TOOL_NUMBER_RE.match(leaf):
                    known.append(
                        _Known(value=Decimal(leaf), unit=_unit_from_field(field), source=path)
                    )
                elif isinstance(leaf, str) and TOOL_DATE_RE.match(leaf):
                    dates.add(date.fromisoformat(leaf))
                elif isinstance(leaf, str):
                    # Numbers inside names, e.g. "Kabelbinder 4,8 x 300 mm".
                    for found in _numbers(leaf):
                        known.append(_Known(value=found.value, unit=None, source=path))
    for found in _numbers(question):
        known.append(_Known(value=found.value, unit=None, source="Frage"))
    for found_date in _dates(question)[0]:
        dates.add(found_date)
    for d in list(dates):
        known.append(_Known(value=Decimal(d.year), unit=None, source=f"Jahr aus {d}"))
    return known, dates


# --- extracting numbers and dates from text ---------------------------------------------


class _Found(BaseModel):
    text: str
    value: Decimal
    decimals: int
    scale: Decimal
    unit: Unit | None


def _parse_unit(raw: str | None) -> Unit | None:
    if not raw:
        return None
    raw = raw.lower()
    if raw in ("€", "eur", "euro"):
        return "eur"
    if raw in ("%", "prozent"):
        return "pct"
    return "days"


def _numbers(text: str) -> list[_Found]:
    found = []
    for m in NUMBER_RE.finditer(text):
        raw = m.group("num")
        integer, _, fraction = raw.partition(",")
        try:
            base = Decimal(integer.replace(".", "") + ("." + fraction if fraction else ""))
        except InvalidOperation:
            continue
        scale_raw = (m.group("scale") or "").rstrip(".").lower()
        scale = SCALES.get(scale_raw, Decimal(1))
        found.append(
            _Found(
                text=m.group(0).strip(),
                value=base * scale,
                decimals=len(fraction),
                scale=scale,
                unit=_parse_unit(m.group("unit")),
            )
        )
    return found


def _dates(text: str) -> tuple[list[date], list[tuple[str, int, int]], str]:
    """Return full dates, (text, day, month) without year, and the text with dates blanked."""
    full: list[date] = []
    partial: list[tuple[str, int, int]] = []

    def blank(m: re.Match[str]) -> str:
        month = int(m.group("m")) if "m" in m.groupdict() and m.group("m") else 0
        if not month:
            month = MONTHS[m.group("mn").lower()]
        day = int(m.group("d"))
        if m.group("y"):
            try:
                full.append(date(int(m.group("y")), month, day))
            except ValueError:
                partial.append((m.group(0), day, month))
        else:
            partial.append((m.group(0), day, month))
        return " " * len(m.group(0))

    for pattern in DATE_PATTERNS:
        text = pattern.sub(blank, text)
    return full, partial, text


# --- matching -----------------------------------------------------------------------------


def _match(found: _Found, known: list[_Known]) -> _Known | None:
    tolerance = Decimal("0.5") * Decimal(10) ** -found.decimals * found.scale
    for candidate in known:
        # A unit in the answer must agree with the tool field; numbers the user wrote count too.
        if found.unit and found.unit != candidate.unit and candidate.source != "Frage":
            continue
        if abs(abs(candidate.value) - found.value) <= tolerance:
            return candidate
    return None


def verify_answer(answer: str, calls: list[ToolCall], question: str = "") -> Verification:
    known, known_dates = _collect(calls, question)
    full_dates, partial_dates, rest = _dates(answer)
    checks: list[NumberCheck] = []

    for d in full_dates:
        ok = d in known_dates
        checks.append(
            NumberCheck(
                text=d.isoformat(),
                value=Decimal(d.strftime("%Y%m%d")),
                unit=None,
                matched=ok,
                source="Datum" if ok else None,
            )
        )
    for text, day, month in partial_dates:
        ok = any(k.day == day and k.month == month for k in known_dates)
        checks.append(
            NumberCheck(
                text=text, value=Decimal(day), unit=None, matched=ok, source="Datum" if ok else None
            )
        )

    for pattern in IGNORED_PATTERNS:
        rest = pattern.sub(lambda m: " " * len(m.group(0)), rest)
    for found in _numbers(rest):
        hit = _match(found, known)
        checks.append(
            NumberCheck(
                text=found.text,
                value=found.value,
                unit=found.unit,
                matched=hit is not None,
                source=hit.source if hit else None,
            )
        )

    if not checks:
        return Verification(status="no_numbers", checks=[])
    status: Literal["verified", "unverified"] = (
        "verified" if all(c.matched for c in checks) else "unverified"
    )
    return Verification(status=status, checks=checks)


def contains_figure(text: str, expected: Decimal) -> bool:
    """True if `text` shows `expected`, possibly rounded to the precision written there.

    Used by the evaluation to check that an answer contains the figure computed by SQL.
    """
    _, _, rest = _dates(text)
    for found in _numbers(rest):
        tolerance = Decimal("0.5") * Decimal(10) ** -found.decimals * found.scale
        if abs(found.value - abs(expected)) <= tolerance:
            return True
    return False
