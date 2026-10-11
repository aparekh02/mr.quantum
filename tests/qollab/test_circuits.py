"""The experiments as one Qiskit circuit (qollab/qubit.py)."""

import math
from typing import Any

import dqd
import numpy as np
import pytest
import qubit
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector


def _marginals(circuit: QuantumCircuit) -> list[float]:
    """Exact P(1) of each qubit, from the statevector (measurements removed)."""
    bare = circuit.remove_final_measurements(inplace=False)
    probs = Statevector(bare).probabilities_dict()
    n = bare.num_qubits
    out = [0.0] * n
    for bits, p in probs.items():
        for k in range(n):
            if bits[n - 1 - k] == "1":
                out[k] += p
    return out


@pytest.mark.parametrize("kind", ["detuning_sweep", "time_sweep", "sweet_spot"])
def test_one_circuit_with_one_qubit_per_setting(kind: str) -> None:
    exp = qubit.Experiment(
        kind=kind,
        qubits=12,
        delta_ueV=40.0,
        detuning_ueV=60.0,
        pulse_ps=60.0,
        noise_ueV=0.0,
        seed=1,
    )
    circuit, settings = qubit.build(exp)
    assert circuit.num_qubits == 12 == len(settings)
    assert circuit.num_clbits == 12


@pytest.mark.parametrize("kind", ["detuning_sweep", "time_sweep", "sweet_spot"])
def test_each_qubit_evolves_exactly_as_the_charge_qubit_hamiltonian(kind: str) -> None:
    exp = qubit.Experiment(
        kind=kind,
        qubits=10,
        delta_ueV=35.0,
        detuning_ueV=50.0,
        pulse_ps=80.0,
        noise_ueV=5.0,
        seed=3,
    )
    circuit, settings = qubit.build(exp)
    exact = _marginals(circuit)
    for s, p in zip(settings, exact, strict=True):
        assert p == pytest.approx(
            dqd.p_right(s.detuning_ueV, s.delta_ueV, s.pulse_ns), abs=1e-9
        )


def test_detuning_sweep_spans_both_sides_of_the_anticrossing() -> None:
    exp = qubit.Experiment(
        kind="detuning_sweep",
        qubits=9,
        delta_ueV=40.0,
        detuning_ueV=0.0,
        pulse_ps=40.0,
        noise_ueV=0.0,
        seed=0,
    )
    _, settings = qubit.build(exp)
    eps = [s.nominal_detuning_ueV for s in settings]
    assert min(eps) < 0 < max(eps)
    assert eps == sorted(eps)


def test_time_sweep_starts_at_zero_and_reaches_the_pulse() -> None:
    exp = qubit.Experiment(
        kind="time_sweep",
        qubits=8,
        delta_ueV=40.0,
        detuning_ueV=0.0,
        pulse_ps=200.0,
        noise_ueV=0.0,
        seed=0,
    )
    _, settings = qubit.build(exp)
    assert settings[0].pulse_ns == 0.0
    assert settings[-1].pulse_ns == pytest.approx(0.2)


def test_noise_is_seeded_and_only_moves_detuning() -> None:
    exp = qubit.Experiment(
        kind="sweet_spot",
        qubits=8,
        delta_ueV=40.0,
        detuning_ueV=80.0,
        pulse_ps=300.0,
        noise_ueV=10.0,
        seed=5,
    )
    a, b = qubit.build(exp)[1], qubit.build(exp)[1]
    assert [s.detuning_ueV for s in a] == [s.detuning_ueV for s in b]
    assert any(s.detuning_ueV != s.nominal_detuning_ueV for s in a)
    assert all(s.delta_ueV == 40.0 for s in a)


def test_sweet_spot_groups() -> None:
    exp = qubit.Experiment(
        kind="sweet_spot",
        qubits=10,
        delta_ueV=40.0,
        detuning_ueV=80.0,
        pulse_ps=300.0,
        noise_ueV=0.0,
        seed=5,
    )
    _, settings = qubit.build(exp)
    groups = [s.group for s in settings]
    assert groups.count("sweet spot") == 5 and groups.count("off sweet spot") == 5


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("qubits", 1, "qubits"),
        ("qubits", 25, "qubits"),
        ("kind", "nope", "experiment"),
        ("pulse_ps", -1.0, "pulse"),
        ("noise_ueV", -1.0, "noise"),
        ("delta_ueV", -1.0, "delta"),
    ],
)
def test_bad_experiments_rejected(field: str, value: object, match: str) -> None:
    base: dict[str, Any] = {
        "kind": "detuning_sweep",
        "qubits": 8,
        "delta_ueV": 40.0,
        "detuning_ueV": 0.0,
        "pulse_ps": 40.0,
        "noise_ueV": 0.0,
        "seed": 0,
    }
    base[field] = value
    with pytest.raises(ValueError, match=match):
        qubit.build(qubit.Experiment(**base))


def test_frequency_estimate_recovers_the_qubit_frequency() -> None:
    delta = 40.0
    f_true = dqd.qubit_frequency_ghz(0.0, delta)
    times = np.linspace(0.0, 0.3, 24)
    probs = [dqd.p_right(0.0, delta, t) for t in times]
    assert qubit.estimate_frequency_ghz(list(times), probs) == pytest.approx(
        f_true, rel=0.03
    )


def test_delta_fit_recovers_the_tunnel_splitting() -> None:
    delta, tau = 40.0, 0.04
    eps = np.linspace(-200, 200, 24)
    probs = [dqd.p_right(e, delta, tau) for e in eps]
    assert qubit.fit_delta_ueV(list(eps), probs, tau) == pytest.approx(delta, rel=0.05)


def test_contrast_metric() -> None:
    assert qubit.oscillation_contrast([0.0, 1.0, 0.0, 1.0]) == pytest.approx(1.0)
    assert qubit.oscillation_contrast([0.5, 0.5]) == 0.0
    assert math.isfinite(qubit.oscillation_contrast([0.2]))


def _sweet_spot(noise_ueV: float, seed: int = 7) -> list[qubit.Setting]:
    exp = qubit.Experiment(
        kind="sweet_spot",
        qubits=24,
        delta_ueV=48.0,
        detuning_ueV=0.0,
        pulse_ps=300.0,
        noise_ueV=noise_ueV,
        seed=seed,
    )
    return qubit.build(exp)[1]


def test_default_off_sweet_spot_detuning_equals_delta() -> None:
    settings = _sweet_spot(0.0)
    off = {s.nominal_detuning_ueV for s in settings if s.group == "off sweet spot"}
    assert off == {48.0}


@pytest.mark.parametrize("seed", [1, 2, 3, 7])
def test_noise_shifts_frequencies_far_less_at_the_sweet_spot(seed: int) -> None:
    settings = _sweet_spot(5.0, seed)
    at = qubit.frequency_shift_ghz(settings, "sweet spot")
    off = qubit.frequency_shift_ghz(settings, "off sweet spot")
    assert at < off / 3


def test_no_noise_no_frequency_shift_and_no_deviation() -> None:
    settings = _sweet_spot(0.0)
    ideal = [dqd.p_right(s.detuning_ueV, s.delta_ueV, s.pulse_ns) for s in settings]
    for group in ("sweet spot", "off sweet spot"):
        assert qubit.frequency_shift_ghz(settings, group) == pytest.approx(0.0)
        assert qubit.deviation_from_noise_free(settings, ideal, group) == pytest.approx(
            0.0
        )


def test_deviation_is_relative_to_the_noise_free_swing() -> None:
    settings = _sweet_spot(0.0)
    off = [s for s in settings if s.group == "off sweet spot"]
    # Off by 0.1 everywhere, on a swing of (Δ/Ω)² = 1/2 at ε = Δ.
    probs = [
        dqd.p_right(s.detuning_ueV, s.delta_ueV, s.pulse_ns)
        + (0.1 if s.group == "off sweet spot" else 0.0)
        for s in settings
    ]
    assert len(off) == 12
    assert qubit.deviation_from_noise_free(
        settings, probs, "off sweet spot"
    ) == pytest.approx(0.2)
