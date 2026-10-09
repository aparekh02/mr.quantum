"""Constant-interaction physics (trainer/physics/coulomb.py)."""

import math

import numpy as np
import pytest

from trainer.physics.coulomb import (
    Dot,
    coulomb_resonance,
    dot_transmission,
    effective_induced_charge,
    induced_charge,
    merged_dot,
    resonance,
    thermal_occupation,
    two_dot_transmission,
)
from trainer.physics.pinchoff import ELECTRON, HOLE

EC = 2.0e-3  # 2 meV
DOT = Dot(charging_energy=EC, lever_arms={"P": 0.1, "C": 0.02}, charge_offset=0.0)


# --- Dot validation -----------------------------------------------------------


def test_dot_rejects_non_positive_charging_energy() -> None:
    with pytest.raises(ValueError, match="charging_energy"):
        Dot(charging_energy=0.0, lever_arms={"P": 0.1})


def test_dot_rejects_negative_lever_arm() -> None:
    with pytest.raises(ValueError, match="lever arm"):
        Dot(charging_energy=EC, lever_arms={"P": -0.1})


# --- induced charge -----------------------------------------------------------


def test_induced_charge_golden() -> None:
    # (0.1 * 0.5 + 0.02 * 0.1) / 2e-3 = 26
    assert induced_charge(DOT, {"P": 0.5, "C": 0.1}, ELECTRON) == pytest.approx(26.0)


def test_induced_charge_hole_polarity_and_missing_gates_are_zero() -> None:
    assert induced_charge(DOT, {"P": -0.5}, HOLE) == pytest.approx(25.0)


def test_induced_charge_includes_offset() -> None:
    dot = Dot(charging_energy=EC, lever_arms={"P": 0.1}, charge_offset=0.3)
    assert induced_charge(dot, {"P": 0.0}, ELECTRON) == pytest.approx(0.3)


def test_effective_induced_charge_shifts_by_mutual_energy() -> None:
    # One extra charge on a neighbour with mutual energy Em shifts n0 by -Em/Ec.
    shifted = effective_induced_charge(10.0, EC, [(0.5e-3, 1.0)])
    assert shifted == pytest.approx(10.0 - 0.25)


# --- resonance and peaks ----------------------------------------------------


def test_resonance_is_one_on_resonance_and_symmetric() -> None:
    assert resonance(0.0, 1e-4) == 1.0
    assert resonance(1e-4, 1e-4) == pytest.approx(resonance(-1e-4, 1e-4))
    assert resonance(1e-4, 1e-4) == pytest.approx(1.0 / math.cosh(0.5) ** 2)


def test_resonance_rejects_non_positive_temperature() -> None:
    with pytest.raises(ValueError, match="kT"):
        resonance(0.0, 0.0)


def test_coulomb_peaks_at_half_integer_induced_charge() -> None:
    assert coulomb_resonance(10.5, EC, 5e-5) == pytest.approx(1.0, abs=1e-9)
    assert coulomb_resonance(10.0, EC, 5e-5) < 1e-6


def test_no_peaks_below_first_charge() -> None:
    # The 0 -> 1 transition sits at n0 = 1/2; below it the dot stays empty.
    assert coulomb_resonance(-2.0, EC, 5e-5) < 1e-12
    assert coulomb_resonance(-0.5, EC, 5e-5) < 1e-12
    assert coulomb_resonance(0.5, EC, 5e-5) == pytest.approx(1.0, abs=1e-9)


def test_peak_spacing_matches_charging_energy_over_lever_arm() -> None:
    v = np.linspace(0.0, 0.2, 20001)
    signal = np.array(
        [
            coulomb_resonance(induced_charge(DOT, {"P": x}, ELECTRON), EC, 2e-5)
            for x in v
        ]
    )
    peaks = np.where(
        (signal[1:-1] > signal[:-2])
        & (signal[1:-1] >= signal[2:])
        & (signal[1:-1] > 0.5)
    )[0]
    spacing = np.diff(v[peaks + 1])
    assert len(peaks) == 10  # 0.2 V / (Ec / alpha = 20 mV)
    assert spacing == pytest.approx(EC / 0.1, abs=2e-5)


def test_cross_gate_shifts_peaks_by_lever_arm_ratio() -> None:
    def first_peak(c_voltage: float) -> float:
        v = np.linspace(0.0, 0.03, 30001)
        s = [
            coulomb_resonance(
                induced_charge(DOT, {"P": x, "C": c_voltage}, ELECTRON), EC, 2e-5
            )
            for x in v
        ]
        return float(v[int(np.argmax(s))])

    shift = first_peak(0.05) - first_peak(0.0)
    assert shift == pytest.approx(-0.02 / 0.1 * 0.05, abs=2e-6)


# --- thermal occupation ------------------------------------------------------


def test_single_dot_occupation_steps_at_half_integers() -> None:
    u = np.array([[EC]])
    assert thermal_occupation(np.array([3.2]), u, 1e-6)[0] == pytest.approx(3.0)
    assert thermal_occupation(np.array([3.8]), u, 1e-6)[0] == pytest.approx(4.0)
    assert thermal_occupation(np.array([3.5]), u, 1e-6)[0] == pytest.approx(3.5)


def test_occupation_is_never_negative() -> None:
    u = np.array([[EC]])
    assert thermal_occupation(np.array([-3.0]), u, 1e-6)[0] == pytest.approx(0.0)


def test_occupation_rejects_bad_shapes() -> None:
    with pytest.raises(ValueError, match="shape"):
        thermal_occupation(np.array([1.0, 2.0]), np.array([[EC]]), 1e-6)


def _charge_map(em: float, n: int = 121) -> np.ndarray:
    u = np.array([[EC, em], [em, EC]])
    # Offset the axes differently so no sample sits exactly on a degeneracy line
    # (where <n> = 1/2), including the interdot line n0_1 = n0_2.
    grid_a = np.linspace(0.0137, 3.0137, n)
    grid_b = np.linspace(0.0071, 3.0071, n)
    states = np.empty((n, n), dtype=np.int64)
    for i, a in enumerate(grid_a):
        for j, b in enumerate(grid_b):
            occ = np.rint(thermal_occupation(np.array([a, b]), u, 1e-7)).astype(int)
            states[i, j] = occ[0] * 100 + occ[1]
    return states


def _max_states_at_a_vertex(states: np.ndarray) -> int:
    return max(
        len({states[i, j], states[i + 1, j], states[i, j + 1], states[i + 1, j + 1]})
        for i in range(states.shape[0] - 1)
        for j in range(states.shape[1] - 1)
    )


def test_double_dot_without_mutual_charging_is_a_square_grid() -> None:
    assert _max_states_at_a_vertex(_charge_map(0.0)) == 4


def test_double_dot_with_mutual_charging_is_a_honeycomb() -> None:
    # Mutual charging splits every 4-fold crossing into two triple points.
    assert _max_states_at_a_vertex(_charge_map(0.5e-3)) == 3


def test_honeycomb_triple_point_separation_matches_mutual_energy() -> None:
    # Along the diagonal n0_1 = n0_2 = x, the (0,0)->(1,1) transition splits into
    # two steps separated by Em/Ec in induced charge.
    em = 0.5e-3
    u = np.array([[EC, em], [em, EC]])
    xs = np.linspace(0.0, 1.0, 10001)
    totals = np.array([thermal_occupation(np.array([x, x]), u, 1e-7).sum() for x in xs])
    first = xs[np.argmax(totals > 0.5)]
    second = xs[np.argmax(totals > 1.5)]
    assert second - first == pytest.approx(em / (EC + em), abs=2e-4)


# --- transmissions -----------------------------------------------------------


@pytest.mark.parametrize(
    ("openness", "res", "expected"),
    [(1.0, 0.0, 1.0), (0.0, 0.3, 0.3), (0.25, 0.0, 0.25), (0.5, 1.0, 1.0)],
)
def test_dot_transmission(openness: float, res: float, expected: float) -> None:
    assert dot_transmission(res, openness) == pytest.approx(expected)


def test_dot_transmission_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="openness"):
        dot_transmission(0.5, 1.5)


def test_two_dot_transmission_triple_points_and_lines() -> None:
    # Closed dots, no merging: only both-resonant points conduct.
    assert two_dot_transmission(1.0, 1.0, 0.0, 0.0, 0.0, 0.0) == pytest.approx(1.0)
    assert two_dot_transmission(1.0, 0.0, 0.0, 0.0, 0.0, 0.0) == pytest.approx(0.0)
    # Partly open dot 2: dot-1 lines appear with strength o2.
    assert two_dot_transmission(1.0, 0.0, 0.0, 0.2, 0.0, 0.0) == pytest.approx(0.2)
    # Fully merged: single big dot.
    assert two_dot_transmission(0.0, 0.0, 0.0, 0.0, 1.0, 0.7) == pytest.approx(0.7)


def test_merged_dot_sums_lever_arms_and_offsets() -> None:
    a = Dot(charging_energy=2e-3, lever_arms={"P1": 0.1, "P2": 0.02}, charge_offset=0.1)
    b = Dot(charging_energy=2e-3, lever_arms={"P2": 0.1, "P1": 0.02}, charge_offset=0.2)
    m = merged_dot(a, b, mutual_energy=0.5e-3)
    # Combined island: Ec_m = (Ec1 Ec2 - Em^2) / (Ec1 + Ec2 - 2 Em),
    # which is (Ec + Em) / 2 for equal dots.
    ec_m = (2e-3 * 2e-3 - 0.5e-3**2) / (2e-3 + 2e-3 - 2 * 0.5e-3)
    assert m.charging_energy == pytest.approx(ec_m)
    assert ec_m == pytest.approx((2e-3 + 0.5e-3) / 2)
    # Induced charges add: alpha_m / Ec_m = alpha_1 / Ec1 + alpha_2 / Ec2.
    expected = ec_m * (0.1 + 0.02) / 2e-3
    assert m.lever_arms == {
        "P1": pytest.approx(expected),
        "P2": pytest.approx(expected),
    }
    assert m.charge_offset == pytest.approx(0.3)


def test_merged_dot_induced_charge_is_the_sum() -> None:
    a = Dot(charging_energy=2e-3, lever_arms={"P1": 0.1, "P2": 0.02}, charge_offset=0.1)
    b = Dot(charging_energy=3e-3, lever_arms={"P2": 0.1, "P1": 0.03}, charge_offset=0.2)
    m = merged_dot(a, b, mutual_energy=0.4e-3)
    v = {"P1": 0.21, "P2": -0.13}
    assert induced_charge(m, v, ELECTRON) == pytest.approx(
        induced_charge(a, v, ELECTRON) + induced_charge(b, v, ELECTRON)
    )


# --- joint occupation with occupation-coupled (sensed) dots -------------------

from trainer.physics.coulomb import joint_occupation  # noqa: E402


def test_joint_occupation_without_sensing_matches_thermal_occupation() -> None:
    u = np.array([[EC, 0.5e-3], [0.5e-3, EC]])
    w = np.zeros((2, 2))
    n0 = np.array([1.3, 2.6])
    assert joint_occupation(n0, u, w, 1e-5) == pytest.approx(
        thermal_occupation(n0, u, 1e-5)
    )


def test_joint_occupation_sensed_charge_repels() -> None:
    # Dot 1 sits just past its 0->1 transition. A sensed neighbour holding two
    # charges with coupling W raises dot 1's addition energy by 2W; with 2W large
    # enough, dot 1 empties.
    u = np.diag([EC, EC])
    n0 = np.array([0.6, 2.2])
    w_small = np.array([[0.0, 0.05e-3], [0.05e-3, 0.0]])
    w_large = np.array([[0.0, 0.3e-3], [0.3e-3, 0.0]])
    assert joint_occupation(n0, u, w_small, 1e-6)[0] == pytest.approx(1.0, abs=1e-6)
    assert joint_occupation(n0, u, w_large, 1e-6)[0] == pytest.approx(0.0, abs=1e-6)


def test_joint_occupation_is_self_consistent_for_a_big_sensor() -> None:
    # A many-charge sensor strongly shifts a small dot; the exact joint answer
    # must satisfy both dots' equilibrium simultaneously.
    u = np.diag([EC, EC])
    w = np.array([[0.0, 1e-4], [1e-4, 0.0]])
    n0 = np.array([1.2, 61.0])
    occ = joint_occupation(n0, u, w, 1e-6)
    shifted_dot = n0[0] - w[0, 1] * occ[1] / EC
    assert occ[0] == pytest.approx(max(0.0, round(shifted_dot)), abs=1e-6)
    shifted_sensor = n0[1] - w[1, 0] * occ[0] / EC
    assert occ[1] == pytest.approx(round(shifted_sensor), abs=1e-6)


def test_joint_occupation_rejects_bad_shapes() -> None:
    with pytest.raises(ValueError, match="shape"):
        joint_occupation(np.array([1.0]), np.eye(1) * EC, np.zeros((2, 2)), 1e-6)


def test_depleted_neighbour_exerts_no_indirect_push() -> None:
    # A partner dot whose gate-induced charge is far negative is a depleted region,
    # not an island: it must not shift its neighbour through the mutual term.
    u = np.array([[EC, 0.5e-3], [0.5e-3, EC]])
    w = np.zeros((2, 2))
    near_empty = joint_occupation(np.array([0.6, 0.0]), u, w, 1e-6)
    depleted = joint_occupation(np.array([0.6, -20.0]), u, w, 1e-6)
    assert near_empty[0] == pytest.approx(1.0, abs=1e-6)
    assert depleted[0] == pytest.approx(1.0, abs=1e-6)
    assert depleted[1] == pytest.approx(0.0, abs=1e-6)


def test_occupied_neighbour_still_couples_through_deviation() -> None:
    # Within the honeycomb (n0 >= 0) the constant-interaction coupling is intact:
    # dot 2 slightly short of a charge pushes dot 1 past its degeneracy.
    u = np.array([[EC, 0.5e-3], [0.5e-3, EC]])
    w = np.zeros((2, 2))
    occ = joint_occupation(np.array([0.45, 1.4]), u, w, 1e-6)
    # mu_1 = Ec (1/2 - 0.45) + Em (1 - 1.4) < 0  ->  dot 1 fills
    assert occ[0] == pytest.approx(1.0, abs=1e-6)
