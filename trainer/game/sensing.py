"""Judge helper: how good is a charge sensor's operating point, from ground truth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from trainer.lab import SimulatedLab

SEARCH_WINDOW = 0.03
LOCAL_WINDOW = 0.01
STEP = 5e-5


@dataclass(frozen=True)
class SensorFlank:
    """Sensitivity of the sensor at its present plunger voltage.

    ``accuracy`` is |dI/dV| here relative to the steepest flank within
    ``SEARCH_WINDOW``; ``blockade`` is 1 - openness of the sensor dot.
    """

    accuracy: float
    blockade: float
    position: Literal["flank", "top", "valley"]
    best_slope: float
    slope: float


def sensor_flank(
    lab: SimulatedLab, dot: str, plunger: str, measure: str
) -> SensorFlank:
    sim = lab.simulator
    low, high = lab.device.channel_configs[plunger].voltage_range
    lo = -np.inf if low is None else low
    hi = np.inf if high is None else high
    v0 = float(sim.state[plunger])

    def current(v: float) -> float:
        return sim.ideal_current(measure, {plunger: float(np.clip(v, lo, hi))})

    voltages = np.arange(max(lo, v0 - SEARCH_WINDOW), min(hi, v0 + SEARCH_WINDOW), STEP)
    currents = np.array([current(v) for v in voltages])
    best = (
        float(np.max(np.abs(np.gradient(currents, voltages))))
        if len(voltages) > 2
        else 0.0
    )
    here = abs(current(v0 + STEP) - current(v0 - STEP)) / (2 * STEP)
    accuracy = min(1.0, here / best) if best > 1e-12 else 0.0
    if best <= 1e-12:
        best = 0.0

    local = (voltages >= v0 - LOCAL_WINDOW) & (voltages <= v0 + LOCAL_WINDOW)
    near = currents[local] if local.any() else currents
    position: Literal["flank", "top", "valley"] = "flank"
    if near.size:
        i0, top, bottom = current(v0), float(np.max(near)), float(np.min(near))
        span = top - bottom
        if span > 0 and i0 >= top - 0.15 * span:
            position = "top"
        elif span > 0 and i0 <= bottom + 0.2 * span:
            position = "valley"
    return SensorFlank(
        accuracy=accuracy,
        blockade=1.0 - sim.dot_openness(dot),
        position=position,
        best_slope=best,
        slope=here,
    )
