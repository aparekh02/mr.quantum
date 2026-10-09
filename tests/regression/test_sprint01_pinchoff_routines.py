"""Regression anchor (Sprint 1): pinch-off health checks on the simulated channel.

Upstream's noise_floor_measurement and global_accumulation must keep running,
unmodified, against trainer/devices/single_channel.yaml and give sane physics.
"""

from pathlib import Path

import numpy as np
import pytest

from stanza.routines import RoutineRunner
from stanza.utils import load_device_config
from trainer.routines import register_builtin_routines

DEVICE = (
    Path(__file__).resolve().parents[2] / "trainer" / "devices" / "single_channel.yaml"
)


def test_pinchoff_health_checks_end_to_end(tmp_path: Path) -> None:
    register_builtin_routines()
    runner = RoutineRunner(configs=[load_device_config(DEVICE)], base_dir=tmp_path)

    noise = runner.run("noise_floor_measurement")
    assert abs(noise["current_mean"]) < 4e-11 / np.sqrt(100)
    assert noise["current_std"] == pytest.approx(1e-11, rel=0.25)

    # leakage_test is anchored separately from Sprint 2; supply its upstream shape.
    runner.results.store(
        "leakage_test", {"max_safe_voltage_bound": 1.5, "min_safe_voltage_bound": -1.5}
    )
    turn_on = runner.run("global_accumulation")["global_turn_on_voltage"]
    assert 0.60 < turn_on < 1.0
