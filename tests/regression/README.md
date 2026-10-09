# tests/regression/ — append-only

Every shipped level gets a headless test here that plays it start to finish.
Sprint 2's routine anchors (`find_sensor_peak`, `find_stable_sensor_peak`,
`run_compensation`, `leakage_test`, `reservoir_characterization`, `dqd_search`)
also land here.

Rules:

- **Append-only.** Add new `test_*.py` files. Never edit, weaken, skip, or delete
  an existing one. If one encodes genuinely wrong behavior, stop and ask; the
  project owner decides. The `.claude/hooks/guard.py` hook denies edits to
  existing files in this directory.
- Runs every sprint, forever, as part of `make verify` (`make regression`).
- Deterministic: use the `test_seed` / `rng` fixtures from the root `conftest.py`.
- While this directory has no `test_*.py` files, `make regression` passes with
  "no regression tests yet". Once any exist, collecting zero tests fails.
