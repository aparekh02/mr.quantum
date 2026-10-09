# Project: Stanza Quantum Tune-Up Trainer

A game-like teaching interface built on top of `conductorquantum/stanza`. Students learn
semiconductor quantum-dot tune-up by driving a **simulated** device through the same
routines real researchers run.

Upstream Stanza is a framework for tune-up sequences on real quantum hardware. We are
adding (a) a physics simulator driver so there is no hardware requirement, and (b) a
visual, level-based frontend. We do not rewrite upstream internals.

This directory is the repo root: a fork of upstream, with `upstream` as a git remote.

## Commands

```bash
make venv         # uv-managed CPython 3.12 venv at .venv (see DECISIONS.md D-002)
make install      # pip install -e ".[dev,test,qm,routines,notebook]" -c constraints.txt
make test         # pytest -q
make cov          # pytest --cov=stanza --cov=trainer --cov-report=term-missing
make lint         # ruff check + ruff format --check (upstream's tools; D-003)
make types        # mypy stanza trainer conftest.py .claude/hooks/guard.py
make regression   # tests/regression/ only
make verify       # lint + types + test + regression suite. THE GATE.
```

`make verify` is the definition of done. Not `make test`.

## Non-negotiable rules

1. **One sprint at a time.** Read `PLAN.md`. Work only the first sprint whose box is
   unchecked. Do not start the next one, do not "also quickly add" anything from a later
   sprint. If you think the plan is wrong, say so and stop — do not improvise.
2. **Test first.** Write the failing test, run it, show me the failure, then implement.
   A sprint with implementation committed before its tests is rejected.
3. **`make verify` must pass before you say a sprint is done.** The whole suite, not just
   the new tests. If something unrelated broke, that is the point of the gate — fix it or
   report it, never skip it.
4. **Never edit or delete an existing passing test to make new code pass.** If an old test
   genuinely encodes wrong behavior, stop and explain why; I decide.
5. **`tests/regression/` is append-only.** Every shipped level gets a headless test that
   plays it start to finish. Those tests run every sprint, forever.
6. **Respect frozen interfaces.** `CONTRACTS.md` lists interfaces other sprints depend on.
   Changing one requires updating every caller in the same commit plus a note in
   `DECISIONS.md`.
7. **Commit at every green state**, conventional commits (`feat:`, `fix:`, `test:`,
   `chore:`). Small commits are rollback points. One branch per sprint: `sprint/NN-slug`.
8. **No new runtime dependency** without asking. Upstream deps are already chosen.
9. **Determinism.** Every simulator path takes an explicit seed. No bare `np.random`.
   Physics tests assert against golden values at a fixed seed.

## Upstream conventions to inherit

- Python ≥ 3.11. Line length 88, formatted with `ruff format` (Black-compatible).
  Ruff: `E,W,F,I,B,C4,UP`.
- mypy with `check_untyped_defs` and `disallow_any_generics` — annotate everything.
- Pydantic v2 for all config models. Validate at the boundary, not in the middle.
- Instruments are structural `Protocol`s (`stanza/base/protocols.py`), not base classes.
  Our simulator satisfies `ControlInstrument` and `MeasurementInstrument` by shape.
- Test doubles follow the hand-rolled mock style in `tests/conftest.py`.
- `pre-commit` is installed and runs. Don't fight it.

## Architecture boundaries

```
stanza/drivers/simulator.py   # NEW. Physics. Knows nothing about the UI or game.
trainer/physics/              # NEW. Device models the simulator draws on. Pure functions.
trainer/api/                  # NEW. FastAPI wrapper over RoutineRunner. No physics here.
trainer/game/                 # NEW. Levels, objectives, scoring. No physics, no HTTP.
frontend/                     # NEW. Visual layer. Talks only to trainer/api.
stanza/**  (everything else)  # UPSTREAM. Treat as read-only.
```

Rules that follow from this:
- The simulator must not import from `trainer/game` or `trainer/api`.
- Game logic must not call instruments directly — only through `RoutineRunner`.
- If you need to touch an upstream file, stop and tell me first. We want to stay
  rebaseable on upstream `main`. (`.claude/hooks/guard.py` asks before any such edit.)

## Pedagogy constraints

The point is that students learn real tune-up, so:
- Simulated physics must be qualitatively faithful: Coulomb blockade peaks, pinch-off
  curves, cross-capacitance between gates, honeycomb charge-stability diagrams, realistic
  noise. A level that can be beaten by behavior a real device wouldn't show is a bug.
- Students run the *actual* upstream built-in routines. Do not reimplement simplified
  versions for the game.
- Every level states the physical concept it teaches in its definition. If you can't name
  the concept, the level isn't designed yet.

## When you are stuck

Say so and stop. Do not: widen a test's tolerance to make it pass, add `# type: ignore`,
mark a test `skip`/`xfail`, or stub a function to return a constant that satisfies the
assertion. Any of those appearing in a diff is a failed sprint. (The guard hook denies the
first two mechanically; the rest is on you.)

## Session hygiene

At the start of each sprint, re-read `PLAN.md`, `CONTRACTS.md`, and `DECISIONS.md`.
At the end, update all three. Context does not survive between sessions; those files do.
