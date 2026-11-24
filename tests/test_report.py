"""Weekly report: content from the fixture data, and every figure passes the verifier."""

from pathlib import Path

from sqlalchemy import Connection

from lagerlotse import formatting
from lagerlotse.agent.verifier import verify_answer
from lagerlotse.report import build_report, render, write_report


def test_formatting() -> None:
    assert formatting.eur("1234567.5") == "1.234.567,50 €"
    assert formatting.pct("4.1") == "4,1 %"
    assert formatting.number(None) == "–"
    assert formatting.datum("2026-06-30") == "30.06.2026"


def test_report_content(conn: Connection) -> None:
    markdown = render(build_report(conn), "md")
    assert "Stichtag 30.06.2026" in markdown
    # KB-1: 30 units suggested for 60,00 € (see test_queries.test_reorder_suggestions)
    assert "| KB-1 | Kabelbinder A | Testlieferant Nord GmbH | 11 | 0 | 18,3 |" in markdown
    assert "| 30 | Stück | 60,00 € |" in markdown
    assert (
        "| BE-4 | Testlieferant Fern Ltd. | 01.05.2026 | 10.06.2026 | 20 | 200,00 € |" in markdown
    )
    assert "BF-1" in markdown


def test_every_figure_in_the_report_is_verified(conn: Connection) -> None:
    report = build_report(conn)
    result = verify_answer(render(report, "md"), report.calls)
    assert result.status == "verified", result.mismatches


def test_write_report(conn: Connection, tmp_path: Path) -> None:
    paths = write_report(build_report(conn), tmp_path)
    assert [p.name for p in paths] == [
        "nachbestellung-2026-06-30.md",
        "nachbestellung-2026-06-30.html",
    ]
    html = paths[1].read_text(encoding="utf-8")
    assert "<td>Kabelbinder A</td>" in html
