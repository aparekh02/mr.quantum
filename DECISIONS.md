# Decisions log

Newest last. Each entry: what, why, and what would make us revisit it.

## Sprint 0 — harness (branch `sprint/00-harness`)

**D-001 Repo root is the `stanza/` fork, attached to upstream history.**
The supplied `stanza/` folder had no `.git`. Its working tree was byte-identical to
`upstream/main` at `6309eef` (2026-01-09), so we `git init`, added
`upstream = https://github.com/conductorquantum/stanza.git`, and `git reset` onto
`upstream/main` without touching files. Result: `main` = upstream, rebaseable.
No `origin` remote yet; add the team fork when one exists.
*Amended:* the fork was then flattened so `educational/` is the single repo root
(upstream's `stanza/` package, `tests/`, `pyproject.toml` sit directly in it, next to our
`trainer/` later). No nested repos. History and the upstream remote are unchanged, so
rebasing on upstream still works; the venv was rebuilt because it embeds absolute paths.

**D-002 Python 3.12 via uv-managed CPython, not Homebrew.**
Homebrew's 3.11 and 3.12 on this machine return an empty `platform.mac_ver()`, which
crashes pip's truststore import, so no venv can install packages. `make venv` uses
`uv venv --managed-python --python 3.12`. 3.12 matches upstream CI and pre-commit's
`default_language_version`. uv is a dev tool, not a project dependency.
Revisit if Homebrew fixes it — any working 3.12 is fine.

**D-003 `ruff format`, not Black.**
The pasted CLAUDE.md said `black --check .`, but upstream's CI (`scripts/lint.sh`) and
`.pre-commit-config.yaml` use `ruff format`. Running both lets pre-commit and the gate
disagree. Black stays in upstream's `dev` extra, unused by us.

**D-004 `constraints.txt` pins dev and transitive versions at upstream's commit date.**
With the latest releases, untouched upstream fails its own gate: ruff 0.16 adds UP042
(6 errors), mypy 2.4 and newer `conductorquantum`/numpy 2.5 stubs (py3.12-only syntax
checked as 3.11) add 5+ errors. Resolving with `uv pip compile --exclude-newer 2026-01-10`
makes upstream green with zero edits. These pin versions of already-chosen packages; no
new dependency. **Refresh this file whenever we rebase on a newer upstream.**

**D-005 `qm` extra is installed.**
Upstream's CI installs `.[dev,test,qm,routines,notebook]` (`requirements-test.txt`), and
`tests/test_opx_cloud_sim/conftest.py` imports `qm`. Without it upstream's suite cannot
even collect.

**D-006 Gate scope mirrors upstream CI, plus our paths.**
Lint: `stanza tests scripts conftest.py .claude/hooks` (+`trainer` once it exists);
`cookbooks/` excluded as upstream does. mypy: `stanza` (+`trainer`), plus our
`conftest.py` and guard hook. Tests are not type-checked, matching upstream.

**D-007 Global test seed lives in a new root `conftest.py`.**
`tests/conftest.py` is upstream, so we do not edit it. A root conftest applies to the
whole suite. Seed `12345`. Upstream's suite was re-run with it: still green.

**D-008 Guard hook enforces the mechanical rules.**
See CONTRACTS C-4. Limitation: it sees only file-editing tools, not edits made via Bash
(`sed`, heredocs). Escape-hatch detection counts occurrences, so moving an existing
marker is fine but adding one is not.

**D-009 `make regression` and the empty suite.**
pytest exits 5 when it collects nothing. That passes only while `tests/regression/` holds
no `test_*.py`, so the suite can never silently go empty after Sprint 1+.

**D-010 Baseline has 2 upstream skips.**
`tests/test_opx_cloud_sim/test_opx_cloud_sim.py` skips 2 tests without
`QM_SAAS_EMAIL`/`QM_SAAS_PASSWORD`. These are upstream's own skips, not ours; they run if
those credentials are put in `.env`.

### Open risks raised in Sprint 0 (owner decides before the named sprint)

**R-1 (blocks Sprint 2 and 6): several target routines call Conductor Quantum's cloud ML.**
`find_sensor_peak` / `find_stable_sensor_peak` (`charge_sensor/utils/sweeps.py`) and
`run_dqd_search` (`dqd_search/routine.py`, `utils.py`) call
`ctx.resources.models_client.models.execute(...)` for Coulomb-peak classification,
peak detection and charge-transition classification. "Run unmodified and succeed against
the simulator" therefore needs either (a) a real API token and network in tests and the
classroom, which costs non-determinism and an external dependency, or (b) a local
test-double `models_client` registered as a resource. Option (b) leaves upstream code
unmodified, but the ML decisions are then ours, not upstream's. Pedagogy and
determinism both hinge on this choice.

**R-2 (Sprint 2 wording):** PLAN.md says `dqd_search`; upstream exports `run_dqd_search`
and `run_dqd_search_fixed_barriers`.

## Owner decisions taken before Sprint 1 (2026-10-09)

**D-011 R-1 resolved: local stand-in `models_client`.** `trainer/` will provide a
deterministic, offline client with the same `.models.execute(model=..., data=...)` shape,
registered as the `models_client` resource. Upstream routine code stays unmodified.
Implemented in Sprint 2.

**D-012 Sprint 3 may add FastAPI + uvicorn**, declared in our own requirements file, not
in upstream's `pyproject.toml`.

**D-013 Frontend: React + Vite + TypeScript**, Vitest + Testing Library for components,
Playwright for end-to-end.

**D-014 Each green sprint branch is merged into local `main`**, and the next sprint
branches from `main`. Nothing is pushed.

## Sprint 1 — simulator driver, pinch-off only (branch `sprint/01-simulator-pinchoff`)

**D-015 Out-of-range voltages are rejected, not silently clamped.** PLAN.md says "voltage
bounds clamped per YAML". Upstream's `ControlChannel` (used by the real QDAC2 driver)
raises `ValueError` when a set point is outside `v_lower_bound`/`v_upper_bound`, and
`Device` re-raises it as `DeviceError`. The simulator reuses that channel, so a student
sees exactly what a real rig does, and the stored voltage never leaves the bounds. We
read "clamped" as "held within bounds". Flagged for the owner; switching to silent
clamping is a one-line change.

**D-016 Simulator is one `GENERAL` instrument.** Physics needs the gate voltages to
compute current, so control and measurement must be one object. `device_from_config`
treats a `GENERAL` instrument as both. Physics parameters live as extra fields on the
YAML instrument entry (`GeneralInstrumentConfig` allows extras), because
`RoutineRunner(configs=...)` passes no driver kwargs.

**D-017 Pinch-off model.** Per-gate turn-on `T = ½(1 + tanh(p·(V − V_th)/w))`, the
Darulová et al. (2019) form that upstream's own `fit_pinchoff_parameters` fits;
`p = +1` for electrons, `−1` for holes. Gate conductances `g_max·T` add in series with a
contact resistance: `I = V_sd / (R_s + Σ 1/g_i)`. Current is positive into the DRAIN and
negative at the SOURCE. Gaussian noise comes from the simulator's own
`np.random.Generator(seed)`. Gates read only noise until Sprint 2 adds leakage.

**D-018 YAML numbers need a signed exponent or a decimal form.** PyYAML (YAML 1.1)
reads `1.0e4` as a string. Pydantic coerces it in the driver, but other readers don't.
Device files write `10000.0` or `1.0e+4`.

**D-019 Built-ins are re-registered explicitly.** Upstream tests call
`clear_routine_registry()`, so anything relying on "imported once" breaks depending on
test order. `trainer.routines.register_builtin_routines()` (C-7) is called by our
fixtures, demos and (later) the API.

**D-020 Sprint 1 supplies `leakage_test`'s result for `global_accumulation`.** That
routine reads `max_safe_voltage_bound` from a prior `leakage_test`. Leakage physics is
Sprint 2, so Sprint 1 tests store `{max: 1.5, min: -1.5}` via
`runner.results.store`, upstream's public API. Sprint 2 replaces this with the real
routine chain.

**D-021 Sprint 1 regression anchor added.** The plan only requires regression tests
for shipped levels and the Sprint 2 anchors. Sprint 1's done-criterion is cheap to keep
forever, so it has one too: `tests/regression/test_sprint01_pinchoff_routines.py`.

## Sprint 2 — full device physics (branch `sprint/02-device-physics`)

**D-022 Sprint 2's device is a hole (p-type) device.** Upstream's charge-sensor routines
sweep `np.arange(saturation, cutoff, window)`, which is empty unless saturation < cutoff,
i.e. a hole device. Upstream's own fixtures use gate bounds −3…0 V and turn-on near
−0.8 V. `trainer/devices/dqd_with_sensor.yaml` follows that convention. The Sprint 1
electron channel stays as it is.

**D-023 Constant-interaction model (trainer/physics/coulomb.py).** Each dot *i* has
charging energy `Ec_i` (eV), lever arms `α_ig` (eV/V) to every gate (the
cross-capacitance matrix) and a charge offset `ν_i`. Induced charge
`n0_i = p·Σ_g α_ig V_g / Ec_i + ν_i` (`p = −1` for holes). Energy
`E(n) = ½ (n−n0)ᵀ U (n−n0)` with `U_ii = Ec_i` and `U_ij` = mutual charging energy.
Dots in one channel are enumerated jointly with Boltzmann weights (n ≥ 0);
cross-channel coupling (sensor ↔ DQD) is mean-field on ⟨n⟩. Peak spacing on gate *g* is
`Ec_i/α_ig`, and a control gate shifts a dot's peaks by `−α_ic/α_ip` (the quantity
`run_compensation` measures).

**D-024 Transport through dots is phenomenological but qualitatively faithful.**
Resonance `P = Σ_n sech²(μ_n / 2kT_eff)` (thermal Coulomb peak, the sech² form upstream
fits). The dot "openness" `o` is the product of the turn-ons of its plunger and barriers.
Dot transmission `F = o + (1−o)·P`: blockade emerges as the dot pinches off and washes
out when it is open. This is why Coulomb oscillations appear near the plunger's cutoff,
which upstream's `find_sensor_peak` relies on. Lifetime broadening:
`kT_eff = kT + Γ·o`. Two dots in one channel: `F = (1−m)·F1·F2 + m·F_merged`, where
`m = T_inner⁴` merges the dots as the inner barrier opens. The `o·P` cross terms draw
the honeycomb edges (cotunnelling-like lines); `P1·P2` makes the triple points. Channel
current = `I_series(segments) · Π F`.

**D-025 Gate leakage (trainer/physics/leakage.py).** Configured links only:
`I = sign(ΔV)·max(0, |ΔV| − V_onset)/R` between two gates or a gate and ground.
Unconfigured gates read noise only.

**D-026 Charge noise.** Per-dot Ornstein–Uhlenbeck offset on `ν` (std in units of e,
correlation time τ), stepped exactly over elapsed simulated time. White current noise
on every reading as in Sprint 1.

**D-027 Virtual time (trainer/clock.py).** Upstream routines call `time.sleep`
(health checks: a hard-coded 10 s per gate; `find_stable_sensor_peak`: a 120 s hold
loop on `time.time()`). The simulator owns a `VirtualClock`; each reading advances it by
`measurement_duration`. `virtual_time(clock)` swaps the `time` attribute in upstream's
routine modules for a proxy whose `sleep`/`time`/`monotonic` use that clock. Routine
code is unmodified; only the wall clock is simulated. Tests and the trainer always run
built-ins inside `virtual_time`. One sleep cannot be patched this way:
`many_window_barrier_sweep` does `import time` inside the function. It uses the
`settling_time_s` routine parameter, which our configs set to 0.

**D-028 Local models client (trainer/models/).** It mirrors the four model ids
upstream calls (`coulomb-blockade-classifier-v3`, `coulomb-blockade-peak-detector-v2`,
`charge-stability-diagram-binary-classifier-v2-16x16`, `…-v1-48x48`) with
deterministic signal processing on the measured data only. It never reads simulator
ground truth, so a level can't be beaten by information a real lab wouldn't have.

**D-029 Cross-channel coupling acts on occupation, not on (n − n0).** Inside one
channel (the DQD) dots interact through the full CI energy, which gives the correct
honeycomb geometry. Between channels (sensor ↔ DQD), a dot's induced charge shifts by
`−Σ Em·⟨n_j⟩/Ec`, i.e. only real charges are sensed. Otherwise an empty control dot whose
gate-induced charge goes strongly negative would drag the sensor as if it held ~10
charges. Consequences: a gate moves a sensor peak by exactly `−α_s,g/α_s,plunger`, the
gradient `run_compensation` should recover, and each extra hole on a control dot steps
the sensor peak by `−Em/α_s,plunger`.

**D-030 Turn-on widths are broad (0.15–0.20 V), as in real devices.** Upstream's
`fit_pinchoff_parameters` bounds the tanh slope at |b| ≤ 20 in normalised voltage, so it
cannot fit a turn-on narrower than ~10% of the swept range. Upstream also takes the
initial slope sign from array order, which is wrong for sweeps toward negative voltage
(R-4), so transitions near the start of a sweep fail. Reservoir thresholds therefore sit
mid-range (−0.80 V). Sharp turn-ons broke every health check.

**D-031 Depleted dots exert no indirect pull.** In the CI coupling term a partner's
induced charge is floored at 0 (`joint_occupation`). A depleted region is not an island;
its gate still acts through direct lever arms. Without the floor, PA2 at +0.3 V pushed D1
by ~2.8 charges.

**D-032 Occupations are solved exactly and jointly over all dots.** An earlier two-pass
mean-field was not self-consistent: the sensor's ~60 holes shifted the control dots by
~3.8 charges between passes.

**D-033 Compensation in the standard workflow uses `zero_control_side=True`.**
Finger-gate characterization leaves the last gate at the end of its sweep (a bound), and
gradients around 0 V on the control side isolate capacitive cross-talk.

### Open risks raised in Sprint 2

**R-3 Upstream group handling.** `RoutineRunner.run(group=...)` leaves the group
resource set for every later run, and `run_dqd_search` reads unsuffixed health-check
results. Bridged by `SimulatedLab.clear_group()` / `alias_group_results()`; upstream is
untouched.

**R-4 Upstream pinch-off fit is fragile** for edge transitions in decreasing sweeps
(see D-030). Worth an upstream issue; not ours to patch.

**R-5 RANSAC flags 11–23 of 40 compensation samples as outliers** per gate on the
simulator, although the fitted gradients are within 3% of the configured ratios. Likely
charge noise plus fit jitter on narrow windows. To revisit before a compensation level
(Sprint 7).

## Sprint 3 — headless API (branch `sprint/03-headless-api`)

**D-034 Streaming taps the DataLogger, not the instrument.** `StreamingDataLogger`
subclasses upstream's `DataLogger` and wraps each new session's public
`log_measurement`, `log_sweep` and `sweep().append/end` on the instance. Upstream files
are still written. Live per-point events exist only where upstream streams per point
(`sweep_1d`); `sweep_nd` arrives as one `sweep` event when it finishes.

**D-035 Ordered, lossless delivery via a sequence-numbered log.** Every session event
goes into one append-only `EventLog`; HTTP, SSE and websocket readers all read "after
cursor". Reconnecting with the last `seq` loses nothing.

**D-036 SSE alongside the websocket.** The done-criterion is "curl can … watch the data
stream"; this curl build has no websocket support, so `GET …/events/stream` serves the
same stream as server-sent events (`curl -N`).

**D-037 One routine executes at a time per process.** Virtual time patches module
globals, so runs are serialised across sessions by a global lock (per-session runs
return 409 while busy). Fine for one classroom server; parallel sessions would need
one process per session (R-6).

**D-038 Defined state after failure = the voltages the run started from.** On any
exception the session jumps back to its pre-run snapshot and reports
`restored_voltages`. Results registries are untouched; failed runs store nothing.

**D-039 Parameter validation from routine signatures.** A pydantic model built from
`inspect.signature` + type hints rejects missing, mistyped and unknown parameters (upstream
routines accept `**kwargs`, so typos would otherwise be silently ignored).

**D-040 Test-only routines re-register per test.** Upstream tests clear the global
routine registry; test routines registered at import vanished and a stream test waited
forever. They now live in `tests/trainer/api/routines_for_tests.py`, registered by an
autouse fixture, and stream tests assert the run was accepted before waiting.

### Open risks raised in Sprint 3

**R-6 Single-process concurrency.** See D-037.
