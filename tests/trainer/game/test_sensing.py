"""Shared judge helper: how sensitive is a charge sensor at its present state."""

from pathlib import Path

import pytest

from tests.trainer.conftest import DQD_YAML
from trainer.game.sensing import sensor_flank
from trainer.lab import SimulatedLab


@pytest.fixture
def lab(tmp_path: Path) -> SimulatedLab:
    lab = SimulatedLab.from_yaml(DQD_YAML, base_dir=tmp_path)
    lab.device.jump(
        {
            "RB1": -1.126,
            "RB2": -1.126,
            "BB0": -1.126,
            "BB1": -1.126,
            "IN_B": 0.001,
            "PB": -0.63,
        }
    )
    return lab


def test_reports_accuracy_blockade_and_position(lab: SimulatedLab) -> None:
    flank = sensor_flank(lab, dot="SD", plunger="PB", measure="OUT_B")
    assert 0.0 <= flank.accuracy <= 1.0
    assert 0.0 <= flank.blockade <= 1.0
    assert flank.position in {"flank", "top", "valley"}
    assert flank.best_slope > 0


def test_steepest_point_has_full_accuracy(lab: SimulatedLab) -> None:
    import numpy as np

    sim = lab.simulator
    v = np.arange(-0.65, -0.61, 5e-5)
    i = np.array([sim.ideal_current("OUT_B", {"PB": x}) for x in v])
    lab.device.jump({"PB": float(v[int(np.argmax(np.abs(np.gradient(i, v))))])})
    assert sensor_flank(lab, dot="SD", plunger="PB", measure="OUT_B").accuracy > 0.97


def test_zero_bias_means_zero_accuracy(lab: SimulatedLab) -> None:
    lab.device.jump({"IN_B": 0.0})
    flank = sensor_flank(lab, dot="SD", plunger="PB", measure="OUT_B")
    assert flank.accuracy == 0.0
    assert flank.best_slope == 0.0
