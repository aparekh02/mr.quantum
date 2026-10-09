"""Level 2: cancel a control gate's cross-capacitance on the charge sensor."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from trainer.game.level import Evaluation, Level, score
from trainer.game.sensing import sensor_flank
from trainer.workflows import DQD_WITH_SENSOR_TUNEUP, Step

if TYPE_CHECKING:
    from trainer.game.attempt import Attempt

SENSOR_DOT, PLUNGER, MEASURE, BIAS = "SD", "PB", "OUT_B", "IN_B"
CONTROL = "PA1"
MIN_STEP = 0.025
MIN_BLOCKADE = 0.6
MIN_ACCURACY = 0.7


def _peak_index(attempt: Attempt) -> int:
    """Which Coulomb peak the sensor sits on: floor of its induced charge."""
    return math.floor(attempt.lab.simulator.induced_charges()[SENSOR_DOT])


@dataclass(frozen=True)
class CompensationLevel(Level):
    def baseline(self, attempt: Attempt) -> dict[str, Any]:
        return {"peak_index": _peak_index(attempt)}

    def judge(self, attempt: Attempt) -> Evaluation:
        sim = attempt.lab.simulator
        step = sim.state[CONTROL] - attempt.setup_state[CONTROL]
        flank = sensor_flank(
            attempt.lab, dot=SENSOR_DOT, plunger=PLUNGER, measure=MEASURE
        )
        biased = abs(sim.state.get(BIAS, 0.0)) > 1e-6
        same_peak = _peak_index(attempt) == attempt.baseline["peak_index"]
        feedback: list[str] = []

        if step < MIN_STEP:
            feedback.append(
                f"Step {CONTROL} up by at least {MIN_STEP * 1000:.0f} mV from where it "
                f"started (it moved {step * 1000:+.1f} mV); that is the change to compensate."
            )
        if not biased:
            feedback.append(f"There is no source-drain bias on {BIAS}.")
        if flank.blockade < MIN_BLOCKADE:
            feedback.append("The sensor dot is too open for Coulomb blockade.")
        if step >= MIN_STEP and biased and flank.blockade >= MIN_BLOCKADE:
            if flank.accuracy < MIN_ACCURACY:
                feedback.append(
                    f"The sensor fell off its flank ({flank.accuracy:.0%} of the best "
                    f"sensitivity): {CONTROL}'s cross-capacitance moved the Coulomb peak. "
                    f"Measure the gradient with run_compensation, then move {PLUNGER} by "
                    f"gradient × Δ{CONTROL}."
                )
            elif not same_peak:
                feedback.append(
                    "The sensor is on a flank, but of a different Coulomb peak than the one "
                    "you started on: compensation keeps the same operating point."
                )

        success = (
            step >= MIN_STEP
            and biased
            and flank.blockade >= MIN_BLOCKADE
            and flank.accuracy >= MIN_ACCURACY
            and same_peak
        )
        if success:
            feedback.append(
                f"{CONTROL} moved {step * 1000:+.0f} mV and the sensor stayed on its flank "
                f"({flank.accuracy:.0%} of the best sensitivity)."
            )
        measurements = attempt.measurements
        return Evaluation(
            success=success,
            accuracy=round(flank.accuracy, 4) if success else 0.0,
            score=score(flank.accuracy, measurements, self.measurement_budget)
            if success
            else 0,
            measurements=measurements,
            feedback=feedback,
        )


_SETUP_SENSOR = (
    *(
        s
        for s in DQD_WITH_SENSOR_TUNEUP
        if s.label.startswith("side_B/") or s.routine == "find_stable_sensor_peak"
    ),
    # Upstream leaves the last group filter in place; the player's routines target
    # side A, so clear it (DECISIONS.md R-3).
    Step("", label="ungroup", before="clear_group"),
)

COMPENSATE_SENSOR = CompensationLevel(
    id="compensate-sensor",
    order=2,
    title="Compensate the sensor",
    concept=(
        "Cross-capacitance: every gate couples to every dot, not just the one under it. "
        "Moving a control-side gate shifts the charge sensor's Coulomb peak by a fixed "
        "fraction of the change (the ratio of lever arms), which can push the sensor off "
        "its sensitive flank. Measuring that ratio and moving the sensor plunger to "
        "cancel it is called compensation."
    ),
    objective=(
        "The sensor is parked on a Coulomb peak flank. Step PA1 up by at least 25 mV, "
        "then adjust PB so the sensor is back on the steep flank of the same peak, and "
        "submit."
    ),
    device="dqd_with_sensor",
    hints=(
        "Try stepping PA1 and re-measuring the sensor: the Coulomb peak moves in PB even "
        "though you never touched PB. That shift is linear in the PA1 change.",
        "run_compensation measures the shift per volt: peak_spacing 0.02, "
        "control_group_name side_A, measure_electrode OUT_B, bias_gate IN_B, "
        "bias_voltage 0.001, settling_time_s 0, num_samples_for_averaging 2, "
        'gates_to_compensate ["PA1"].',
        "Its compensation_gradients[PA1] is ΔPB/ΔPA1. After stepping PA1 by ΔV, set "
        "PB to its starting value + gradient × ΔV.",
    ),
    measurement_budget=12000,
    setup=_SETUP_SENSOR,
)
