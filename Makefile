# Stanza Quantum Tune-Up Trainer — developer harness.
# `make verify` is the definition of done.

VENV ?= .venv
PY ?= $(VENV)/bin/python
EXTRAS ?= dev,test,qm,routines,notebook
REGRESSION_DIR ?= tests/regression

# trainer/ does not exist until Sprint 1; include it once it does.
PKG_PATHS := stanza $(wildcard trainer)
LINT_PATHS := $(PKG_PATHS) tests scripts conftest.py .claude/hooks
TYPE_PATHS := $(PKG_PATHS) conftest.py .claude/hooks/guard.py
COV_PKGS := $(foreach p,$(PKG_PATHS),--cov=$(p))

.PHONY: venv install test cov lint types regression verify demo-01 demo-02

venv:
	uv venv --managed-python --python 3.12 --seed $(VENV)

install:
	$(PY) -m pip install -e ".[$(EXTRAS)]" -c constraints.txt
	$(VENV)/bin/pre-commit install

test:
	$(PY) -m pytest -q

cov:
	$(PY) -m pytest $(COV_PKGS) --cov-report=term-missing

lint:
	$(PY) -m ruff check $(LINT_PATHS)
	$(PY) -m ruff format --check $(LINT_PATHS)

types:
	$(PY) -m mypy $(TYPE_PATHS)

# Exit 5 means pytest collected nothing. That is fine only while the directory
# holds no test files at all; once a level ships, an empty collection is a failure.
regression:
	@$(PY) -m pytest -q -p no:cacheprovider $(REGRESSION_DIR); rc=$$?; \
	if [ $$rc -eq 5 ]; then \
		if ls $(REGRESSION_DIR)/test_*.py >/dev/null 2>&1; then \
			echo "regression: test files present but collected no tests"; exit 1; \
		fi; \
		echo "regression: no regression tests yet"; exit 0; \
	fi; exit $$rc

verify: lint types test regression

demo-01:
	$(PY) -m trainer.demos.sprint01

demo-02:
	$(PY) -m trainer.demos.sprint02
