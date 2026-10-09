"""Repo-wide pytest fixtures for the trainer project.

Lives at the repo root (not in upstream's tests/conftest.py) so upstream files
stay untouched. Pins one global test seed and re-applies it before every test.
"""

import random
from collections.abc import Iterator

import numpy as np
import pytest

TEST_SEED = 12345


@pytest.fixture(autouse=True)
def _pin_global_seed() -> Iterator[None]:
    """Reset stdlib and legacy numpy global RNG state before each test."""
    random.seed(TEST_SEED)
    np.random.seed(TEST_SEED)
    yield


@pytest.fixture
def test_seed() -> int:
    """The pinned seed, for code that takes an explicit seed argument."""
    return TEST_SEED


@pytest.fixture
def rng() -> np.random.Generator:
    """A fresh generator at the pinned seed, independent per test."""
    return np.random.default_rng(TEST_SEED)
