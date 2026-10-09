"""Level 3, "Find the double dot": tune into the honeycomb, sit on a triple point."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from trainer.game.attempt import Attempt
from trainer.game.levels import get_level

DEVICES = Path(__file__).resolve().parents[3] / "trainer" / "devices"
SIDE_A = ["RA1", "BA0", "PA1", "BA1", "PA2", "BA2", "RA2"]
DQD_SEARCH = {
    "gates": SIDE_A,
    "measure_electrode": "OUT_A",
    "min_search_scale": 0.0005,
    "max_search_scale": 0.001,
    "current_trace_points": 128,
    "outer_barrier_points": 3,
    "inner_barrier_points": 3,
    "num_dqds_for_exit": 1,
}


@pytest.fixture(scope="module")
def searched(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Attempt, dict[str, Any]]:
    a = Attempt.start(get_level("double-dot"), DEVICES, tmp_path_factory.mktemp("dqd"))
    return a, a.lab.run("run_dqd_search", **DQD_SEARCH)


def _fresh(searched: tuple[Attempt, dict[str, Any]], tmp_path: Path) -> Attempt:
    base, _ = searched
    a = Attempt.start(base.level, DEVICES, tmp_path, reuse=base)
    a.lab.device.jump(
        dict(base.lab.simulator.state)
    )  # where the search left the device
    return a


def _square(searched: tuple[Attempt, dict[str, Any]]) -> np.ndarray:
    _, result = searched
    square = next(sq for sw in result["run_dqd_search"] for sq in sw["dqd_squares"])
    return np.array(square["high_res_csd_voltages"]).reshape(48, 48, len(SIDE_A))


def _triple_point(attempt: Attempt, square: np.ndarray) -> dict[str, float]:
    """Brightest transport point of the found square, from a student's own map."""
    lab = attempt.lab
    lab.device.jump(dict(zip(SIDE_A, square[24, 24].tolist(), strict=True)))
    xs = square[0, :, SIDE_A.index("PA1")]
    ys = square[:, 0, SIDE_A.index("PA2")]
    csd = lab.run(
        "charge_stability_diagram",
        gate_x="PA1",
        gate_y="PA2",
        x_range=[float(xs[0]), float(xs[-1])],
        y_range=[float(ys[0]), float(ys[-1])],
        points=60,
        measure_electrode="OUT_A",
    )
    current = np.array(csd["current"])
    j, i = np.unravel_index(int(np.argmax(current)), current.shape)
    return {"PA1": csd["x"][i], "PA2": csd["y"][j]}


def test_level_metadata() -> None:
    level = get_level("double-dot")
    assert level.order == 3
    assert "honeycomb" in level.concept.lower()
    assert "triple point" in level.concept.lower()


def test_search_then_triple_point_wins(
    searched: tuple[Attempt, dict[str, Any]], tmp_path: Path
) -> None:
    attempt = _fresh(searched, tmp_path)
    attempt.lab.device.jump(_triple_point(attempt, _square(searched)))
    evaluation = attempt.submit()
    assert evaluation.success, evaluation.feedback
    assert evaluation.accuracy >= 0.5


def test_found_region_but_not_on_a_triple_point_is_a_near_miss(
    searched: tuple[Attempt, dict[str, Any]], tmp_path: Path
) -> None:
    attempt = _fresh(searched, tmp_path)
    best = _triple_point(attempt, _square(searched))
    # Inside the honeycomb but in the middle of a charge plateau: no transport.
    attempt.lab.device.jump({"PA1": best["PA1"] + 0.009, "PA2": best["PA2"] + 0.009})
    evaluation = attempt.submit()
    if evaluation.success:  # pragma: no cover - only if we landed on another one
        pytest.fail("a plateau point should not count as a triple point")
    assert any("triple point" in f for f in evaluation.feedback)


def test_merged_dots_fail(
    searched: tuple[Attempt, dict[str, Any]], tmp_path: Path
) -> None:
    attempt = _fresh(searched, tmp_path)
    attempt.lab.device.jump(_triple_point(attempt, _square(searched)))
    attempt.lab.device.jump({"BA1": -1.6})  # open the inner barrier
    evaluation = attempt.submit()
    assert not evaluation.success
    assert any("inner barrier" in f for f in evaluation.feedback)


def test_doing_nothing_fails(tmp_path: Path) -> None:
    attempt = Attempt.start(get_level("double-dot"), DEVICES, tmp_path)
    assert not attempt.submit().success


def test_no_bias_fails(
    searched: tuple[Attempt, dict[str, Any]], tmp_path: Path
) -> None:
    attempt = _fresh(searched, tmp_path)
    attempt.lab.device.jump(_triple_point(attempt, _square(searched)))
    attempt.lab.device.jump({"IN_A": 0.0})
    evaluation = attempt.submit()
    assert not evaluation.success
    assert any("bias" in f for f in evaluation.feedback)


def test_random_plunger_points_do_not_reliably_win(
    searched: tuple[Attempt, dict[str, Any]], tmp_path: Path
) -> None:
    rng = np.random.default_rng(4)
    square = _square(searched)
    xs, ys = square[0, :, SIDE_A.index("PA1")], square[:, 0, SIDE_A.index("PA2")]
    wins = 0
    for k in range(30):
        a = _fresh(searched, tmp_path / f"p{k}")
        a.lab.device.jump(
            {
                "PA1": float(rng.uniform(xs.min(), xs.max())),
                "PA2": float(rng.uniform(ys.min(), ys.max())),
            }
        )
        wins += a.submit().success
    assert wins / 30 <= 0.25
