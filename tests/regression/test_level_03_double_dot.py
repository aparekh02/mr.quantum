"""Regression (Sprint 7): Level 3 "Find the double dot", played headlessly.

Search with upstream's run_dqd_search, map the square it found with a charge
stability diagram, pick the brightest triple point, submit.
"""

from pathlib import Path

import numpy as np

from trainer.game.attempt import Attempt
from trainer.game.levels import get_level

DEVICES = Path(__file__).resolve().parents[2] / "trainer" / "devices"
SIDE_A = ["RA1", "BA0", "PA1", "BA1", "PA2", "BA2", "RA2"]


def test_level_03_played_start_to_finish(tmp_path: Path) -> None:
    attempt = Attempt.start(get_level("double-dot"), DEVICES, tmp_path)
    lab = attempt.lab
    search = lab.run(
        "run_dqd_search",
        gates=SIDE_A,
        measure_electrode="OUT_A",
        min_search_scale=0.0005,
        max_search_scale=0.001,
        current_trace_points=128,
        outer_barrier_points=3,
        inner_barrier_points=3,
        num_dqds_for_exit=1,
    )
    square = next(sq for sw in search["run_dqd_search"] for sq in sw["dqd_squares"])
    voltages = np.array(square["high_res_csd_voltages"]).reshape(48, 48, len(SIDE_A))
    xs, ys = voltages[0, :, SIDE_A.index("PA1")], voltages[:, 0, SIDE_A.index("PA2")]
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
    lab.device.jump({"PA1": csd["x"][i], "PA2": csd["y"][j]})
    evaluation = attempt.submit()
    assert evaluation.success, evaluation.feedback
    assert evaluation.score > 500


def test_level_03_not_won_by_doing_nothing(tmp_path: Path) -> None:
    attempt = Attempt.start(get_level("double-dot"), DEVICES, tmp_path)
    assert not attempt.submit().success
