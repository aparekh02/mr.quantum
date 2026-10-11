# From Tune-Up to Qubit

Before a semiconductor spin or charge qubit can compute anything, someone has to find it: sweep gates, find Coulomb peaks, park a charge sensor, compensate cross-talk and locate a double dot in a honeycomb charge-stability diagram. This project takes the double dot that students tune in the Stanza Tune-Up Trainer and runs it as a charge qubit with Qiskit, so the gate voltages they learned to set become the qubit's Hamiltonian, and its measured oscillations come back through the same charge sensor.

## What it shows

Theme: **Quantum Unlocked**. The hard topic is how a gate-defined quantum dot becomes a qubit, and why tune-up choices (inner barrier, detuning, sensor operating point) decide whether that qubit works.

The double dot's two lowest charge states, charge on the left dot |L⟩ or the right dot |R⟩, form a qubit with Hamiltonian H = (ε σz + Δ σx) / 2. The detuning ε is set by the plungers PA1 and PA2 along the honeycomb's interdot line; the tunnel splitting Δ = 2 t_c is set by the inner barrier BA1. Both are computed from the same device the trainer simulates (charging energies, lever arms, barrier turn-on).

Three experiments, chosen in **Run settings**:

- **detuning_sweep**: a fixed pulse at many detunings. The charge only crosses near ε = 0, and the resonance width measures Δ, i.e. how open the inner barrier is.
- **time_sweep**: a fixed detuning for longer and longer pulses. The charge oscillates between the dots at Ω/h = sqrt(ε² + Δ²)/h: the qubit's frequency.
- **sweet_spot**: the same oscillation at ε = 0 and at ε = Δ, with frozen charge noise on every qubit. At ε = 0 the frequency is insensitive to noise to first order, so the qubits keep their frequency and the data stay on the noise-free curve; off it, each qubit's frequency shifts and the data scatter away. The run prints both numbers for each group.

The run prints the device numbers, an ASCII charge map with your settings marked on the interdot line, a table of every qubit's result as charge-sensor current, a fit of the physics back out of the data, and a short explanation.

## How to run

1. Open this page in Chrome, Edge, Brave, Opera or Firefox 153+. Safari and iPhone/iPad cannot run Qollab projects.
2. Press **Run on Qollab** (top right). No sign-in is needed for the free local simulators.
3. Under **Run settings**, keep the defaults the first time. `experiment` is `detuning_sweep`, `time_sweep` or `sweet_spot`; `inner_barrier_V` is the BA1 voltage (−0.80 to −0.95 V keeps the dots separate); `detuning_ueV` is ε in µeV; `pulse_ps` is the pulse length; `charge_noise_ueV` adds quasi-static noise; `sensor_on_flank` parks the charge sensor on a Coulomb peak's flank (true) or its top (false); `qubits` is how many settings to measure at once (2 to 24); `shots` and `seed` as usual.
4. Pick **Built-in simulator (24q)** under *Locally Run Simulators* and press **Run**.
5. Expected: within a few seconds the console shows the Device section, the charge map, a 16-row results table with bars, and "fitted Δ ≈ 47 µeV (true Δ = 47.9 µeV)".
6. On IonQ's simulator: run again and pick IonQ's simulator under *Remotely Run Simulators*. The project sends exactly one job per run, so it works there too.

Things to try: set `inner_barrier_V` to −0.95 and then −0.80 and watch the resonance width follow the tunnel coupling; run `time_sweep` with `pulse_ps` 300; run `sweet_spot` with `pulse_ps` 300 and `charge_noise_ueV` 5, then 15, and compare the two groups; set `sensor_on_flank` to false and see the readout contrast collapse; set `inner_barrier_V` to −1.6 and read the warning about merged dots.

Locally: `pip install -r requirements.txt`, then `python -c "from main import main; main()"`.

## How it works

Each qubit of one circuit is an independent copy of the charge qubit at its own setting. Evolving for a pulse τ under H is a rotation by θ = Ω τ / ħ about the axis n = (Δ, 0, ε) / Ω, built as Ry(φ) Rz(θ) Ry(−φ) with φ = atan2(Δ, ε). Starting from |L⟩, the probability of finding the charge on the right dot is (Δ/Ω)² sin²(θ/2). The tests check every qubit's exact statevector against that formula.

Because every setting is a separate qubit, a whole sweep is one circuit and one job. That is what IonQ backends accept per run, and it means the measured counts carry the whole experiment.

| Concept | In the circuit | Effect you see |
|---|---|---|
| Detuning ε (plungers PA1/PA2) | tilt φ of the rotation axis, rotation speed Ω | resonance centred at ε = 0 |
| Tunnel coupling t_c (barrier BA1) | Δ = 2 t_c in Ω and φ | resonance width, oscillation frequency at ε = 0 |
| Pulse length τ | rotation angle θ = Ω τ / ħ | oscillation in time |
| Charge noise | a random ε offset per qubit (seeded) | dephasing off the sweet spot |
| Charge-sensor readout | maps P(R) to sensor current | contrast depends on where the sensor is parked |

The device numbers come from the trainer's `dqd_with_sensor.yaml`: charging energies 1.6 meV, mutual charging energy 0.35 meV, lever arms 0.080 and 0.020 eV/V, BA1 threshold −0.85 V with 0.15 V width. The fully open tunnel coupling (40 µeV) is the one parameter added here.

## What's new here

Novelty category: an **original educational contribution**. Tutorials teach qubits as abstract two-level systems, and device tune-up is taught, if at all, from papers. This connects the two: the voltages a student sets while tuning a double dot become the parameters of a Qiskit circuit, and the qubit's behaviour (resonance width, frequency, sweet-spot protection, readout contrast) is explained in terms of those tune-up choices. A second, technical contribution is packing a whole parameter sweep into one circuit of independent qubits, so a full experiment fits the one-job-per-run limit of IonQ backends.

## Make it yours

- Change the device: edit the constants at the top of `dqd.py` (charging energies, lever arms, BA1 turn-on, `T_MAX_UEV`).
- Add an experiment: add a kind to `KINDS` in `qubit.py`, give it settings in `_nominal`, and an explanation in `EXPLAIN` in `main.py`.
- Add physics: Landau–Zener sweeps or a two-axis (ε, τ) chevron fit naturally into `build`, one qubit per setting.

## Built during the hackathon / prior work

Prior work, before 2026-10-09 19:00 ET, disclosed: the Stanza Tune-Up Trainer (a physics simulator for gate-defined quantum dots, a FastAPI service, a React frontend and three tune-up levels) built on top of Stanza by Conductor Quantum (MIT License). It was built on 2026-10-09 with AI assistance (Claude Code). This Qollab project reuses only its device parameters and turn-on model, copied into `dqd.py`.

Built during the hackathon window: everything in this Qollab project (`main.py`, `dqd.py`, `qubit.py`, `report.py`, this page) and its tests, plus a render-loop fix in the trainer's frontend. AI-tool use: written with Claude Code, reviewed and tested by the author.

## Accessibility

The output is plain text in the console, so screen readers can read it. Every bar in the results table also has its value printed as a number, and nothing is conveyed by colour alone. The charge map uses letters (L, R, ., #, *) rather than colours, with a legend in its heading. All settings are typed into the standard Run settings form, which works from the keyboard.

## License

MIT (see `LICENSE`). Stanza is © 2025 Conductor Quantum, MIT License.

This effort is supported by Qollab & IonQ
