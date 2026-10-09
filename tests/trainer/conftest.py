"""Shared fixtures for trainer tests: the canonical simulated device configs."""

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from trainer.routines import register_builtin_routines

DEVICES_DIR = Path(__file__).resolve().parents[2] / "trainer" / "devices"
SINGLE_CHANNEL_YAML = DEVICES_DIR / "single_channel.yaml"
DQD_YAML = DEVICES_DIR / "dqd_with_sensor.yaml"


@pytest.fixture
def single_channel_dict() -> dict[str, Any]:
    """A fresh, mutable copy of the single-channel device config."""
    data: dict[str, Any] = yaml.safe_load(SINGLE_CHANNEL_YAML.read_text())
    return copy.deepcopy(data)


@pytest.fixture
def dqd_dict() -> dict[str, Any]:
    """A fresh, mutable copy of the double-dot-with-sensor device config."""
    data: dict[str, Any] = yaml.safe_load(DQD_YAML.read_text())
    return copy.deepcopy(data)


@pytest.fixture
def quiet_dqd_dict(dqd_dict: dict[str, Any]) -> dict[str, Any]:
    """The double-dot device with all noise switched off, for exact physics tests."""
    sim = dqd_dict["instruments"][0]["simulation"]
    sim["noise_std"] = 0.0
    sim.pop("charge_noise", None)
    return dqd_dict


@pytest.fixture(autouse=True)
def _builtin_routines_registered() -> None:
    """Upstream tests clear the global routine registry; restore the built-ins."""
    register_builtin_routines()
