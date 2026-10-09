"""Trainer measurement routines: thin wrappers over upstream Device methods."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from stanza.routines import clear_routine_registry, get_registered_routines
from tests.trainer.conftest import DQD_YAML
from trainer.api.events import EventLog
from trainer.api.streaming import StreamingDataLogger
from trainer.lab import SimulatedLab
from trainer.routines import register_builtin_routines

CSD = {
    "gate_x": "PA1",
    "gate_y": "PA2",
    "x_range": [-0.66, -0.58],
    "y_range": [-0.66, -0.58],
    "points": 12,
    "measure_electrode": "OUT_A",
}


@pytest.fixture
def lab(tmp_path: Path) -> SimulatedLab:
    lab = SimulatedLab.from_yaml(DQD_YAML, base_dir=tmp_path)
    lab.device.jump(
        {
            "RA1": -1.7,
            "RA2": -1.7,
            "BA0": -0.9,
            "BA1": -0.75,
            "BA2": -0.9,
            "IN_A": 0.001,
        }
    )
    return lab


def test_registered_alongside_the_builtins() -> None:
    clear_routine_registry()
    register_builtin_routines()
    assert "charge_stability_diagram" in get_registered_routines()


def test_returns_a_grid_matching_the_device(lab: SimulatedLab) -> None:
    result: dict[str, Any] = lab.run("charge_stability_diagram", **CSD)
    xs, ys = np.array(result["x"]), np.array(result["y"])
    current = np.array(result["current"])
    assert xs.shape == (12,) and ys.shape == (12,)
    assert current.shape == (12, 12)  # rows follow y, columns follow x
    assert xs[0] == pytest.approx(-0.66) and xs[-1] == pytest.approx(-0.58)
    # Spot check one cell against a direct measurement at the same point.
    lab.device.jump({"PA1": float(xs[3]), "PA2": float(ys[7])})
    assert lab.device.measure("OUT_A") == pytest.approx(current[7, 3], abs=2e-11)


def test_streams_every_point_through_the_logger(
    lab: SimulatedLab, tmp_path: Path
) -> None:
    log = EventLog()
    lab.runner.resources.add(
        "logger",
        StreamingDataLogger(routine_name="device", base_dir=tmp_path, events=log),
    )
    lab.run("charge_stability_diagram", **{**CSD, "points": 5})
    points = [e for e in log.since(0) if e.kind == "sweep_point"]
    assert len(points) == 25
    assert all(len(p.data["x"]) == 2 for p in points)
    final = log.since(0)[-1]
    # Upstream labels 2D sweeps [outer, inner]: y is the slow axis, x the fast one.
    assert final.kind == "sweep" and final.data["x_label"] == ["PA2", "PA1"]
    assert points[1].data["x"][0] == points[0].data["x"][0]  # outer (y) held


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"points": 1}, "points"),
        ({"points": 257}, "points"),
        ({"gate_x": "NOPE"}, "NOPE"),
        ({"gate_y": "PA1"}, "different"),
        ({"x_range": [-0.5, -0.5]}, "x_range"),
        ({"y_range": [-0.5]}, "y_range"),
    ],
)
def test_rejects_bad_arguments(
    lab: SimulatedLab, override: dict[str, Any], match: str
) -> None:
    with pytest.raises(RuntimeError, match=match):
        lab.run("charge_stability_diagram", **{**CSD, **override})


def test_descending_ranges_are_allowed(lab: SimulatedLab) -> None:
    result = lab.run(
        "charge_stability_diagram", **{**CSD, "x_range": [-0.58, -0.66], "points": 3}
    )
    assert result["x"][0] > result["x"][-1]
