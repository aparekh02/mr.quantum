"""Gate leakage: unwanted conduction between gates, or from a gate to ground.

Leakage through a damaged gate oxide typically sets in above a voltage difference
and then grows roughly linearly, so each link conducts
``sign(dV) * max(0, |dV| - onset) / resistance``. Only configured links leak.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

GROUND = "ground"
"""Pseudo-gate name for a link to ground."""


@dataclass(frozen=True)
class LeakageLink:
    """A leakage path between gate ``a`` and gate ``b`` (or :data:`GROUND`)."""

    a: str
    b: str
    resistance: float
    onset: float = 0.0

    def __post_init__(self) -> None:
        if self.resistance <= 0:
            raise ValueError(f"resistance must be positive, got {self.resistance}")
        if self.onset < 0:
            raise ValueError(f"onset must be non-negative, got {self.onset}")
        if self.a == self.b:
            raise ValueError(f"a leakage link cannot connect {self.a} to itself")


def _link_current(dv: float, link: LeakageLink) -> float:
    excess = max(0.0, abs(dv) - link.onset)
    return (excess if dv >= 0 else -excess) / link.resistance


def leakage_currents(
    voltages: Mapping[str, float], links: Iterable[LeakageLink]
) -> dict[str, float]:
    """Current flowing out of each gate through the leakage links (A)."""
    currents: dict[str, float] = {}
    for link in links:
        v_a = voltages.get(link.a, 0.0)
        v_b = 0.0 if link.b == GROUND else voltages.get(link.b, 0.0)
        i = _link_current(v_a - v_b, link)
        currents[link.a] = currents.get(link.a, 0.0) + i
        if link.b != GROUND:
            currents[link.b] = currents.get(link.b, 0.0) - i
    return currents
