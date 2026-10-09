"""Regression (Sprint 7): Level 2 "Compensate the sensor", played headlessly."""

from pathlib import Path

from trainer.game.attempt import Attempt
from trainer.game.levels import get_level

DEVICES = Path(__file__).resolve().parents[2] / "trainer" / "devices"


def test_level_02_played_start_to_finish(tmp_path: Path) -> None:
    attempt = Attempt.start(get_level("compensate-sensor"), DEVICES, tmp_path)
    result = attempt.lab.run(
        "run_compensation",
        peak_spacing=0.02,
        control_group_name="side_A",
        measure_electrode="OUT_B",
        bias_gate="IN_B",
        bias_voltage=0.001,
        settling_time_s=0.0,
        num_samples_for_averaging=2,
        gates_to_compensate=["PA1"],
        seed=3,
    )
    gradient = result["compensation_gradients"]["PA1"]
    start = attempt.setup_state
    attempt.lab.device.jump(
        {"PA1": start["PA1"] + 0.03, "PB": start["PB"] + gradient * 0.03}
    )
    evaluation = attempt.submit()
    assert evaluation.success, evaluation.feedback
    assert evaluation.score > 700


def test_level_02_not_won_without_compensating(tmp_path: Path) -> None:
    attempt = Attempt.start(get_level("compensate-sensor"), DEVICES, tmp_path)
    attempt.lab.device.jump({"PA1": attempt.setup_state["PA1"] + 0.03})
    assert not attempt.submit().success
