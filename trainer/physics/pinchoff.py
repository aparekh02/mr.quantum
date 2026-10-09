"""Pinch-off physics: how gate voltages open a conduction channel.

Each gate above the channel controls a local conductance with a smooth turn-on,
using the tanh form of Darulová et al., Phys. Rev. Applied 13, 054005 (2019), the
same form upstream Stanza fits in ``stanza.analysis.fitting.pinchoff_curve``.
Gates add in series with a contact resistance, and the source-drain bias drives
an ohmic current through the result.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import overload

import numpy as np
from numpy.typing import NDArray

ELECTRON = 1
"""Polarity for n-channel devices: conduction at positive gate voltage."""
HOLE = -1
"""Polarity for p-channel devices: conduction at negative gate voltage."""


@dataclass(frozen=True)
class GateTurnOn:
    """Turn-on parameters for the channel segment under one gate.

    Attributes:
        v_threshold: Gate voltage at which the segment is half open (V).
        width: Voltage scale of the turn-on (V). Must be positive.
        g_max: Conductance of the fully open segment (S). Must be non-negative.
    """

    v_threshold: float
    width: float
    g_max: float

    def __post_init__(self) -> None:
        if self.width <= 0:
            raise ValueError(f"width must be positive, got {self.width}")
        if self.g_max < 0:
            raise ValueError(f"g_max must be non-negative, got {self.g_max}")


def _check_polarity(polarity: int) -> None:
    if polarity not in (ELECTRON, HOLE):
        raise ValueError(f"polarity must be ELECTRON (+1) or HOLE (-1), got {polarity}")


@overload
def turn_on(voltage: float, gate: GateTurnOn, polarity: int) -> float: ...


@overload
def turn_on(
    voltage: NDArray[np.float64], gate: GateTurnOn, polarity: int
) -> NDArray[np.float64]: ...


def turn_on(
    voltage: float | NDArray[np.float64], gate: GateTurnOn, polarity: int
) -> float | NDArray[np.float64]:
    """Fraction of the segment that conducts, in [0, 1]."""
    _check_polarity(polarity)
    x = polarity * (np.asarray(voltage, dtype=np.float64) - gate.v_threshold)
    result = 0.5 * (1.0 + np.tanh(x / gate.width))
    if np.ndim(result) == 0:
        return float(result)
    return np.asarray(result, dtype=np.float64)


def gate_conductance(voltage: float, gate: GateTurnOn, polarity: int) -> float:
    """Conductance of the segment under one gate (S)."""
    return gate.g_max * turn_on(voltage, gate, polarity)


def series_conductance(
    conductances: Iterable[float], series_resistance: float
) -> float:
    """Total conductance of gate segments in series with a contact resistance (S).

    A fully pinched segment (zero conductance) blocks the whole channel.
    """
    if series_resistance < 0:
        raise ValueError(
            f"series_resistance must be non-negative, got {series_resistance}"
        )
    resistance = series_resistance
    for g in conductances:
        if g <= 0:
            return 0.0
        resistance += 1.0 / g
    if resistance == 0:
        raise ValueError("channel is a short: no gates and zero series_resistance")
    return 1.0 / resistance


def channel_current(bias: float, conductance: float) -> float:
    """Ohmic source-drain current (A) for a source-drain bias (V)."""
    return bias * conductance


def noisy(current: float, noise_std: float, rng: np.random.Generator) -> float:
    """Add Gaussian measurement noise with standard deviation ``noise_std`` (A)."""
    if noise_std < 0:
        raise ValueError(f"noise_std must be non-negative, got {noise_std}")
    if noise_std == 0:
        return current
    return current + noise_std * float(rng.standard_normal())
