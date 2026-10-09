"""trainer.workflows: the standard tune-up as data, run step by step."""

from pathlib import Path

import pytest

from tests.trainer.conftest import DQD_YAML, SINGLE_CHANNEL_YAML
from trainer.lab import SimulatedLab
from trainer.workflows import DQD_WITH_SENSOR_TUNEUP, Step, run_steps


def test_labels_are_unique_and_ordered() -> None:
    labels = [s.label for s in DQD_WITH_SENSOR_TUNEUP]
    assert len(labels) == len(set(labels))
    assert labels[0] == "side_B/noise_floor_measurement"
    assert labels[-1] == "run_dqd_search"


def test_every_step_names_a_registered_builtin() -> None:
    import stanza.routines.builtins as builtins

    for step in DQD_WITH_SENSOR_TUNEUP:
        assert step.routine in builtins.__all__


def test_run_steps_stops_after_label(tmp_path: Path) -> None:
    lab = SimulatedLab.from_yaml(DQD_YAML, base_dir=tmp_path)
    results = run_steps(lab, DQD_WITH_SENSOR_TUNEUP, stop_after="side_B/leakage_test")
    assert list(results) == ["side_B/noise_floor_measurement", "side_B/leakage_test"]


def test_run_steps_rejects_unknown_stop_label(tmp_path: Path) -> None:
    lab = SimulatedLab.from_yaml(DQD_YAML, base_dir=tmp_path)
    with pytest.raises(ValueError, match="no step labelled"):
        run_steps(lab, DQD_WITH_SENSOR_TUNEUP, stop_after="nope")


def test_actions_run_before_their_step(tmp_path: Path) -> None:
    lab = SimulatedLab.from_yaml(SINGLE_CHANNEL_YAML, base_dir=tmp_path)
    steps = (
        Step("noise_floor_measurement", {"num_points": 5}, label="a"),
        Step(
            "noise_floor_measurement",
            {"num_points": 5},
            label="b",
            before="clear_group",
        ),
    )
    run_steps(lab, steps)
    assert lab.runner.resources.get("group") is None


def test_alias_action(tmp_path: Path) -> None:
    lab = SimulatedLab.from_yaml(DQD_YAML, base_dir=tmp_path)
    steps = (
        Step(
            "noise_floor_measurement",
            {"measure_electrode": "OUT_A", "num_points": 5, "group": "side_A"},
            label="a",
        ),
        Step(
            "noise_floor_measurement",
            {"measure_electrode": "OUT_A", "num_points": 5},
            label="b",
            before="alias:side_A",
        ),
    )
    run_steps(lab, steps)
    assert "noise_floor_measurement" in lab.runner.results.list_results()


def test_unknown_action_rejected() -> None:
    with pytest.raises(ValueError, match="action"):
        Step("noise_floor_measurement", {}, label="x", before="dance")
