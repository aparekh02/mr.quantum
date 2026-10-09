"""trainer.lab.SimulatedLab: upstream RoutineRunner wired to the simulator."""

import time
from pathlib import Path

import pytest

from stanza.drivers.simulator import Simulator
from tests.trainer.conftest import DQD_YAML, SINGLE_CHANNEL_YAML
from trainer.lab import SimulatedLab
from trainer.models.client import LocalModelsClient


def test_lab_builds_runner_with_simulator_and_models(tmp_path: Path) -> None:
    lab = SimulatedLab.from_yaml(DQD_YAML, base_dir=tmp_path)
    assert isinstance(lab.simulator, Simulator)
    assert isinstance(lab.runner.resources.models_client, LocalModelsClient)
    assert lab.device is lab.runner.resources.device


def test_lab_runs_routines_in_virtual_time(tmp_path: Path) -> None:
    lab = SimulatedLab.from_yaml(SINGLE_CHANNEL_YAML, base_dir=tmp_path)
    lab.runner.results.store(
        "leakage_test", {"max_safe_voltage_bound": 1.5, "min_safe_voltage_bound": -1.5}
    )
    start = time.perf_counter()
    lab.run("noise_floor_measurement")
    lab.run("global_accumulation")
    assert time.perf_counter() - start < 30
    assert lab.simulator.clock.now() > 0


def test_lab_records_every_run(tmp_path: Path) -> None:
    lab = SimulatedLab.from_yaml(SINGLE_CHANNEL_YAML, base_dir=tmp_path)
    lab.run("noise_floor_measurement", num_points=10)
    assert [r.routine for r in lab.history] == ["noise_floor_measurement"]
    assert lab.history[0].group is None
    assert lab.history[0].ok


def test_failed_run_is_recorded_and_raised(tmp_path: Path) -> None:
    lab = SimulatedLab.from_yaml(SINGLE_CHANNEL_YAML, base_dir=tmp_path)
    with pytest.raises(RuntimeError, match="global_accumulation"):
        lab.run("global_accumulation")  # needs leakage_test results first
    assert not lab.history[-1].ok
    assert "global_accumulation" in (lab.history[-1].error or "")


def test_grouped_run_then_clear_group(tmp_path: Path) -> None:
    lab = SimulatedLab.from_yaml(DQD_YAML, base_dir=tmp_path)
    lab.run("noise_floor_measurement", measure_electrode="OUT_B", group="side_B")
    assert lab.runner.resources.get("group") is not None
    assert "noise_floor_measurement_side_B" in lab.runner.results.list_results()
    lab.clear_group()
    assert lab.runner.resources.get("group") is None


def test_alias_group_results(tmp_path: Path) -> None:
    lab = SimulatedLab.from_yaml(DQD_YAML, base_dir=tmp_path)
    lab.run("noise_floor_measurement", measure_electrode="OUT_A", group="side_A")
    aliased = lab.alias_group_results("side_A")
    assert aliased == ["noise_floor_measurement"]
    assert (
        lab.runner.results["noise_floor_measurement"]
        == lab.runner.results["noise_floor_measurement_side_A"]
    )


def test_settling_sleeps_take_no_wall_time(tmp_path: Path) -> None:
    lab = SimulatedLab.from_yaml(DQD_YAML, base_dir=tmp_path)
    start = time.perf_counter()
    lab.device.jump({"PA1": -1.0}, wait_for_settling=True)  # outside a routine
    with lab.virtual_time():
        lab.device.jump({"PA1": 0.0}, wait_for_settling=True)
    assert time.perf_counter() - start < 0.5
