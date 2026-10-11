# Build Plan

Work the first unchecked sprint. One branch per sprint. Each sprint ends with
`make verify` green and this file updated.

**Definition of done, every sprint:**
- [ ] Tests written before implementation, failure shown first
- [ ] New unit tests cover the happy path, each error path, and each boundary value
- [ ] `tests/regression/` extended if this sprint shipped a player-visible capability
- [ ] `make verify` green (lint + types + full test suite + regression)
- [ ] Coverage on new modules ≥ 90%, and no previously covered line newly uncovered
- [ ] `CONTRACTS.md` and `DECISIONS.md` updated
- [ ] Demoable in one command, and that command is written in the sprint notes

---

## Sprint 0 — Harness only, zero features
Fork, install, get upstream's own suite green locally. Add the `Makefile` targets above,
`tests/regression/` (empty, with a README explaining append-only), `CONTRACTS.md`,
`DECISIONS.md`. Add `.claude/settings.json` hooks. Pin a global test seed.

Done when: `make verify` passes on an untouched fork. No `stanza/` or `trainer/` code yet.
This sprint exists so that every later failure is *your* failure, not a setup problem.

- [x] Complete

**Sprint 0 notes** (branch `sprint/00-harness`)
- Demo: `make venv install verify` — from a fresh checkout to a green gate.
- Baseline: upstream `6309eef` untouched; full upstream suite green (2 upstream skips
  need QM SaaS credentials, D-010). Upstream needed version pins to pass its own lint
  and types (D-004).
- Added: `Makefile`, `constraints.txt`, root `conftest.py` (seed 12345),
  `tests/harness/` (seed, guard hook, regression-runner tests),
  `tests/regression/README.md`, `.claude/settings.json` + `.claude/hooks/guard.py`,
  `CLAUDE.md`, `CONTRACTS.md`, `DECISIONS.md`.
- New-module coverage: `conftest.py` 100%, `.claude/hooks/guard.py` 100%.
- **Before Sprint 1/2:** decide R-1 in DECISIONS.md (upstream routines call cloud ML).

## Sprint 1 — Simulator driver, pinch-off only
`stanza/drivers/simulator.py`: a class satisfying `ControlInstrument` and
`MeasurementInstrument` (`set_voltage`, `get_voltage`, `get_slew_rate`, `measure`, plus
`instrument_config.breakout_line`). Physics in `trainer/physics/pinchoff.py` as pure
functions: current through a channel vs gate voltage as a smooth turn-on curve, plus
Gaussian noise at a fixed seed.

Must load through upstream's own path: `driver: simulator` in `device.yaml` resolved by
`load_driver_class`, passing `validate_driver_protocols`.

Tests: protocol conformance; voltage bounds clamped per YAML `v_lower_bound`/
`v_upper_bound`; monotonicity of the turn-on curve; determinism at fixed seed; golden
values; `device.sweep_1d` returns correct array shapes.

Done when: upstream's `noise_floor_measurement` and `global_accumulation` routines run
unmodified against the simulator and return sane numbers.

- [x] Complete

**Sprint 1 notes** (branch `sprint/01-simulator-pinchoff`)
- Demo: `make demo-01`. Prints noise floor (~1.3 pA mean, ~11 pA std) and the
  channel turn-on (~0.685 V) from upstream routines on the simulator.
- Added: `stanza/drivers/simulator.py`, `trainer/physics/pinchoff.py`,
  `trainer/routines.py`, `trainer/devices/single_channel.yaml`, `trainer/demos/`,
  tests in `tests/trainer/`, regression anchor
  `tests/regression/test_sprint01_pinchoff_routines.py`.
- Coverage: simulator driver 100%, `trainer/` 100%.
- Owner review: out-of-range voltages are **rejected** like real hardware, not
  silently clamped (D-015).

## Sprint 2 — Full device physics
Extend to a constant-interaction model: cross-capacitance matrix between gates, Coulomb
blockade peaks on the sensor plunger, gate-to-gate leakage, double-dot honeycomb in 2D.
`trainer/physics/` stays pure functions; the driver only composes them.

Tests: peak spacing and count match the capacitance parameters; cross-talk shows up as
the predicted peak shift; 2D sweep produces the expected honeycomb topology; leakage
appears only on gates configured leaky; all golden-valued.

Done when: `find_sensor_peak`, `find_stable_sensor_peak`, `run_compensation`, `leakage_test`,
`reservoir_characterization`, and `dqd_search` all run unmodified and succeed. **This is
the project's regression anchor** — every one of those gets a permanent regression test.

- [x] Complete

**Sprint 2 notes** (branch `sprint/02-device-physics`)
- Demo: `make demo-02`. The full upstream tune-up on
  `trainer/devices/dqd_with_sensor.yaml` (hole device, DQD + charge sensor):
  health checks on both sides, Coulomb peak at PB ≈ −0.629 V, compensation
  gradients PA1 −0.097 / PA2 −0.151 / BA1 −0.049 V/V (configured ratios −0.10 /
  −0.15 / −0.05), and a double dot found at the first barrier setting.
- Regression anchors: `tests/regression/test_sprint02_device_physics_anchors.py`, one
  test per routine, checked against simulator ground truth.
- Anti-degenerate checks: no sensor dot → `find_sensor_peak` fails; a leaky gate pair
  shrinks the safe range; merged dots are not reported as a double dot.
- Added: `trainer/physics/{coulomb,leakage,noise}.py`, `trainer/clock.py`,
  `trainer/models/`, `trainer/lab.py`, `trainer/workflows.py`, extended simulator.
- Coverage: 99% over `trainer/` and the simulator driver.
- Plan wording: `dqd_search` is upstream's `run_dqd_search` (R-2).

## Sprint 3 — Headless API
`trainer/api/`: FastAPI over `RoutineRunner`. List device pads, list routines, set
voltages, run a routine with parameter overrides, stream logged data (websocket off the
`DataLogger`). No physics, no game logic, no UI.

Tests: contract test per endpoint, schema-validated; bad parameters rejected with 422 not
500; a routine raising mid-run leaves the device in a defined state; websocket delivers
points in order with no loss.

Done when: `curl` can run `find_sensor_peak` end to end and watch the data stream.

- [x] Complete

**Sprint 3 notes** (branch `sprint/03-headless-api`)
- Demo: `make demo-03`. Starts the API, then `trainer/demos/sprint03.sh` uses curl to
  run the side-B health checks and `find_sensor_peak`, watching the run live over SSE.
  `make serve` runs the API alone.
- Contract: CONTRACTS C-13. Tests: `tests/trainer/api/` (every endpoint, 422 cases,
  failure restore, busy 409, ordered/lossless websocket and SSE, real uvicorn + curl).
- New runtime deps (approved, D-012): `requirements-trainer.txt`.

## Sprint 4 — Minimal UI, no game
`frontend/`: one device, sliders per gate, a live 1D trace, a "run routine" button.
Ugly is fine. This sprint proves the data path, nothing else.

Tests: component tests on state handling; one end-to-end test driving a sweep and
asserting rendered points; reconnect behavior when the socket drops.

- [x] Complete

**Sprint 4 notes** (branch `sprint/04-minimal-ui`)
- Demo: `make demo-04`, then open http://127.0.0.1:5173. It opens a session on the
  double dot, with a slider per gate and contact, a run panel and a live trace.
- Tests: Vitest (stream reconnect/dedupe/gap, trace reducer, sliders' one-in-flight
  queue and revert, run panel validation, chart, App wiring with fake client and
  socket); Playwright (UI-driven `global_accumulation`, 200 rendered points; slider →
  server PUT). All run in `make verify`.

## Sprint 5 — 2D visualization
Charge-stability-diagram heatmap, pan/zoom, crosshair readout, clicking a point to set
both gate voltages.

Tests: colormap scaling against golden data; click-to-voltage mapping accurate at edges
and after zoom; render budget on a 100×100 sweep.

- [x] Complete

**Sprint 5 notes** (branch `sprint/05-2d-visualization`)
- Demo: `make demo-04`, open http://127.0.0.1:5173. Set side A into the double-dot
  regime (RA1/RA2 −1.7, BA0/BA2 −0.9, BA1 −0.75, IN_A 1 mV), then "Measure map" for
  PA1 × PA2 over −0.66…−0.58 V. Hover for the crosshair, scroll to zoom, drag to pan,
  double-click to reset, click to set both plungers.
- Backend: the `charge_stability_diagram` trainer routine (a thin wrapper over
  upstream's `Device.sweep_2d`) runs via `RoutineRunner` and streams every point.
- Tests: viridis colormap golden values and robust limits; viewport edges, zoom and pan;
  map accumulator (10k points); heatmap readout, click at the edges and after zoom,
  drag vs click; 100×100 render < 16 ms (unit) and < 50 ms on a real canvas (e2e).

## Sprint 6 — First level
`trainer/game/`: a `Level` model (objective, concept taught, success predicate, scoring,
hints) and one level wrapping `find_sensor_peak` — "find the Coulomb peak." Scoring on
measurement count and accuracy.

Tests: success predicate true for a correct solution, false for near-misses; score
monotonic in accuracy; the level is beatable headlessly; **it is not beatable by a
degenerate strategy** (write that test explicitly).

Done when: a human can play it start to finish in a browser.

- [x] Complete

**Sprint 6 notes** (branch `sprint/06-first-level`)
- Demo: `make demo-04`, open http://127.0.0.1:5173, click **Start level** on "1. Find
  the Coulomb peak", take hints, run `find_sensor_peak` from the run panel, **Submit**.
- Judge (ground truth via the simulator's read-only oracle): sensor dot blockaded
  (1 − openness ≥ 0.6), bias on, and sensitivity |dI/dV_PB| ≥ 70% of the best flank
  within ±30 mV. Score = 1000 × accuracy × efficiency (budget 2500 readings).
- Measured: `find_sensor_peak` 97% accuracy (874 pts), `find_stable_sensor_peak` 95%;
  random plunger guesses win 2.3% (300 trials); peak centre, valley, no bias and open
  dot all fail with specific feedback.
- Regression: `tests/regression/test_level_01_coulomb_peak.py`. E2E:
  `frontend/e2e/level1.spec.ts` (played through the UI).

## Sprint 7 — Levels 2 and 3
Sensor compensation, then double-dot search. Each gets its own regression test. Sprint 6's
level must still pass unchanged.

- [x] Complete

**Sprint 7 notes** (branch `sprint/07-levels-2-3`)
- Demo: `make demo-04`, open http://127.0.0.1:5173, choose a level in the **Level**
  picker. Level 2 "Compensate the sensor": run `run_compensation`, read the gradient in
  the Result panel, step PA1 by ≥ 25 mV, move PB by gradient × ΔPA1. Level 3 "Find the
  double dot": run `run_dqd_search`; its square appears on the map; click a bright
  triple point.
- Measured: L2 intended 94% (941 pts), uncompensated fails, random PB 5%. L3 intended
  89% (889 pts), random points in the found square 0%; merged dots, no bias and plateau
  points fail with feedback.
- Regression: `tests/regression/test_level_02_compensate_sensor.py`,
  `test_level_03_double_dot.py`; Level 1's regression and e2e tests unchanged and green.
  E2E: `frontend/e2e/level2.spec.ts`, `level3.spec.ts` (both played in the browser).

## Sprint 8 — Progression
Level select, unlocking, persisted progress, hint system, post-level explanation of the
physics. All earlier levels still pass.

- [x] Complete

**Sprint 8 notes** (branch `sprint/08-progression`)
- Demo: `make demo-04`, open http://127.0.0.1:5173, enter a name and click **Save my
  progress**. Levels 2–3 show 🔒 until the previous level is completed; ✓ and best score
  appear after a win; progress survives a reload and a server restart
  (`--progress-file`, default `~/.stanza-trainer/progress.json`). Without a name the app
  is in free play: everything open, nothing saved.
- Hints cost 10% of the score each and are recorded per player. After submitting, each
  level shows "Why it works", including numbers from the player's own device (e.g.
  Ec/α = 20.0 mV for the sensor; true vs measured compensation gradient).
- All earlier levels' regression and e2e tests pass unchanged. New: progress store
  (persistence, unlocking, corrupt-file refusal, concurrency), API (403 locked, 422 bad
  player, restart), UI (picker locks, explanation), e2e progression across a reload.

---

## Hackathon — Qollab × IonQ submission

Goal: a Qiskit project on Qollab, built in the window, that turns the trainer's double
dot into a charge qubit (D-065 to D-070, C-22).

- [x] `qollab/` project: physics (`dqd.py`), circuits (`qubit.py`), report, `main()`
- [x] Tests for physics, circuits, one-job runs and Qollab's file/README rules
- [x] README project page with prior-work and AI-use disclosure and attribution
- [x] Fix the trainer frontend's intermittent render loop
- [ ] Upload and publish on Qollab; run on the built-in and IonQ simulators (author)
- [ ] 2–3 minute demo video on YouTube, linked from the README (author)
- [ ] Public MIT repository and team submission before 2026-10-11 19:00 ET (author)

## Backlog, not scheduled
Multiplayer leaderboards; instructor dashboard; a real-hardware mode that swaps the
simulator for a `qdac2`; exporting a student's session as a Stanza notebook.

## Explicitly out of scope
Rewriting upstream routines. Hosting. Accounts and auth. Mobile.
