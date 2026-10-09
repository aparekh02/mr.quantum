"""The global test seed is pinned and re-applied before every test."""

import random

import numpy as np
import pytest

SEED = 12345
# Golden values are numpy's / CPython's own output at SEED, not ours.
GOLDEN_DEFAULT_RNG = 0.22733602246716966
GOLDEN_LEGACY_NP = 0.9296160928171479
GOLDEN_STDLIB = 0.41661987254534116


def test_test_seed_fixture_is_pinned(test_seed: int) -> None:
    assert test_seed == SEED


def test_rng_fixture_is_seeded_generator(rng: np.random.Generator) -> None:
    assert isinstance(rng, np.random.Generator)
    assert rng.random() == GOLDEN_DEFAULT_RNG


def test_rng_fixture_is_fresh_per_test(rng: np.random.Generator) -> None:
    # Same golden value as the previous test: state does not leak between tests.
    assert rng.random() == GOLDEN_DEFAULT_RNG


@pytest.mark.parametrize("attempt", [1, 2])
def test_legacy_numpy_global_state_reset_each_test(attempt: int) -> None:
    assert np.random.random() == GOLDEN_LEGACY_NP


@pytest.mark.parametrize("attempt", [1, 2])
def test_stdlib_random_reset_each_test(attempt: int) -> None:
    assert random.random() == GOLDEN_STDLIB
