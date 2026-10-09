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
