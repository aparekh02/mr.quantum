"""Level 1: find the Coulomb peak and park the charge sensor on its flank."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from trainer.game.level import Evaluation, Level, score
from trainer.game.sensing import sensor_flank
from trainer.workflows import DQD_WITH_SENSOR_TUNEUP

if TYPE_CHECKING:
    from trainer.game.attempt import Attempt

SENSOR_DOT = "SD"
PLUNGER = "PB"
MEASURE = "OUT_B"
BIAS = "IN_B"

MIN_BLOCKADE = 0.6
"""1 - openness of the sensor dot: below this it is an open wire, not a dot."""
MIN_ACCURACY = 0.7
"""Sensitivity relative to the best flank nearby needed to pass."""


@dataclass(frozen=True)
class CoulombPeakLevel(Level):
    def judge(self, attempt: Attempt) -> Evaluation:
        sim = attempt.lab.simulator
        flank = sensor_flank(
            attempt.lab, dot=SENSOR_DOT, plunger=PLUNGER, measure=MEASURE
        )
        accuracy, blockade = flank.accuracy, flank.blockade

        feedback: list[str] = []
        biased = abs(sim.state.get(BIAS, 0.0)) > 1e-6
        if not biased:
            feedback.append(
                f"There is no source-drain bias on {BIAS}, so no current can flow "
                "through the sensor dot."
            )
        if blockade < MIN_BLOCKADE:
            feedback.append(
                "The sensor dot has not formed: its barriers and plunger are too open "
                "for Coulomb blockade, so there are no Coulomb peaks here."
            )
        if biased and blockade >= MIN_BLOCKADE and accuracy < MIN_ACCURACY:
            if flank.position == "top":
                feedback.append(
                    "You are at the top of a peak: the current is flat there, so it "
                    "barely responds to nearby charges. Move onto its steep side."
                )
            elif flank.position == "valley":
                feedback.append(
                    "You are in a blockade valley: no transition is aligned with the "
                    "leads, so almost no current flows. Move onto a peak's flank."
                )
            else:
                feedback.append(
                    f"Close: you are on a flank, but at {accuracy:.0%} of the best "
                    "sensitivity nearby. Find the steepest point."
                )

        success = biased and blockade >= MIN_BLOCKADE and accuracy >= MIN_ACCURACY
        if success:
            feedback.append(
                f"The sensor sits on a Coulomb peak's flank at {accuracy:.0%} of the best "
                "sensitivity nearby."
            )
        measurements = attempt.measurements
        points = (
            score(accuracy, measurements, self.measurement_budget) if success else 0
        )
        return Evaluation(
            success=success,
            accuracy=round(accuracy, 4) if biased and blockade >= MIN_BLOCKADE else 0.0,
            score=points,
            measurements=measurements,
            feedback=feedback,
        )


COULOMB_PEAK = CoulombPeakLevel(
    id="coulomb-peak",
    order=1,
    title="Find the Coulomb peak",
    concept=(
        "Coulomb blockade: a quantum dot only conducts when one of its charge "
        "transitions lines up with the leads. Sweeping its plunger gate gives a "
        "series of sharp, evenly spaced current peaks with blockaded valleys in "
        "between. On the steep flank of a peak the current is most sensitive to "
        "nearby charges, which is where a charge sensor is parked."
    ),
    objective=(
        "The sensor side (side_B) has been health-checked. Find a Coulomb peak of "
        "the sensor dot and leave the sensor plunger PB on its steepest flank, with "
        "bias on IN_B, then submit."
    ),
    device="dqd_with_sensor",
    hints=(
        "Coulomb peaks of the sensor appear when its plunger PB is near pinch-off: "
        "between the saturation and cutoff voltages finger_gate_characterization "
        "found for PB.",
        "find_sensor_peak automates the search. Try peak_spacing 0.02, "
        "sensor_group_name side_B, sensor_plunger_gate PB, measure_electrode OUT_B, "
        "bias_gate IN_B, bias_voltage 0.001, settling_time_s 0.",
        "The top of a peak is flat. A sensor works on the side of a peak, where dI/dV "
        "is largest; find_sensor_peak leaves PB there.",
    ),
    measurement_budget=2500,
    setup=tuple(s for s in DQD_WITH_SENSOR_TUNEUP if s.label.startswith("side_B/")),
)
