"""Charge-qubit physics of the trainer's double dot (qollab/dqd.py)."""

import math

import dqd
import numpy as np
import pytest


def test_tunnel_coupling_grows_as_the_inner_barrier_opens() -> None:
    voltages = np.linspace(-0.4, -1.4, 50)  # holes: more negative = more open
    couplings = [dqd.tunnel_coupling_ueV(v) for v in voltages]
    assert all(b >= a for a, b in zip(couplings, couplings[1:], strict=False))
    assert couplings[0] < 1.0
    assert couplings[-1] == pytest.approx(dqd.T_MAX_UEV, rel=0.01)


def test_tunnel_coupling_is_half_maximum_at_the_barrier_threshold() -> None:
    assert dqd.tunnel_coupling_ueV(dqd.BA1_THRESHOLD_V) == pytest.approx(
        dqd.T_MAX_UEV / 2
    )


def test_merge_factor_matches_the_trainer_simulator() -> None:
    # The trainer merges the dots by (inner-barrier turn-on)^4.
    v = -0.88
    turn_on = 0.5 * (1 + math.tanh(-(v - dqd.BA1_THRESHOLD_V) / dqd.BA1_WIDTH_V))
    assert dqd.merge_factor(v) == pytest.approx(turn_on**4)
    assert dqd.dots_separate(-0.88)
    assert not dqd.dots_separate(-1.6)


def test_detuning_per_millivolt_from_lever_arms() -> None:
    # Moving +δ/2 on PA1 and -δ/2 on PA2 changes ε by ((α11-α21)+(α22-α12))/2 · δ.
    expected = ((0.080 - 0.020) + (0.080 - 0.020)) / 2 * 1e3  # µeV per mV
    assert dqd.detuning_ueV_per_mV() == pytest.approx(expected)


def test_excited_probability_formula_golden() -> None:
    eps, delta, tau_ns = 30.0, 40.0, 0.05
    omega = math.hypot(eps, delta)
    theta = omega * tau_ns / dqd.HBAR_UEV_NS
    expected = (delta / omega) ** 2 * math.sin(theta / 2) ** 2
    assert dqd.p_right(eps, delta, tau_ns) == pytest.approx(expected, rel=1e-12)


def test_resonance_is_full_contrast_only_at_zero_detuning() -> None:
    delta = 40.0
    tau = math.pi * dqd.HBAR_UEV_NS / delta  # a pi pulse at ε = 0
    assert dqd.p_right(0.0, delta, tau) == pytest.approx(1.0)
    assert dqd.p_right(3 * delta, delta, tau) < 0.2


def test_sweet_spot_is_first_order_insensitive_to_detuning_noise() -> None:
    delta = 40.0
    freq = lambda e: dqd.qubit_frequency_ghz(e, delta)  # noqa: E731
    h = 1e-3
    slope_at_sweet_spot = (freq(h) - freq(-h)) / (2 * h)
    slope_off = (freq(2 * delta + h) - freq(2 * delta - h)) / (2 * h)
    assert abs(slope_at_sweet_spot) < 1e-6
    assert abs(slope_off) > 1e-3


def test_qubit_frequency_golden() -> None:
    # Ω = sqrt(ε² + Δ²); f = Ω / h; h = 4.135667 µeV·ns
    assert dqd.qubit_frequency_ghz(0.0, 41.35667) == pytest.approx(10.0, rel=1e-5)


def test_sensor_current_contrast_depends_on_the_sensor_operating_point() -> None:
    on_flank = dqd.sensor_currents_nA(on_flank=True)
    on_top = dqd.sensor_currents_nA(on_flank=False)
    assert abs(on_flank[1] - on_flank[0]) > 1.5 * abs(on_top[1] - on_top[0])


def test_charge_map_shows_the_interdot_line() -> None:
    rows = dqd.charge_map(width=41, height=21, half_window_mV=12.0, marks=[(0.0, 0.0)])
    assert len(rows) == 21 and all(len(r) == 41 for r in rows)
    text = "".join(rows)
    assert {"L", "R"} <= set(text)  # (1,0) and (0,1) both present
    assert "*" in text  # the operating point is marked
