"""Sprint 1 done-criterion: upstream routines run unmodified against the simulator."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from stanza.models import DeviceConfig
from stanza.routines import RoutineRunner
from stanza.utils import load_device_config
from tests.trainer.conftest import SINGLE_CHANNEL_YAML

GATES = ["R1", "B1", "P1", "B2", "R2"]
NOISE_STD = 1e-11
HIGHEST_THRESHOLD = 0.60  # B2 in single_channel.yaml
LOWEST_THRESHOLD = 0.35  # R1


@pytest.fixture
def runner(tmp_path: Path) -> RoutineRunner:
    config = load_device_config(SINGLE_CHANNEL_YAML)
    return RoutineRunner(configs=[config], base_dir=tmp_path)


def test_noise_floor_measurement_runs_unmodified(runner: RoutineRunner) -> None:
    result = runner.run("noise_floor_measurement")
    # Every pad is zeroed first, so there is no bias: pure measurement noise.
    assert abs(result["current_mean"]) < 4 * NOISE_STD / np.sqrt(100)
    assert result["current_std"] == pytest.approx(NOISE_STD, rel=0.25)


def test_noise_floor_is_deterministic(tmp_path: Path) -> None:
    config = load_device_config(SINGLE_CHANNEL_YAML)
    a = RoutineRunner(configs=[config], base_dir=tmp_path / "a")
    b = RoutineRunner(configs=[config], base_dir=tmp_path / "b")
    assert a.run("noise_floor_measurement") == b.run("noise_floor_measurement")


def test_global_accumulation_runs_unmodified(runner: RoutineRunner) -> None:
    runner.run("noise_floor_measurement")
    # global_accumulation reads leakage_test's safe bounds. leakage_test itself
    # is a Sprint 2 anchor, so here we supply its result in upstream's own shape.
    runner.results.store(
        "leakage_test",
        {"max_safe_voltage_bound": 1.5, "min_safe_voltage_bound": -1.5},
    )
    result = runner.run("global_accumulation")
    turn_on = result["global_turn_on_voltage"]

    # Sane physics: the channel saturates once the most resistive gate is open,
    # i.e. above the highest threshold and within a few turn-on widths of it.
    assert HIGHEST_THRESHOLD < turn_on < HIGHEST_THRESHOLD + 0.4
    assert turn_on > LOWEST_THRESHOLD

    # The routine leaves every control gate parked at the turn-on voltage.
    device = runner.resources.device
    assert device.check(GATES) == pytest.approx([turn_on] * len(GATES))
    assert device.check("S") == pytest.approx(0.001)


def test_global_accumulation_is_deterministic(tmp_path: Path) -> None:
    config = load_device_config(SINGLE_CHANNEL_YAML)
    values = []
    for name in ("a", "b"):
        r = RoutineRunner(configs=[config], base_dir=tmp_path / name)
        r.run("noise_floor_measurement")
        r.results.store(
            "leakage_test",
            {"max_safe_voltage_bound": 1.5, "min_safe_voltage_bound": -1.5},
        )
        values.append(r.run("global_accumulation")["global_turn_on_voltage"])
    assert values[0] == values[1]


def test_global_accumulation_fails_on_fully_pinched_device(
    tmp_path: Path, single_channel_dict: dict[str, Any]
) -> None:
    # A device that never conducts in the swept range has no turn-on to find:
    # upstream's fit-quality check must reject it rather than invent one.
    sim = single_channel_dict["instruments"][0]["simulation"]
    for params in sim["gates"].values():
        params["v_threshold"] = 5.0
    config = DeviceConfig.model_validate(single_channel_dict)
    r = RoutineRunner(configs=[config], base_dir=tmp_path)
    r.run("noise_floor_measurement")
    r.results.store(
        "leakage_test", {"max_safe_voltage_bound": 1.5, "min_safe_voltage_bound": -1.5}
    )
    with pytest.raises(RuntimeError, match="global_accumulation"):
        r.run("global_accumulation")
