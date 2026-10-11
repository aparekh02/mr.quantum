"""The trainer's double dot as a charge qubit: device numbers and closed-form physics.

Parameters are copied from the Stanza Tune-Up Trainer's simulated device
(trainer/devices/dqd_with_sensor.yaml): charging energies, mutual charging energy,
lever arms and the inner barrier BA1's turn-on. T_MAX_UEV, the fully-open tunnel
coupling, is the one extra model parameter this project adds.

Units: energies in µeV, times in ns, voltages in V (offsets in mV where noted).
"""

from __future__ import annotations

import math

HBAR_UEV_NS = 0.6582119569
H_UEV_NS = 4.135667696

# From trainer/devices/dqd_with_sensor.yaml (side A double dot D1/D2, sensor SD).
EC_D1_UEV = 1600.0
EC_D2_UEV = 1600.0
EM_D1D2_UEV = 350.0
ALPHA = {
    ("D1", "PA1"): 0.080,
    ("D1", "PA2"): 0.020,
    ("D2", "PA1"): 0.020,
    ("D2", "PA2"): 0.080,
}
BA1_THRESHOLD_V = -0.85
BA1_WIDTH_V = 0.15
EM_SD_D1_UEV = 100.0
EM_SD_D2_UEV = 150.0
SENSOR_KT_UEV = 56.0  # thermal + lifetime broadening of the sensor at its flank
SENSOR_PEAK_NA = 1.0

T_MAX_UEV = 40.0
"""Interdot tunnel coupling with the inner barrier fully open (model parameter)."""

MAX_MERGE = 0.5


def _barrier_turn_on(inner_barrier_v: float) -> float:
    """Turn-on of the channel under BA1 (holes: conducts at negative voltage)."""
    return 0.5 * (1.0 + math.tanh(-(inner_barrier_v - BA1_THRESHOLD_V) / BA1_WIDTH_V))


def tunnel_coupling_ueV(inner_barrier_v: float) -> float:
    """Interdot tunnel coupling t_c set by the inner barrier."""
    return T_MAX_UEV * _barrier_turn_on(inner_barrier_v)


def merge_factor(inner_barrier_v: float) -> float:
    """How far the two dots have merged into one (the trainer uses turn-on⁴)."""
    return _barrier_turn_on(inner_barrier_v) ** 4


def dots_separate(inner_barrier_v: float) -> bool:
    return merge_factor(inner_barrier_v) < MAX_MERGE


def detuning_ueV_per_mV() -> float:
    """Detuning change per mV along the axis (+δ/2 on PA1, -δ/2 on PA2)."""
    a11, a12 = ALPHA[("D1", "PA1")], ALPHA[("D1", "PA2")]
    a21, a22 = ALPHA[("D2", "PA1")], ALPHA[("D2", "PA2")]
    return ((a11 - a21) + (a22 - a12)) / 2.0 * 1e3


def p_right(detuning_ueV: float, delta_ueV: float, pulse_ns: float) -> float:
    """Probability the charge has moved to the right dot after a detuning pulse.

    H = (ε σz + Δ σx) / 2 from |L>: P = (Δ/Ω)² sin²(Ω τ / 2ħ), Ω = sqrt(ε² + Δ²).
    """
    omega = math.hypot(detuning_ueV, delta_ueV)
    if omega == 0.0:
        return 0.0
    theta = omega * pulse_ns / HBAR_UEV_NS
    return (delta_ueV / omega) ** 2 * math.sin(theta / 2.0) ** 2


def qubit_frequency_ghz(detuning_ueV: float, delta_ueV: float) -> float:
    """Charge-qubit frequency Ω / h."""
    return math.hypot(detuning_ueV, delta_ueV) / H_UEV_NS


def sensor_currents_nA(on_flank: bool) -> tuple[float, float]:
    """Charge-sensor current with the charge on the left vs the right dot.

    Moving the charge from D1 to D2 shifts the sensor dot by the difference of its
    mutual charging energies with them. On a Coulomb peak's flank that shift
    changes the current a lot; on the flat top it changes it much less.
    """

    def peak(mu: float) -> float:
        return SENSOR_PEAK_NA / math.cosh(mu / (2.0 * SENSOR_KT_UEV)) ** 2

    park = 1.317 * SENSOR_KT_UEV if on_flank else 0.0
    shift = EM_SD_D2_UEV - EM_SD_D1_UEV
    return peak(park), peak(park + shift)


def _ground_state(x1: float, x2: float) -> tuple[int, int]:
    best, state = math.inf, (0, 0)
    for n1 in range(4):
        for n2 in range(4):
            d1, d2 = n1 - x1, n2 - x2
            e = (
                0.5 * EC_D1_UEV * d1 * d1
                + 0.5 * EC_D2_UEV * d2 * d2
                + EM_D1D2_UEV * d1 * d2
            )
            if e < best:
                best, state = e, (n1, n2)
    return state


_SYMBOL = {(0, 0): ".", (1, 0): "L", (0, 1): "R", (1, 1): "#"}


def charge_map(
    width: int, height: int, half_window_mV: float, marks: list[tuple[float, float]]
) -> list[str]:
    """ASCII charge-stability map around the (1,0)↔(0,1) interdot line.

    Columns are the PA1 offset, rows the PA2 offset (top = positive), in mV. 'L' is
    the charge on the left dot, 'R' on the right, '.' both empty, '#' both full;
    '*' marks the given (PA1, PA2) offsets.
    """

    def column(mv: float) -> int:
        return round((mv + half_window_mV) / (2 * half_window_mV) * (width - 1))

    def row(mv: float) -> int:
        return round((half_window_mV - mv) / (2 * half_window_mV) * (height - 1))

    marked = {(row(b), column(a)) for a, b in marks}
    rows = []
    for r in range(height):
        d2 = (half_window_mV - r * 2 * half_window_mV / (height - 1)) * 1e-3
        line = []
        for c in range(width):
            d1 = (-half_window_mV + c * 2 * half_window_mV / (width - 1)) * 1e-3
            # Holes: a more negative plunger adds charge.
            x1 = (
                0.5
                - (ALPHA[("D1", "PA1")] * d1 + ALPHA[("D1", "PA2")] * d2)
                * 1e6
                / EC_D1_UEV
            )
            x2 = (
                0.5
                - (ALPHA[("D2", "PA1")] * d1 + ALPHA[("D2", "PA2")] * d2)
                * 1e6
                / EC_D2_UEV
            )
            line.append(
                "*" if (r, c) in marked else _SYMBOL.get(_ground_state(x1, x2), "+")
            )
        rows.append("".join(line))
    return rows
