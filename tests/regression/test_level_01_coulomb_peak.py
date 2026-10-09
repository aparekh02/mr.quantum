"""Regression (Sprint 6): Level 1 "Find the Coulomb peak", played headlessly.

Start the level, run upstream's find_sensor_peak as a student would, submit: it
must succeed with a high score. Submitting without playing must not.
"""

from pathlib import Path

from trainer.game.attempt import Attempt
from trainer.game.levels import get_level

DEVICES = Path(__file__).resolve().parents[2] / "trainer" / "devices"
SENSOR = {
    "peak_spacing": 0.02,
    "sensor_group_name": "side_B",
    "sensor_plunger_gate": "PB",
    "measure_electrode": "OUT_B",
    "bias_gate": "IN_B",
    "bias_voltage": 0.001,
    "settling_time_s": 0.0,
}


def test_level_01_played_start_to_finish(tmp_path: Path) -> None:
    attempt = Attempt.start(get_level("coulomb-peak"), DEVICES, tmp_path / "play")
    assert attempt.next_hint()
    attempt.lab.run("find_sensor_peak", **SENSOR)
    result = attempt.submit()
    assert result.success, result.feedback
    assert result.accuracy > 0.8
    assert result.score > 700


def test_level_01_not_won_by_doing_nothing(tmp_path: Path) -> None:
    attempt = Attempt.start(get_level("coulomb-peak"), DEVICES, tmp_path / "idle")
    assert not attempt.submit().success
