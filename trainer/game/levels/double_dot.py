"""Level 3: tune into a double dot and sit on a triple point."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from trainer.game.level import Evaluation, Level, score
from trainer.workflows import DQD_WITH_SENSOR_TUNEUP, Step

if TYPE_CHECKING:
    from trainer.game.attempt import Attempt

PX, PY, INNER, MEASURE, BIAS = "PA1", "PA2", "BA1", "OUT_A", "IN_A"
MAX_MERGE = 0.5
REGIME_WINDOW = 0.025
LOCAL_WINDOW = 0.02
MIN_CURRENT = 20e-12
MIN_ACCURACY = 0.5
CLICK_TOLERANCE = 0.001


@dataclass(frozen=True)
class DoubleDotLevel(Level):
    @staticmethod
    def _both_dots_change(sim: Any, x0: float, y0: float) -> bool:
        """Physical double-dot regime: within the window around (PA1, PA2), each dot
        gains or loses charge, i.e. the honeycomb's two families of lines pass by."""
        offsets = np.linspace(-REGIME_WINDOW, REGIME_WINDOW, 9)
        seen: dict[str, set[int]] = {"D1": set(), "D2": set()}
        for dx in offsets:
            for dy in offsets:
                occ = sim.occupations_at({PX: x0 + float(dx), PY: y0 + float(dy)})
                for dot in seen:
                    seen[dot].add(round(occ[dot]))
        return all(len(states) > 1 for states in seen.values())

    def judge(self, attempt: Attempt) -> Evaluation:
        sim = attempt.lab.simulator
        x0, y0 = float(sim.state[PX]), float(sim.state[PY])

        def grid(half: float, n: int) -> np.ndarray:
            xs, ys = (
                np.linspace(x0 - half, x0 + half, n),
                np.linspace(y0 - half, y0 + half, n),
            )
            return np.array(
                [
                    [
                        sim.ideal_current(MEASURE, {PX: float(x), PY: float(y)})
                        for x in xs
                    ]
                    for y in ys
                ]
            )

        biased = abs(sim.state.get(BIAS, 0.0)) > 1e-6
        merge = sim.gate_turn_on(INNER) ** 4
        separate = merge < MAX_MERGE
        local = grid(LOCAL_WINDOW, 41)
        i_max = float(np.max(local))
        # "On a triple point" = within one map pixel (~1 mV) of one: triple points
        # are narrower than any map a student measures, so judge the neighbourhood.
        near = np.linspace(-CLICK_TOLERANCE, CLICK_TOLERANCE, 5)
        i_here = max(
            sim.ideal_current(MEASURE, {PX: x0 + float(dx), PY: y0 + float(dy)})
            for dx in near
            for dy in near
        )
        accuracy = max(0.0, min(1.0, i_here / i_max)) if i_max > 0 else 0.0
        visible = i_max > MIN_CURRENT
        is_dqd = visible and separate and self._both_dots_change(sim, x0, y0)

        feedback: list[str] = []
        if not biased:
            feedback.append(
                f"There is no source-drain bias on {BIAS}, so no current can flow."
            )
        if not separate:
            feedback.append(
                f"The inner barrier {INNER} is too open: the two dots merge into one big dot "
                "and the honeycomb collapses into parallel lines. Close it a little."
            )
        if biased and separate and not visible:
            feedback.append(
                "Almost no current flows anywhere near here: the dots are pinched off from "
                "the leads, or the plungers are far from any transition."
            )
        if biased and separate and visible and not is_dqd:
            feedback.append(
                "The charge-stability diagram around this point is not a double-dot "
                "honeycomb. Search the barrier settings and plunger windows."
            )
        if biased and separate and is_dqd and accuracy < MIN_ACCURACY:
            feedback.append(
                f"You are in a double-dot region, but not on a triple point ({accuracy:.0%} "
                "of the brightest one nearby). Transport only flows where three charge "
                "states meet: click a bright spot on the map."
            )

        success = biased and separate and is_dqd and accuracy >= MIN_ACCURACY
        if success:
            feedback.append(
                f"You are on a triple point of a double dot ({accuracy:.0%} of the brightest "
                "one nearby)."
            )
        measurements = attempt.measurements
        return Evaluation(
            success=success,
            accuracy=round(accuracy, 4) if success else 0.0,
            score=score(accuracy, measurements, self.measurement_budget)
            if success
            else 0,
            measurements=measurements,
            feedback=feedback,
        )


_SETUP_SIDE_A = (
    *(s for s in DQD_WITH_SENSOR_TUNEUP if s.label.startswith("side_A/")),
    Step("", label="ungroup", before="clear_group"),
    Step("", label="alias side_A results", before="alias:side_A"),
)

DOUBLE_DOT = DoubleDotLevel(
    id="double-dot",
    order=3,
    title="Find the double dot",
    concept=(
        "Two coupled quantum dots: each plunger mostly sets the charge on its own dot, "
        "and the mutual charging energy between them turns the charge-stability "
        "diagram into a honeycomb. In transport, current flows only at the triple "
        "points where three charge states meet. The inner barrier sets the interdot "
        "coupling: too open, and the two dots merge into one."
    ),
    objective=(
        "Side A has been health-checked. Tune the barriers and plungers into a double-dot "
        "regime, put PA1 and PA2 on a triple point (with bias on IN_A), and submit."
    ),
    device="dqd_with_sensor",
    hints=(
        "A double dot needs the inner barrier BA1 partly closed, so the dots stay "
        "separate, and the outer barriers BA0 and BA2 open enough to exchange holes with "
        "the leads.",
        'run_dqd_search tries barrier settings for you: gates ["RA1","BA0","PA1","BA1",'
        '"PA2","BA2","RA2"], measure_electrode OUT_A, min_search_scale 0.0005, '
        "max_search_scale 0.001, current_trace_points 128, outer_barrier_points 3, "
        "inner_barrier_points 3, num_dqds_for_exit 1.",
        "It leaves the barriers where it found the double dot and shows the square it "
        "measured on the map. Click one of the bright triple points on it.",
    ),
    measurement_budget=40000,
    setup=_SETUP_SIDE_A,
)
