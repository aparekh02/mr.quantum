"""Shared fixtures for trainer tests: the canonical simulated device configs."""

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from trainer.routines import register_builtin_routines

DEVICES_DIR = Path(__file__).resolve().parents[2] / "trainer" / "devices"
SINGLE_CHANNEL_YAML = DEVICES_DIR / "single_channel.yaml"


@pytest.fixture
def single_channel_dict() -> dict[str, Any]:
    """A fresh, mutable copy of the single-channel device config."""
    data: dict[str, Any] = yaml.safe_load(SINGLE_CHANNEL_YAML.read_text())
    return copy.deepcopy(data)


@pytest.fixture(autouse=True)
def _builtin_routines_registered() -> None:
    """Upstream tests clear the global routine registry; restore the built-ins."""
    register_builtin_routines()
