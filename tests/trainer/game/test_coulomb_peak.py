"""Level 1, "Find the Coulomb peak": correct play wins, near-misses and
degenerate strategies do not."""

from pathlib import Path

import numpy as np
import pytest

from trainer.game.attempt import Attempt, AttemptClosed
from trainer.game.levels import LEVELS, get_level

DEVICES = Path(__file__).resolve().parents[3] / "trainer" / "devices"
SENSOR = {
    "peak_spacing": 0.02,
    "sensor_group_name": "side_B",
    "sensor_plunger_gate": "PB",
    "measure_electrode": "OUT_B",
    "bias_gate": "IN_B",
    "bias_voltage": 0.001,
    "settling_time_s": 0.0,
}


@pytest.fixture
def attempt(tmp_path: Path) -> Attempt:
    a = Attempt.start(get_level("coulomb-peak"), DEVICES, tmp_path)
    return a


def test_level_is_registered_and_states_its_concept() -> None:
    level = get_level("coulomb-peak")
    assert level in LEVELS
    assert level.order == 1
    assert "Coulomb blockade" in level.concept
    assert level.device == "dqd_with_sensor"


def test_setup_runs_the_prerequisite_health_checks(attempt: Attempt) -> None:
    results = attempt.lab.runner.results.list_results()
    assert "global_accumulation_side_B" in results
    assert "finger_gate_characterization_side_B" in results
    assert attempt.measurements == 0  # setup readings don't count against the player


def test_find_sensor_peak_then_submit_wins(attempt: Attempt) -> None:
    attempt.lab.run(
        "find_stable_sensor_peak", **SENSOR, top_n_peaks=3, hold_time_seconds=1.0
    )
    result = attempt.submit()
    assert result.success, result.feedback
    assert result.accuracy > 0.8
    assert result.score > 500
    assert result.measurements > 0


def test_plain_find_sensor_peak_also_wins(attempt: Attempt) -> None:
    attempt.lab.run("find_sensor_peak", **SENSOR)
    assert attempt.submit().success


# --- near misses ------------------------------------------------------------


def _found_peak(attempt: Attempt) -> dict[str, float]:
    result: dict[str, float] = attempt.lab.run("find_sensor_peak", **SENSOR)
    return result


def test_peak_centre_is_a_near_miss(attempt: Attempt) -> None:
    peak = _found_peak(attempt)
    attempt.lab.device.jump({"PB": peak["best_peak_voltage"]})
    result = attempt.submit()
    assert not result.success
    assert any("top of a peak" in f for f in result.feedback)


def test_blockade_valley_is_a_near_miss(attempt: Attempt) -> None:
    peak = _found_peak(attempt)
    spacing = peak["next_peak_voltage"] - peak["best_peak_voltage"]
    attempt.lab.device.jump({"PB": peak["best_peak_voltage"] + spacing / 2})
    result = attempt.submit()
    assert not result.success
    assert any("valley" in f for f in result.feedback)


def test_no_bias_is_a_near_miss(attempt: Attempt) -> None:
    _found_peak(attempt)
    attempt.lab.device.jump({"IN_B": 0.0})
    result = attempt.submit()
    assert not result.success
    assert any("bias" in f for f in result.feedback)


def test_open_dot_is_a_near_miss(attempt: Attempt) -> None:
    # A steep slope without blockade (plain pinch-off of an open channel) is not
    # a Coulomb peak, even though the current changes quickly there.
    _found_peak(attempt)
    attempt.lab.device.jump({"BB0": -1.9, "BB1": -1.9, "PB": -0.75})
    result = attempt.submit()
    assert not result.success
    assert any("dot" in f for f in result.feedback)


# --- degenerate strategies -------------------------------------------------


def test_submitting_immediately_fails(attempt: Attempt) -> None:
    assert not attempt.submit().success


def test_maximising_current_fails(attempt: Attempt) -> None:
    attempt.lab.device.jump(
        {"RB1": -2.0, "BB0": -2.0, "PB": -2.0, "BB1": -2.0, "RB2": -2.0, "IN_B": 0.001}
    )
    assert not attempt.submit().success


def test_random_plunger_guesses_do_not_reliably_win(tmp_path: Path) -> None:
    rng = np.random.default_rng(99)
    level = get_level("coulomb-peak")
    base = Attempt.start(level, DEVICES, tmp_path / "base")
    turn_on = base.lab.runner.results["global_accumulation_side_B"][
        "global_turn_on_voltage"
    ]
    wins, scores = 0, []
    for k in range(40):
        a = Attempt.start(level, DEVICES, tmp_path / f"r{k}", reuse=base)
        a.lab.device.jump(
            {
                "RB1": turn_on,
                "BB0": turn_on,
                "BB1": turn_on,
                "RB2": turn_on,
                "IN_B": 0.001,
                "PB": float(rng.uniform(-2.0, 0.3)),
            }
        )
        result = a.submit()
        wins += result.success
        scores.append(result.score)
    assert wins / 40 <= 0.1
    assert float(np.mean(scores)) < 100


# --- attempt mechanics ------------------------------------------------------


def test_hints_are_revealed_in_order(attempt: Attempt) -> None:
    level = attempt.level
    assert attempt.next_hint() == level.hints[0]
    for _ in range(10):
        attempt.next_hint()
    assert attempt.hints_shown == len(level.hints)
    assert attempt.next_hint() is None


def test_measurements_count_only_the_players_readings(attempt: Attempt) -> None:
    attempt.lab.device.measure("OUT_B")
    attempt.lab.device.measure("OUT_B")
    assert attempt.measurements == 2


def test_an_attempt_can_only_be_submitted_once(attempt: Attempt) -> None:
    attempt.submit()
    with pytest.raises(AttemptClosed):
        attempt.submit()
    assert attempt.result is not None


def test_using_more_than_the_budget_lowers_the_score(tmp_path: Path) -> None:
    level = get_level("coulomb-peak")
    lean = Attempt.start(level, DEVICES, tmp_path / "lean")
    lean.lab.run(
        "find_stable_sensor_peak", **SENSOR, top_n_peaks=1, hold_time_seconds=0.2
    )
    wasteful = Attempt.start(level, DEVICES, tmp_path / "wasteful")
    for _ in range(level.measurement_budget * 2):
        wasteful.lab.device.measure("OUT_B")
    wasteful.lab.run(
        "find_stable_sensor_peak", **SENSOR, top_n_peaks=1, hold_time_seconds=0.2
    )
    a, b = lean.submit(), wasteful.submit()
    assert a.success and b.success
    assert b.score < a.score
