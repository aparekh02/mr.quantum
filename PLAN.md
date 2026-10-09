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

- [ ] Complete

## Sprint 5 — 2D visualization
Charge-stability-diagram heatmap, pan/zoom, crosshair readout, clicking a point to set
both gate voltages.

Tests: colormap scaling against golden data; click-to-voltage mapping accurate at edges
and after zoom; render budget on a 100×100 sweep.

- [ ] Complete

## Sprint 6 — First level
`trainer/game/`: a `Level` model (objective, concept taught, success predicate, scoring,
hints) and one level wrapping `find_sensor_peak` — "find the Coulomb peak." Scoring on
measurement count and accuracy.

Tests: success predicate true for a correct solution, false for near-misses; score
monotonic in accuracy; the level is beatable headlessly; **it is not beatable by a
degenerate strategy** (write that test explicitly).

Done when: a human can play it start to finish in a browser.

- [ ] Complete

## Sprint 7 — Levels 2 and 3
Sensor compensation, then double-dot search. Each gets its own regression test. Sprint 6's
level must still pass unchanged.

- [ ] Complete

## Sprint 8 — Progression
Level select, unlocking, persisted progress, hint system, post-level explanation of the
physics. All earlier levels still pass.

- [ ] Complete

---

## Backlog, not scheduled
Multiplayer leaderboards; instructor dashboard; a real-hardware mode that swaps the
simulator for a `qdac2`; exporting a student's session as a Stanza notebook.

## Explicitly out of scope
Rewriting upstream routines. Hosting. Accounts and auth. Mobile.
