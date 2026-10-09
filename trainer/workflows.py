"""The standard tune-up, expressed as data over upstream's built-in routines.

Each step is one ``RoutineRunner.run`` call with explicit parameters. Two lab
actions bridge quirks of upstream's group handling (see DECISIONS.md R-3):
``clear_group`` before an ungrouped routine, and ``alias:<group>`` before a routine
that reads unsuffixed health-check results.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from trainer.lab import SimulatedLab


@dataclass(frozen=True)
class Step:
    """One routine invocation in a workflow."""

    routine: str
    params: Mapping[str, Any] = field(default_factory=dict)
    label: str = ""
    before: str | None = None

    def __post_init__(self) -> None:
        if not self.label:
            object.__setattr__(self, "label", self.routine)
        if self.before is not None and not (
            self.before == "clear_group" or self.before.startswith("alias:")
        ):
            raise ValueError(f"unknown action {self.before!r}")


def _apply(lab: SimulatedLab, action: str) -> None:
    if action == "clear_group":
        lab.clear_group()
    else:
        lab.alias_group_results(action.removeprefix("alias:"))


def run_steps(
    lab: SimulatedLab, steps: Sequence[Step], stop_after: str | None = None
) -> dict[str, Any]:
    """Run steps in order; return results keyed by step label."""
    if stop_after is not None and stop_after not in {s.label for s in steps}:
        raise ValueError(f"no step labelled {stop_after!r}")
    results: dict[str, Any] = {}
    for step in steps:
        if step.before is not None:
            _apply(lab, step.before)
        results[step.label] = lab.run(step.routine, **step.params)
        if step.label == stop_after:
            break
    return results


def _health_checks(group: str, measure: str, bias: str) -> tuple[Step, ...]:
    sweep = {
        "measure_electrode": measure,
        "bias_gate": bias,
        "bias_voltage": 0.001,
        "charge_carrier_type": "hole",
        "step_size": 0.01,
        "group": group,
    }
    return (
        Step(
            "noise_floor_measurement",
            {"measure_electrode": measure, "num_points": 100, "group": group},
            label=f"{group}/noise_floor_measurement",
        ),
        Step(
            "leakage_test",
            {
                "leakage_threshold_resistance": 50_000_000,
                "num_points": 10,
                "group": group,
            },
            label=f"{group}/leakage_test",
        ),
        Step("global_accumulation", sweep, label=f"{group}/global_accumulation"),
        Step(
            "reservoir_characterization",
            sweep,
            label=f"{group}/reservoir_characterization",
        ),
        Step(
            "finger_gate_characterization",
            sweep,
            label=f"{group}/finger_gate_characterization",
        ),
    )


_SENSOR = {
    "peak_spacing": 0.02,
    "sensor_group_name": "side_B",
    "sensor_plunger_gate": "PB",
    "measure_electrode": "OUT_B",
    "bias_gate": "IN_B",
    "bias_voltage": 0.001,
    "settling_time_s": 0.0,
}

DQD_WITH_SENSOR_TUNEUP: tuple[Step, ...] = (
    *_health_checks("side_B", "OUT_B", "IN_B"),
    *_health_checks("side_A", "OUT_A", "IN_A"),
    Step("find_sensor_peak", _SENSOR, before="clear_group"),
    Step(
        "find_stable_sensor_peak",
        {**_SENSOR, "top_n_peaks": 3, "hold_time_seconds": 1.0},
    ),
    Step(
        "run_compensation",
        {
            "peak_spacing": 0.02,
            "control_group_name": "side_A",
            "measure_electrode": "OUT_B",
            "bias_gate": "IN_B",
            "bias_voltage": 0.001,
            "settling_time_s": 0.0,
            "num_samples_for_averaging": 2,
            "zero_control_side": True,
            "seed": 7,
        },
    ),
    Step(
        "run_dqd_search",
        {
            "gates": ["RA1", "BA0", "PA1", "BA1", "PA2", "BA2", "RA2"],
            "measure_electrode": "OUT_A",
            "min_search_scale": 0.0005,
            "max_search_scale": 0.001,
            "current_trace_points": 128,
            "outer_barrier_points": 3,
            "inner_barrier_points": 3,
            "num_dqds_for_exit": 1,
        },
        before="alias:side_A",
    ),
)
"""Health checks on both sides, then sensor tune-up, compensation and DQD search,
for ``trainer/devices/dqd_with_sensor.yaml``."""
