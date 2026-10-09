# Frozen interfaces

Other sprints depend on everything listed here. Changing an entry requires updating
every caller in the same commit **and** a note in `DECISIONS.md`.

## C-1 Test seed (root `conftest.py`) — Sprint 0

| Name | Kind | Contract |
|---|---|---|
| `TEST_SEED` | `int` constant | `12345`. The single global test seed. |
| `_pin_global_seed` | autouse fixture | Before every test: `random.seed(TEST_SEED)` and `np.random.seed(TEST_SEED)`. Safety net only — our code must not use global RNG state (CLAUDE.md rule 9). |
| `test_seed` | fixture → `int` | Returns `TEST_SEED`. Pass it to anything that takes an explicit `seed`. |
| `rng` | fixture → `np.random.Generator` | `np.random.default_rng(TEST_SEED)`, fresh per test. |

Golden values at this seed are asserted in `tests/harness/test_seed.py`. Changing the
seed invalidates every golden value in the repo.

## C-2 Make targets — Sprint 0

`venv`, `install`, `test`, `cov`, `lint`, `types`, `regression`, `verify`.
`verify` = `lint` → `types` → `test` → `regression`, stopping at the first failure.
Paths for `lint`, `types` and `cov` pick up `trainer/` automatically once it exists.
`regression` passes on an empty `tests/regression/` only while it holds no `test_*.py`.

## C-3 `tests/regression/` — Sprint 0

Append-only. One file per shipped level / anchored routine, named `test_<thing>.py`.
Existing files are never edited (the guard hook denies it).

## C-4 Guard hook (`.claude/hooks/guard.py`) — Sprint 0

PreToolUse on `Edit|Write|MultiEdit|NotebookEdit`. Decisions, in priority order:
1. `deny` — modifying an existing file under `tests/regression/`.
2. `deny` — a `.py`/`.pyi` edit that *increases* the count of type-ignore comments,
   `pytest.mark.skip/skipif/xfail`, `pytest.skip()/xfail()`, or `unittest.skip*`.
3. `ask` — any file in the `upstream/main` tree, or any new file under `stanza/` other
   than `stanza/drivers/simulator.py`.
Otherwise no output. Pure logic is `decide(...)`; tests in `tests/harness/test_guard_hook.py`.

## C-5 Simulator driver (`stanza/drivers/simulator.py`) — Sprint 1

- Loaded by upstream: `driver: simulator`, `type: GENERAL` →
  `load_driver_class("simulator")` returns `Simulator`; passes
  `validate_driver_protocols` for GENERAL, CONTROL and MEASUREMENT.
- Constructor: `Simulator(instrument_config: GeneralInstrumentConfig,
  channel_configs: dict[str, ChannelConfig])` — no other kwargs.
- Pad-name API (like QDAC2): `set_voltage(pad, v)`, `get_voltage(pad)`,
  `get_slew_rate(pad)`, `set_slew_rate(pad, r)`, `measure(pad | [pads])`,
  `instrument_config` (incl. `breakout_line`), read-only `state`.
- Out-of-bounds set points raise `ValueError` (upstream `ControlChannel`); voltage is
  unchanged. Voltages start at 0 V. Slew rate limited to [0.001, 1000] V/s by upstream.
- YAML `simulation` block (validated by `SimulationSettings`, `extra="forbid"`):
  `seed: int ≥ 0` (**required**), `carrier: electron|hole`, `noise_std ≥ 0` (A),
  `series_resistance ≥ 0` (Ω), `gates: {name: {v_threshold, width > 0, g_max ≥ 0}}`
  covering exactly the device's non-SCREEN gates. Device needs exactly one SOURCE
  and one DRAIN contact.
- Current sign: positive into DRAIN, negative at SOURCE, gates read noise only.
- RNG: one `standard_normal` draw per `measure` of one pad, from
  `default_rng(seed)`, in call order. Golden tests depend on this.
- Sprint 2 extends the `simulation` block; existing keys keep their meaning.

## C-6 Physics API (`trainer/physics/pinchoff.py`) — Sprint 1

`ELECTRON = 1`, `HOLE = -1`; `GateTurnOn(v_threshold, width, g_max)` (frozen, validated);
`turn_on(v, gate, polarity) -> [0,1]` (float in → float, array in → array);
`gate_conductance(v, gate, polarity)`; `series_conductance(gs, series_resistance)`
(0 if any segment is pinched); `channel_current(bias, g)`;
`noisy(i, noise_std, rng)` (exact when `noise_std == 0`, no draw).

## C-7 Routine registration (`trainer/routines.py`) — Sprint 1

`register_builtin_routines()` — idempotently (re)registers every name in
`stanza.routines.builtins.__all__`. Call before running built-ins; upstream code can
clear the global registry.

## C-8 Device files (`trainer/devices/`) — Sprint 1

`single_channel.yaml`: gates R1, B1, P1, B2, R2 (all with measure channels), contacts
S (SOURCE, bias, ±10 mV) and D (DRAIN, measured), electron, seed 1234. Regression
tests depend on its values; add new files rather than editing it.

## C-5a Simulator extensions — Sprint 2

Optional keys in the `simulation` block (absent → Sprint 1 behaviour):
`temperature` (kT, eV, > 0, default 4e-5), `lifetime_broadening` (eV),
`charge_noise {std (e), tau (s)}`, `channels [{name, source, drain, segments, dots,
series_resistance?}]`, `dots {name: {charging_energy, plunger, barriers, lever_arms,
charge_offset}}`, `mutual [{dots: [a, b], energy}]`, `leakage [{gates: [a, b|ground],
resistance, onset}]`. At most two dots per channel; two dots share exactly one barrier.
Driver attributes: `conduction_channels`, `dots`, `clock` (a `VirtualClock`, advanced by
`measurement_duration` per reading), `occupations()`, `transition_voltage(dot, gate, n)`.
The last two are ground truth for tests and instructors, never for routines or levels.

## C-9 Physics API additions — Sprint 2

`trainer.physics.coulomb`: `Dot`, `induced_charge`, `effective_induced_charge`,
`resonance`, `coulomb_resonance`, `thermal_occupation`, `joint_occupation`,
`dot_transmission`, `two_dot_transmission`, `merged_dot`.
`trainer.physics.leakage`: `GROUND`, `LeakageLink`, `leakage_currents`.
`trainer.physics.noise`: `ou_step`.

## C-10 Virtual time (`trainer/clock.py`) — Sprint 2

`VirtualClock` (`now`, `advance`, `sleep`); `virtual_time(clock)` context manager
patches the `time` attribute of `PATCHED_MODULES`. Not re-entrant.

## C-11 Local models (`trainer/models/client.py`) — Sprint 2

`LocalModelsClient` (resource name `models_client`, `.models.execute(model, data)` →
`.output`, `.calls`), supporting exactly the four ids in `SUPPORTED_MODELS`. Outputs:
classifiers `{classification: bool, score: float in [0, 1]}`, peak detector
`{peak_indices: list[int]}`. Data-only; never reads simulator state.

## C-12 Lab and workflows — Sprint 2

`SimulatedLab(config, base_dir)` / `.from_yaml(path, base_dir)`: `.runner`,
`.device`, `.simulator`, `.models_client`, `.history: list[RunRecord]`,
`.run(routine, **params)` (virtual time), `.clear_group()`,
`.alias_group_results(group)`, `.virtual_time()`.
`trainer.workflows`: `Step(routine, params, label, before)`, `run_steps(lab, steps,
stop_after)`, `DQD_WITH_SENSOR_TUNEUP`. The Sprint 3 API builds on these.

## C-8a `trainer/devices/dqd_with_sensor.yaml` — Sprint 2

Gates RA1 BA0 PA1 BA1 PA2 BA2 RA2 (side_A), RB1 BB0 PB BB1 RB2 (side_B), contacts
IN_A/OUT_A, IN_B/OUT_B, hole carrier, seed 2024. Regression anchors depend on it; add
new device files rather than editing it.

## C-13 HTTP API (`trainer/api/`) — Sprint 3

Served by `python -m trainer.api` (default `127.0.0.1:8765`); `create_app(devices_dir,
data_dir)` builds it. All bodies JSON; validation errors are **422** with pydantic-style
`detail`, never 500; a running session answers **409** to device changes.

| Method & path | Body / query | Response |
|---|---|---|
| `GET /health` | | `{"status": "ok"}` |
| `GET /devices` | | `[DeviceInfo{name, title}]` (one per `trainer/devices/*.yaml`) |
| `POST /sessions` | `{device}` | 201 `SessionInfo{id, device, title, groups}` |
| `GET /sessions/{id}` · `DELETE` | | `SessionInfo` · 204 |
| `GET /sessions/{id}/pads` | | `[PadInfo{name, pad_type, electrode_type, v_lower_bound, v_upper_bound, controllable, measurable, group}]` |
| `GET /sessions/{id}/voltages` | | `{pad: V}` |
| `PUT /sessions/{id}/voltages` | `{voltages: {pad: V}}` | `{pad: V}`; bounds-checked, all-or-nothing |
| `POST /sessions/{id}/measure` | `{pads: [..]}` | `{currents: {pad: A}}` |
| `GET /sessions/{id}/routines` | | `[RoutineInfo{name, parameters: [{name, type, required, default}]}]` |
| `POST /sessions/{id}/runs` | `{routine, parameters}`, `?wait=` | 202 (or 200 with `wait=true`) `RunInfo` |
| `GET /sessions/{id}/runs` · `/runs/{rid}` | `?wait=` | `[RunInfo]` · `RunInfo` |
| `GET /sessions/{id}/events` | `?after=N` | `[Event]` with `seq > N` |
| `GET /sessions/{id}/events/stream` | `?after=N&follow=&until=kind`, `Last-Event-ID` | SSE: `id: seq`, `event: kind`, `data: Event` |
| `WS /sessions/{id}/stream` | `?after=N` | one JSON `Event` per message |

`RunInfo{id, routine, parameters, status: running|succeeded|failed, result, error,
restored_voltages, first_seq, last_seq}`. Run parameters are validated against the
routine's own signature (unknown names rejected; `group`, `session_suffix` allowed;
`group` must exist). A run that fails restores the voltages it started from.

`Event{seq, time, kind, routine, name, data}`; `seq` starts at 1 and is contiguous per
session; `time` is simulated seconds. Kinds: `run_started`, `run_finished`,
`run_failed`, `sweep_point`, `sweep`, `measurement`, `analysis`, `voltages`. Clients
resume by passing the last `seq` they saw. The frontend (Sprint 4) depends on all of
this.

## C-14 Frontend (`frontend/`) — Sprint 4

- Talks only to the API at `/api` (Vite proxies HTTP and websocket to `TRAINER_API`,
  default `http://127.0.0.1:8765`).
- `src/api/client.ts` `createClient(base, fetch)`: one method per C-13 endpoint; errors
  throw `ApiError(status, detail)`.
- `src/api/stream.ts` `EventStream`: delivers events strictly in `seq` order, drops
  duplicates, reconnects after a drop or gap with `?after=lastSeq` and backoff.
- `src/state/traces.ts` `applyEvent`: `sweep_point` grows the live trace; `sweep`
  replaces it with the full data, plotted against the coordinate that moves most.
- DOM hooks the e2e tests (and later levels) rely on: sliders labelled by pad name,
  `data-testid="value-<pad>"`, `data-testid="trace"` with `data-points`,
  `data-testid="stream-status"`, `.last-run` text `<routine> succeeded|failed: …`,
  labels `Device`, `Routine`, `Parameters (JSON)`, button `Run routine`.

## C-15 `charge_stability_diagram` routine — Sprint 5

Registered by `register_builtin_routines()`. Parameters: `gate_x`, `gate_y`
(different controllable gates), `x_range`, `y_range` (two different voltages each,
either order), `points` (2…256 per axis), `measure_electrode`. Returns
`{x: [..], y: [..], current: [[..]]}` with `current[i_y][i_x]`. Calls upstream
`Device.sweep_2d(gate_y, ys, gate_x, xs, …)`, so its sweep is labelled
`[gate_y, gate_x]`.

## C-16 2D views (`frontend/`) — Sprint 5

- Upstream 2D sweeps are labelled `[outer, inner]`. The heatmap puts the **inner (fast)
  gate horizontally** and the outer gate vertically, for any 2D sweep.
- `MapAccumulator` (`src/state/maps.ts`): `apply(event)`, `latest(): MapData | null`
  (`xs`, `ys` ascending; `values` row-major, NaN where unmeasured; gates null until
  the finished `sweep` event).
- `src/viz/colormap.ts`: `colorAt(v, lo, hi)` (9-stop viridis), `limits(values, tail)`.
- `src/viz/viewport.ts`: `pixelToData`, `dataToPixel`, `zoomAt`, `pan`,
  `clampToBounds`, `fullView`; pixel (0, 0) = (min x, max y).
- DOM: `data-testid="heatmap"` (canvas, `data-cells`, `data-render-ms`),
  `data-testid="crosshair"`, panel labels `X gate`, `Y gate`, `X from (V)`, `X to (V)`,
  `Y from (V)`, `Y to (V)`, `Points per axis`, button `Measure map`;
  `main[data-session-id]`.
- Picks are clamped to the measured extent, so an edge click never steps past a bound.

## C-17 Game (`trainer/game/`) — Sprint 6

- `Level` (frozen dataclass, abstract `judge(attempt) -> Evaluation`): `id` (slug),
  `order ≥ 1`, `title`, `concept`, `objective`, `device`, `hints` (non-empty),
  `measurement_budget ≥ 1`, `setup: tuple[Step, ...]`; `public()` hides hint text.
- `score(accuracy, measurements, budget) -> int` in [0, 1000], monotonic up in
  accuracy and never rewarding extra measurements. Failed attempts score 0.
- `Evaluation{success, accuracy, score, measurements, feedback: list[str]}`.
- `Attempt.start(level, devices_dir, data_dir, reuse=None, lab=None)` runs the setup;
  `.measurements` counts readings since setup; `.next_hint()`; `.submit()` once
  (else `AttemptClosed`).
- `trainer.game.levels`: `LEVELS` in play order, `get_level(id)`. Level 1:
  `coulomb-peak`.
- Judges read only the simulator oracle (C-18), never through instrument calls.

## C-18 Simulator oracle — Sprint 6

`Simulator.reading_count` (every reading), `ideal_current(pad, overrides)` (noiseless,
no clock/RNG/count side effects, charge noise excluded), `dot_openness(dot)`, plus
Sprint 2's `occupations()` and `transition_voltage()`. Not exposed through the API.

## C-19 Level API — Sprint 6 (extends C-13)

`GET /levels` → `[LevelInfo]`; `POST /levels/{id}/attempts` → 201 `AttemptInfo{id,
level_id, session_id, status: active|submitted, measurements, hints_shown, evaluation}`
(setup already run on that session); `GET /attempts/{id}`; `POST /attempts/{id}/hints`
→ `{hint | null, hints_shown}`; `POST /attempts/{id}/submit` → `AttemptInfo` (409 if a
run is in progress or already submitted). Frontend: `LevelPanel` with buttons
`Start level`, `Show a hint`, `Submit`, `Try again`, `data-testid="measurements"` and
`"result"`.

## C-20 Levels 2 and 3 — Sprint 7 (extends C-17)

- `LEVELS = (coulomb-peak, compensate-sensor, double-dot)`, orders 1–3.
- `Level.baseline(attempt) -> dict` (ground truth recorded after setup); `Attempt.baseline`.
- `trainer.game.sensing.sensor_flank(lab, dot, plunger, measure) -> SensorFlank{accuracy,
  blockade, position: flank|top|valley, best_slope, slope}`, shared by Levels 1–2.
- Level 2 success: PA1 stepped ≥ 25 mV, bias on, blockade ≥ 0.6, flank accuracy ≥ 0.7,
  and the same Coulomb peak as at setup (floor of the sensor's induced charge).
- Level 3 success: bias on, inner barrier BA1 turn-on⁴ < 0.5, both dots change charge
  within ±25 mV, ≥ 20 pA nearby, and current within ±1 mV of the point ≥ 50% of the
  brightest within ±20 mV.
- Oracle additions (C-18): `induced_charges()`, `gate_turn_on(gate)`,
  `occupations_at(overrides)`.
- Workflows: action-only `Step("", label=..., before=...)` runs no routine.
- Frontend: `Level` picker (`<select aria-label="Level">`, one `Start level` button);
  `data-testid="last-result"` (abbreviated JSON of the last finished run); sliders step
  0.1 mV; voltages shown by `formatVolts` (3 decimals, a 4th when non-zero); the
  heatmap also shows DQD-search maps (logged `*_csd` measurements); colour limits clip
  0.2% (`COLOUR_TAIL`).

## C-21 Progression — Sprint 8

- `trainer.game.progress`: `validate_player(id)` (`^[A-Za-z0-9_-]{1,64}$`);
  `ProgressStore(path, levels)` with `record(player, level_id, success, score, accuracy,
  hints)`, `view(player) -> [{id, order, unlocked, completed, attempts, best_score,
  best_accuracy, hints_used}]`, `is_unlocked(player, level_id)`. Level n unlocks when
  level n−1 is completed. JSON file, atomic writes; a corrupt file raises rather than
  resetting progress.
- Scoring: `HINT_PENALTY = 0.1`, `apply_hint_penalty(points, hints)`, applied in
  `Attempt.submit()` to successful scores; accuracy is not affected.
- `Level.explanation: tuple[str, ...]`, `Level.explain(attempt) -> list[str]`;
  `Attempt.explanation()` is `[]` until submitted.
- API (extends C-19): `POST /levels/{id}/attempts` takes optional `{player}` (locked →
  403, bad id → 422; no player = free play, never locked); `AttemptInfo` adds
  `explanation: list[str]` and `player`; `GET /players/{player}/progress` →
  `[LevelProgress]`. `create_app(..., progress_file=None)`; CLI `--progress-file`.
- Frontend: `PlayerBar` (`Your name`, `Save my progress`, `Switch to free play`;
  `localStorage["trainer.player"]`); `LevelPanel` `progress` prop (locked options
  disabled, labels `✓ … (best N)` / `🔒 …`), `data-testid="explanation"`,
  `Choose another level`.

## Upstream interfaces we depend on (pinned at upstream `6309eef`)

Not ours to change; listed so a rebase that alters them is noticed.

- `stanza/base/protocols.py`: `ControlInstrument` (`set_voltage`, `get_voltage`,
  `get_slew_rate`, `instrument_config.breakout_line`), `MeasurementInstrument` (`measure`).
- Driver loading: `device_from_config` → `load_driver_class(driver)` (first
  `InstrumentChannelMixin` subclass defined in `stanza.drivers.<driver>`) →
  `validate_driver_protocols` → `cls(instrument_config, channel_configs)`.
  GENERAL instruments fill both control and measurement roles.
- `RoutineRunner(configs=[DeviceConfig], base_dir=...)`, `.run(name, **params)`,
  `.results.store(name, value)`; global registry via `@routine`.
