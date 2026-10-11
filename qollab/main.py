"""From tune-up to qubit: the double dot you tune in the Stanza Tune-Up Trainer, run as a charge qubit with Qiskit. On Qollab: press Run on Qollab, pick a simulator, press Run."""

import builtins
from typing import Any

import dqd
import qubit
import report
from qiskit import transpile

# Qollab pre-creates `backend` from the Select QPU dialog: use it, never replace it.
# Off Qollab (local development only), fall back to Qiskit's built-in simulator.
backend: Any = globals().get("backend", getattr(builtins, "backend", None))
if backend is None:
    from qiskit.providers.basic_provider import BasicSimulator

    backend = BasicSimulator()

EXPLAIN = {
    "detuning_sweep": (
        "Each qubit got the same short pulse at a different detuning ε. The charge only "
        "tunnels across fully near ε = 0, where the two dots' levels anticross; the width "
        "of that resonance is the tunnel splitting Δ = 2 t_c, which the inner barrier "
        "sets. Open BA1 (more negative) and the resonance widens; close it and it narrows."
    ),
    "time_sweep": (
        "Each qubit sat at the same detuning for a longer pulse. The charge oscillates "
        "between the dots at the qubit frequency Ω/h = sqrt(ε² + Δ²)/h: a charge qubit. "
        "Off ε = 0 it oscillates faster but never fully crosses."
    ),
    "sweet_spot": (
        "Half the qubits sat at ε = 0, half off it, each with its own frozen sample of "
        "charge noise. At ε = 0 the frequency depends on ε only to second order (a "
        "'sweet spot'), so the noisy qubits still oscillate together; off it they drift "
        "apart and the oscillation washes out. That is why qubits are parked at sweet spots."
    ),
}


# fmt: off
def main(experiment: str = "detuning_sweep", inner_barrier_V: float = -0.88, detuning_ueV: float = 0.0, pulse_ps: float = 40.0, charge_noise_ueV: float = 0.0, sensor_on_flank: bool = True, qubits: int = 16, shots: int = 1000, seed: int = 7):
# fmt: on
    t_c = dqd.tunnel_coupling_ueV(inner_barrier_V)
    delta = 2.0 * t_c
    print(report.heading("Device"))
    print(
        f"Inner barrier BA1 = {inner_barrier_V:+.3f} V  →  tunnel coupling t_c = {t_c:.1f} µeV, Δ = 2t_c = {delta:.1f} µeV"
    )
    print(
        f"Qubit frequency at the sweet spot: {dqd.qubit_frequency_ghz(0.0, delta):.2f} GHz. Detuning: {dqd.detuning_ueV_per_mV():.0f} µeV per mV along +PA1/−PA2."
    )
    if not dqd.dots_separate(inner_barrier_V):
        print(
            f"Warning: BA1 is so open that the dots merge ({dqd.merge_factor(inner_barrier_V):.0%}): the two-level charge-qubit picture breaks down. Try BA1 between −0.80 and −0.95 V."
        )

    exp = qubit.Experiment(
        kind=experiment,
        qubits=qubits,
        delta_ueV=delta,
        detuning_ueV=detuning_ueV,
        pulse_ps=pulse_ps,
        noise_ueV=charge_noise_ueV,
        seed=seed,
    )
    try:
        circuit, settings = qubit.build(exp)
    except ValueError as error:
        print(f"Cannot run this experiment: {error}")
        return

    per_mv = dqd.detuning_ueV_per_mV()
    marks = [
        (s.nominal_detuning_ueV / per_mv / 2, -s.nominal_detuning_ueV / per_mv / 2)
        for s in settings
    ]
    print(
        report.heading(
            "Charge map (PA1 → , PA2 ↑, ±12 mV; L/R = charge on left/right dot, * = your settings)"
        )
    )
    for line in dqd.charge_map(width=49, height=17, half_window_mV=12.0, marks=marks):
        print("   " + line)

    compiled = transpile(circuit, backend)
    counts = (
        backend.run(compiled, shots=shots).result().get_counts()
    )  # the one job of this run
    measured = qubit.marginals(counts, circuit.num_qubits)

    i_left, i_right = dqd.sensor_currents_nA(sensor_on_flank)
    print(
        report.heading(
            f"Experiment: {experiment}, {qubits} qubits in one circuit, {shots} shots"
        )
    )
    print(
        f"Charge-sensor readout ({'on a flank' if sensor_on_flank else 'on a peak top'}): {i_left:.3f} nA with the charge left, {i_right:.3f} nA right."
    )
    widths = [16, 6, 9, 7, 9, report.BAR]
    print(
        report.row(
            ["group", "ε µeV", "pulse ps", "P(R)", "sensor nA", "measured P(R)"], widths
        )
    )
    for s, p in zip(settings, measured, strict=True):
        current = i_left + (i_right - i_left) * p
        print(
            report.row(
                [
                    s.group,
                    f"{s.nominal_detuning_ueV:+.0f}",
                    f"{s.pulse_ns * 1000:.0f}",
                    f"{p:.3f}",
                    f"{current:.3f}",
                    report.bar(p),
                ],
                widths,
            )
        )

    print(report.heading("Analysis"))
    if experiment == "detuning_sweep":
        fitted = qubit.fit_delta_ueV(
            [s.detuning_ueV for s in settings], measured, settings[0].pulse_ns
        )
        print(
            f"From the resonance: fitted Δ = {fitted:.1f} µeV (true Δ = {delta:.1f} µeV), so t_c ≈ {fitted / 2:.1f} µeV."
        )
    elif experiment == "time_sweep":
        f_true = dqd.qubit_frequency_ghz(detuning_ueV, delta)
        step_ns = settings[-1].pulse_ns / (len(settings) - 1)
        nyquist = 0.5 / step_ns if step_ns > 0 else float("inf")
        if f_true > 0.9 * nyquist:
            longest = 0.9 * 0.5 * (len(settings) - 1) / f_true * 1000
            print(
                f"Samples too coarse to resolve the oscillation: one every {step_ns * 1000:.0f} ps (Nyquist {nyquist:.1f} GHz), but the qubit runs at {f_true:.2f} GHz. Use more qubits or pulse_ps ≤ {longest:.0f}."
            )
        else:
            f_fit = qubit.estimate_frequency_ghz([s.pulse_ns for s in settings], measured)
            print(
                f"From the oscillation: f = {f_fit:.2f} GHz (true {f_true:.2f} GHz at ε = {detuning_ueV:+.0f} µeV)."
            )
    else:
        print(f"With {charge_noise_ueV:.0f} µeV of frozen charge noise on every qubit:")
        for group in ("sweet spot", "off sweet spot"):
            shift = qubit.frequency_shift_ghz(settings, group)
            dev = qubit.deviation_from_noise_free(settings, measured, group)
            print(
                f"{group:>15}: typical frequency shift {shift:.3f} GHz; data off the noise-free curve by {100 * dev:.0f}% of its swing"
            )
    contrast = abs(i_right - i_left)
    print(
        f"Sensor contrast {contrast:.3f} nA per electron moved{'' if sensor_on_flank else ': small, because the sensor sits on a peak top (set sensor_on_flank)'}."
    )

    print(report.heading("What this shows"))
    print(EXPLAIN[experiment])
