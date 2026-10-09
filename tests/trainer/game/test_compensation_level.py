"""Level 2, "Compensate the sensor": cross-capacitance, measured and cancelled."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from trainer.game.attempt import Attempt
from trainer.game.levels import get_level

DEVICES = Path(__file__).resolve().parents[3] / "trainer" / "devices"
COMPENSATION = {
    "peak_spacing": 0.02,
    "control_group_name": "side_A",
    "measure_electrode": "OUT_B",
    "bias_gate": "IN_B",
    "bias_voltage": 0.001,
    "settling_time_s": 0.0,
    "num_samples_for_averaging": 2,
    "gates_to_compensate": ["PA1"],
    "seed": 3,
}


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Attempt:
    return Attempt.start(
        get_level("compensate-sensor"), DEVICES, tmp_path_factory.mktemp("base")
    )


@pytest.fixture
def attempt(base: Attempt, tmp_path: Path) -> Attempt:
    return Attempt.start(base.level, DEVICES, tmp_path, reuse=base)


def _step_pa1(attempt: Attempt, delta: float) -> None:
    attempt.lab.device.jump({"PA1": attempt.setup_state["PA1"] + delta})


def test_level_metadata() -> None:
    level = get_level("compensate-sensor")
    assert level.order == 2
    assert "cross-capacitance" in level.concept.lower()


def test_setup_parks_the_sensor_on_a_flank(base: Attempt) -> None:
    assert "find_stable_sensor_peak" in base.lab.runner.results.list_results()
    assert base.setup_state["PA1"] == pytest.approx(0.0)


def test_measured_gradient_then_compensated_step_wins(attempt: Attempt) -> None:
    result: dict[str, Any] = attempt.lab.run("run_compensation", **COMPENSATION)
    gradient = result["compensation_gradients"]["PA1"]
    delta = 0.03
    _step_pa1(attempt, delta)
    pb = attempt.setup_state["PB"] + gradient * delta
    attempt.lab.device.jump({"PB": pb})
    evaluation = attempt.submit()
    assert evaluation.success, evaluation.feedback
    assert evaluation.accuracy > 0.8


def test_stepping_without_compensating_is_a_near_miss(attempt: Attempt) -> None:
    _step_pa1(attempt, 0.03)
    evaluation = attempt.submit()
    assert not evaluation.success
    assert any("cross-capacitance" in f for f in evaluation.feedback)


def test_not_stepping_pa1_fails(attempt: Attempt) -> None:
    evaluation = attempt.submit()
    assert not evaluation.success
    assert any("PA1" in f for f in evaluation.feedback)


def test_a_different_coulomb_peak_does_not_count(attempt: Attempt) -> None:
    # Re-parking one whole peak away keeps the flank sensitivity but is not the
    # same operating point: that is not compensation.
    result = attempt.lab.runner.results["find_stable_sensor_peak"]
    spacing = result["next_peak_voltage"] - result["best_peak_voltage"]
    gradient = -0.1  # roughly right, from the hints
    _step_pa1(attempt, 0.03)
    attempt.lab.device.jump(
        {"PB": attempt.setup_state["PB"] + gradient * 0.03 + spacing}
    )
    evaluation = attempt.submit()
    assert not evaluation.success
    assert any("different Coulomb peak" in f for f in evaluation.feedback)


def test_random_compensation_guesses_do_not_reliably_win(
    base: Attempt, tmp_path: Path
) -> None:
    rng = np.random.default_rng(11)
    wins = 0
    for k in range(40):
        a = Attempt.start(base.level, DEVICES, tmp_path / f"g{k}", reuse=base)
        _step_pa1(a, 0.03)
        a.lab.device.jump({"PB": a.setup_state["PB"] + float(rng.uniform(-0.02, 0.02))})
        wins += a.submit().success
    assert wins / 40 <= 0.15
