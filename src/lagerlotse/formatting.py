"""German number and date formatting for reports and the web app."""

from datetime import date
from decimal import Decimal


def number(value: Decimal | int | float | str | None, decimals: int = 0) -> str:
    if value is None or value == "":
        return "–"
    formatted = f"{Decimal(str(value)):,.{decimals}f}"
    return formatted.replace(",", "\0").replace(".", ",").replace("\0", ".")


def eur(value: Decimal | int | float | str | None) -> str:
    return "–" if value is None else f"{number(value, 2)} €"


def pct(value: Decimal | int | float | str | None) -> str:
    return "–" if value is None else f"{number(value, 1)} %"


def datum(value: date | str | None) -> str:
    if value is None:
        return "–"
    d = date.fromisoformat(value) if isinstance(value, str) else value
    return d.strftime("%d.%m.%Y")
