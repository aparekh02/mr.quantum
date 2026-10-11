"""Charge-qubit experiments as one Qiskit circuit, and their analysis.

Every qubit of the circuit is an independent copy of the double-dot charge qubit at
its own experimental setting (detuning, pulse length). Measuring all of them at once
puts a whole sweep into one job, which is what IonQ backends allow per run.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import dqd
import numpy as np
from qiskit import QuantumCircuit

KINDS = ("detuning_sweep", "time_sweep", "sweet_spot")
MAX_QUBITS = 24


@dataclass(frozen=True)
class Experiment:
    kind: str
    qubits: int
    delta_ueV: float
    detuning_ueV: float
    pulse_ps: float
    noise_ueV: float
    seed: int


@dataclass(frozen=True)
class Setting:
    index: int
    group: str
    nominal_detuning_ueV: float
    detuning_ueV: float
    delta_ueV: float
    pulse_ns: float


def _validate(exp: Experiment) -> None:
    if exp.kind not in KINDS:
        raise ValueError(
            f"experiment must be one of {', '.join(KINDS)}; got {exp.kind!r}"
        )
    if not 2 <= exp.qubits <= MAX_QUBITS:
        raise ValueError(f"qubits must be between 2 and {MAX_QUBITS}; got {exp.qubits}")
    if exp.pulse_ps < 0:
        raise ValueError(f"pulse_ps must be >= 0; got {exp.pulse_ps}")
    if exp.noise_ueV < 0:
        raise ValueError(f"charge noise must be >= 0; got {exp.noise_ueV}")
    if exp.delta_ueV < 0:
        raise ValueError(f"delta (tunnel splitting) must be >= 0; got {exp.delta_ueV}")


def _nominal(exp: Experiment) -> list[tuple[str, float, float]]:
    n, pulse = exp.qubits, exp.pulse_ps / 1000.0
    if exp.kind == "detuning_sweep":
        span = max(4.0 * exp.delta_ueV, 100.0)
        return [
            ("sweep", exp.detuning_ueV + e, pulse) for e in np.linspace(-span, span, n)
        ]
    if exp.kind == "time_sweep":
        return [
            ("sweep", exp.detuning_ueV, float(t)) for t in np.linspace(0.0, pulse, n)
        ]
    off = exp.detuning_ueV if exp.detuning_ueV != 0.0 else max(exp.delta_ueV, 1.0)
    half = n // 2
    first = [("sweet spot", 0.0, float(t)) for t in np.linspace(0.0, pulse, half)]
    second = [
        ("off sweet spot", off, float(t)) for t in np.linspace(0.0, pulse, n - half)
    ]
    return first + second


def build(exp: Experiment) -> tuple[QuantumCircuit, list[Setting]]:
    """One circuit, one qubit per setting; quasi-static charge noise per qubit."""
    _validate(exp)
    rng = np.random.default_rng(exp.seed)
    circuit = QuantumCircuit(exp.qubits, exp.qubits, name=exp.kind)
    settings = []
    for k, (group, eps0, tau) in enumerate(_nominal(exp)):
        eps = (
            float(eps0 + exp.noise_ueV * rng.standard_normal())
            if exp.noise_ueV
            else float(eps0)
        )
        omega = math.hypot(eps, exp.delta_ueV)
        phi = math.atan2(exp.delta_ueV, eps)  # tilt of the rotation axis from z
        theta = omega * tau / dqd.HBAR_UEV_NS
        # exp(-iHτ/ħ) with H = (ε σz + Δ σx)/2 is a rotation by θ about n = (Δ, 0, ε)/Ω:
        # R_n(θ) = Ry(φ) Rz(θ) Ry(-φ).
        circuit.ry(-phi, k)
        circuit.rz(theta, k)
        circuit.ry(phi, k)
        circuit.measure(k, k)
        settings.append(Setting(k, group, float(eps0), eps, exp.delta_ueV, float(tau)))
    return circuit, settings


def marginals(counts: dict[str, int], qubits: int) -> list[float]:
    """P(1) for each qubit from a counts dict (bit k is the k-th character from the right)."""
    shots = sum(counts.values())
    out = [0.0] * qubits
    for bits, c in counts.items():
        bits = bits.replace(" ", "")
        for k in range(qubits):
            if bits[len(bits) - 1 - k] == "1":
                out[k] += c
    return [x / shots for x in out] if shots else out


def estimate_frequency_ghz(times_ns: list[float], probs: list[float]) -> float:
    """Best-fit f of P(t) = A sin²(π f t), by a dense search over f.

    The search stops below the Nyquist frequency of the sample spacing: above it,
    f and its alias 1/dt − f produce identical samples."""
    t, p = np.asarray(times_ns), np.asarray(probs)
    steps = np.diff(np.unique(t))
    f_max = 200.0 if steps.size == 0 else min(200.0, 0.5 / float(steps.min()))
    best_f, best_err = 0.0, math.inf
    for f in np.geomspace(0.5, f_max, 6000):
        s = np.sin(math.pi * f * t) ** 2
        denom = float(np.dot(s, s))
        if denom == 0.0:
            continue
        a = float(np.dot(p, s)) / denom
        err = float(np.sum((p - a * s) ** 2))
        if err < best_err:
            best_f, best_err = float(f), err
    return best_f


def fit_delta_ueV(
    detunings_ueV: list[float], probs: list[float], pulse_ns: float
) -> float:
    """Best-fit tunnel splitting Δ from a detuning sweep at a fixed pulse."""
    eps, p = np.asarray(detunings_ueV), np.asarray(probs)
    best_d, best_err = 0.0, math.inf
    for d in np.linspace(0.5, 300.0, 3000):
        model = np.array([dqd.p_right(float(e), float(d), pulse_ns) for e in eps])
        err = float(np.sum((p - model) ** 2))
        if err < best_err:
            best_d, best_err = float(d), err
    return best_d


def oscillation_contrast(probs: list[float]) -> float:
    return float(max(probs) - min(probs)) if len(probs) >= 2 else 0.0


def frequency_shift_ghz(settings: list[Setting], group: str) -> float:
    """Typical (median) shift of a group's qubit frequencies from the noise-free
    value, caused by each qubit's frozen charge-noise offset."""
    shifts = [
        abs(
            dqd.qubit_frequency_ghz(s.detuning_ueV, s.delta_ueV)
            - dqd.qubit_frequency_ghz(s.nominal_detuning_ueV, s.delta_ueV)
        )
        for s in settings
        if s.group == group
    ]
    return float(np.median(shifts)) if shifts else 0.0


def deviation_from_noise_free(
    settings: list[Setting], probs: list[float], group: str
) -> float:
    """Mean distance of a group's measured P(R) from the noise-free prediction,
    as a fraction of the noise-free swing (Δ/Ω)²."""
    devs = []
    for s, p in zip(settings, probs, strict=True):
        if s.group != group:
            continue
        ideal = dqd.p_right(s.nominal_detuning_ueV, s.delta_ueV, s.pulse_ns)
        swing = s.delta_ueV**2 / (s.delta_ueV**2 + s.nominal_detuning_ueV**2)
        devs.append(abs(p - ideal) / swing)
    return float(np.mean(devs)) if devs else 0.0
