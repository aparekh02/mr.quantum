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
