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

## Upstream interfaces we depend on (pinned at upstream `6309eef`)

Not ours to change; listed so a rebase that alters them is noticed.

- `stanza/base/protocols.py`: `ControlInstrument` (`set_voltage`, `get_voltage`,
  `get_slew_rate`, `instrument_config.breakout_line`), `MeasurementInstrument` (`measure`).
- Driver loading: `load_driver_class`, `validate_driver_protocols` (Sprint 1 will pin the
  exact call path here).
