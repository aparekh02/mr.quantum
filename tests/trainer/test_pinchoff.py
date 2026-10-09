"""Pure-function pinch-off physics (trainer/physics/pinchoff.py)."""

import math

import numpy as np
import pytest

from trainer.physics.pinchoff import (
    ELECTRON,
    HOLE,
    GateTurnOn,
    channel_current,
    gate_conductance,
    noisy,
    series_conductance,
    turn_on,
)

P1 = GateTurnOn(v_threshold=0.5, width=0.05, g_max=4e-5)


# --- turn_on -----------------------------------------------------------------


def test_turn_on_is_half_at_threshold() -> None:
    assert turn_on(0.5, P1, ELECTRON) == pytest.approx(0.5, abs=1e-15)


def test_turn_on_limits() -> None:
    assert turn_on(-1.0, P1, ELECTRON) == pytest.approx(0.0, abs=1e-12)
    assert turn_on(2.0, P1, ELECTRON) == pytest.approx(1.0, abs=1e-12)


def test_turn_on_golden_value() -> None:
    # 0.5 * (1 + tanh((0.55 - 0.5) / 0.05)) = 0.5 * (1 + tanh(1))
    assert turn_on(0.55, P1, ELECTRON) == pytest.approx(
        0.5 * (1 + math.tanh(1.0)), rel=1e-12
    )


def test_turn_on_monotonic_increasing_for_electrons() -> None:
    v = np.linspace(-2.0, 2.0, 2001)
    t = turn_on(v, P1, ELECTRON)
    assert np.all(np.diff(t) >= 0)
    assert np.all((t >= 0) & (t <= 1))


def test_turn_on_monotonic_decreasing_for_holes() -> None:
    hole_gate = GateTurnOn(v_threshold=-0.5, width=0.05, g_max=4e-5)
    v = np.linspace(-2.0, 2.0, 2001)
    t = turn_on(v, hole_gate, HOLE)
    assert np.all(np.diff(t) <= 0)
    assert turn_on(-0.5, hole_gate, HOLE) == pytest.approx(0.5, abs=1e-15)
    assert turn_on(-2.0, hole_gate, HOLE) == pytest.approx(1.0, abs=1e-12)


def test_turn_on_accepts_arrays_and_scalars() -> None:
    assert isinstance(turn_on(0.1, P1, ELECTRON), float)
    assert turn_on(np.array([0.1, 0.9]), P1, ELECTRON).shape == (2,)


# --- parameter validation ----------------------------------------------------


@pytest.mark.parametrize("width", [0.0, -0.01])
def test_gate_turn_on_rejects_non_positive_width(width: float) -> None:
    with pytest.raises(ValueError, match="width"):
        GateTurnOn(v_threshold=0.5, width=width, g_max=1e-5)


def test_gate_turn_on_rejects_negative_g_max() -> None:
    with pytest.raises(ValueError, match="g_max"):
        GateTurnOn(v_threshold=0.5, width=0.05, g_max=-1e-6)


def test_gate_turn_on_allows_zero_g_max_boundary() -> None:
    assert GateTurnOn(v_threshold=0.5, width=0.05, g_max=0.0).g_max == 0.0


def test_turn_on_rejects_bad_polarity() -> None:
    with pytest.raises(ValueError, match="polarity"):
        turn_on(0.5, P1, 0)


# --- conductance and current ------------------------------------------------


def test_gate_conductance_is_g_max_times_turn_on() -> None:
    assert gate_conductance(0.55, P1, ELECTRON) == pytest.approx(
        4e-5 * 0.5 * (1 + math.tanh(1.0)), rel=1e-12
    )


def test_series_conductance_golden() -> None:
    # 1 / (1e4 + 1/2e-5 + 1/5e-5) = 1 / (1e4 + 5e4 + 2e4) = 1 / 8e4
    assert series_conductance([2e-5, 5e-5], series_resistance=1e4) == pytest.approx(
        1.25e-5, rel=1e-12
    )


def test_series_conductance_any_pinched_gate_blocks() -> None:
    assert series_conductance([2e-5, 0.0], series_resistance=1e4) == 0.0


def test_series_conductance_no_gates_is_contact_only() -> None:
    assert series_conductance([], series_resistance=1e4) == pytest.approx(1e-4)


def test_series_conductance_rejects_negative_resistance() -> None:
    with pytest.raises(ValueError, match="series_resistance"):
        series_conductance([1e-5], series_resistance=-1.0)


def test_series_conductance_zero_resistance_and_no_gates_rejected() -> None:
    with pytest.raises(ValueError, match="short"):
        series_conductance([], series_resistance=0.0)


def test_channel_current_is_ohmic_in_bias() -> None:
    g = 1.25e-5
    assert channel_current(1e-3, g) == pytest.approx(1.25e-8, rel=1e-12)
    assert channel_current(-1e-3, g) == pytest.approx(-1.25e-8, rel=1e-12)
    assert channel_current(0.0, g) == 0.0


# --- noise ---------------------------------------------------------------------


def test_noisy_is_deterministic_at_fixed_seed() -> None:
    a = noisy(1e-9, 1e-11, np.random.default_rng(1234))
    b = noisy(1e-9, 1e-11, np.random.default_rng(1234))
    assert a == b


def test_noisy_golden_value(rng: np.random.Generator) -> None:
    # rng is default_rng(12345); its first standard normal is numpy's, not ours.
    first_normal = np.random.default_rng(12345).standard_normal()
    assert noisy(1e-9, 1e-11, rng) == pytest.approx(
        1e-9 + 1e-11 * first_normal, rel=1e-12
    )


def test_noisy_zero_std_is_exact() -> None:
    assert noisy(1e-9, 0.0, np.random.default_rng(0)) == 1e-9


def test_noisy_rejects_negative_std() -> None:
    with pytest.raises(ValueError, match="noise_std"):
        noisy(1e-9, -1e-12, np.random.default_rng(0))


def test_noisy_statistics(rng: np.random.Generator) -> None:
    samples = np.array([noisy(0.0, 1e-11, rng) for _ in range(20000)])
    assert abs(samples.mean()) < 3 * 1e-11 / math.sqrt(20000) * 2
    assert samples.std() == pytest.approx(1e-11, rel=0.03)
