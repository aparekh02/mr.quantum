"""Upstream routines must fail, or report trouble, when the physics says so.

A level is only meaningful if the routines (and the local models behind them)
cannot be satisfied by a device that lacks the physics being taught.
"""

from pathlib import Path
from typing import Any

import pytest

from stanza.models import DeviceConfig
from trainer.lab import SimulatedLab
from trainer.workflows import DQD_WITH_SENSOR_TUNEUP, Step, run_steps

SIDE_A_GATES = ["RA1", "BA0", "PA1", "BA1", "PA2", "BA2", "RA2"]


def _lab(config: dict[str, Any], tmp_path: Path) -> SimulatedLab:
    return SimulatedLab(DeviceConfig.model_validate(config), base_dir=tmp_path)


def _steps(prefix: str) -> list[Step]:
    return [s for s in DQD_WITH_SENSOR_TUNEUP if s.label.startswith(prefix)]


def test_sensor_without_a_dot_has_no_coulomb_peak(
    dqd_dict: dict[str, Any], tmp_path: Path
) -> None:
    sim = dqd_dict["instruments"][0]["simulation"]
    sim["channels"][1]["dots"] = []
    del sim["dots"]["SD"]
    sim["mutual"] = [m for m in sim["mutual"] if "SD" not in m["dots"]]
    lab = _lab(dqd_dict, tmp_path)
    run_steps(lab, _steps("side_B/"))
    sensor = next(s for s in DQD_WITH_SENSOR_TUNEUP if s.routine == "find_sensor_peak")
    with pytest.raises(RuntimeError, match="find_sensor_peak"):
        run_steps(lab, [sensor])


def test_leaky_gate_pair_shrinks_the_safe_range(
    dqd_dict: dict[str, Any], tmp_path: Path
) -> None:
    dqd_dict["instruments"][0]["simulation"]["leakage"] = [
        {"gates": ["BA0", "PA1"], "resistance": 2.0e6, "onset": 0.4}
    ]
    lab = _lab(dqd_dict, tmp_path)
    results = run_steps(lab, _steps("side_A/"), stop_after="side_A/leakage_test")
    bounds = results["side_A/leakage_test"]
    # Sweeping BA0 against PA1 by more than ~0.5 V leaks below 50 MOhm.
    assert bounds["min_safe_voltage_bound"] > -2.0
    assert bounds["max_safe_voltage_bound"] == pytest.approx(0.3)
    leak_logged = any(r.routine == "leakage_test" and r.ok for r in lab.history)
    assert leak_logged


def test_merged_dots_are_not_reported_as_a_double_dot(
    dqd_dict: dict[str, Any], tmp_path: Path
) -> None:
    lab = _lab(dqd_dict, tmp_path)
    run_steps(lab, _steps("side_A/"))
    lab.clear_group()
    lab.alias_group_results("side_A")
    merged = {"BA0": -1.116, "BA1": -1.6, "BA2": -1.116}  # inner barrier wide open
    common = {
        "gates": SIDE_A_GATES,
        "measure_electrode": "OUT_A",
        "current_trace_points": 128,
        "barrier_voltages": merged,
    }
    lab.run(
        "compute_peak_spacing",
        min_search_scale=0.0005,
        max_search_scale=0.001,
        **common,
    )
    result = lab.run("run_dqd_search_fixed_barriers", max_samples=12, **common)
    assert result["dqd_squares"] == []
