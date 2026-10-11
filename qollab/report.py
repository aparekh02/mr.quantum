"""Plain-text report for the Qollab console: tables, bars, and what it means."""

from __future__ import annotations

BAR = 24


def heading(title: str) -> str:
    return f"\n== {title} " + "=" * max(3, 60 - len(title))


def bar(p: float) -> str:
    filled = max(0, min(BAR, round(p * BAR)))
    return "█" * filled + "·" * (BAR - filled)


def row(cells: list[str], widths: list[int]) -> str:
    return "  ".join(c.rjust(w) for c, w in zip(cells, widths, strict=True))
