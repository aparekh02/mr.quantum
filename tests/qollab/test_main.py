"""main.py as Qollab runs it: one backend.run, a readable report, Qollab's rules."""

import ast
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

PROJECT = Path(__file__).resolve().parents[2] / "qollab"


class CountingBackend:
    """Wraps Qiskit's BasicSimulator and counts jobs, like an IonQ backend would."""

    def __init__(self) -> None:
        from qiskit.providers.basic_provider import BasicSimulator

        self.inner = BasicSimulator()
        self.jobs = 0

    def run(self, circuits: Any, **kwargs: Any) -> Any:
        self.jobs += 1
        return self.inner.run(circuits, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


@pytest.fixture
def main_module(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    import importlib

    import main

    importlib.reload(main)
    backend = CountingBackend()
    monkeypatch.setattr(main, "backend", backend)
    yield main


def test_main_runs_exactly_one_job_and_reports(
    main_module: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    main_module.main()
    out = capsys.readouterr().out
    assert main_module.backend.jobs == 1
    for heading in ("Device", "Charge map", "Experiment", "What this shows"):
        assert heading in out


@pytest.mark.parametrize("experiment", ["detuning_sweep", "time_sweep", "sweet_spot"])
def test_every_experiment_runs(
    main_module: Any, experiment: str, capsys: pytest.CaptureFixture[str]
) -> None:
    main_module.main(experiment=experiment, shots=200, qubits=10)
    out = capsys.readouterr().out
    assert main_module.backend.jobs == 1
    assert "sensor" in out.lower()


def test_detuning_sweep_measures_the_tunnel_coupling(
    main_module: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    main_module.main(experiment="detuning_sweep", shots=2000, qubits=20)
    out = capsys.readouterr().out
    match = re.search(r"fitted Δ = ([0-9.]+) µeV.*true Δ = ([0-9.]+) µeV", out)
    assert match, out
    assert float(match.group(1)) == pytest.approx(float(match.group(2)), rel=0.15)


def test_merged_dots_are_explained_not_crashed(
    main_module: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    main_module.main(inner_barrier_V=-1.6)
    out = capsys.readouterr().out
    assert "merge" in out.lower()
    assert main_module.backend.jobs == 1


def test_bad_settings_are_explained(
    main_module: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    main_module.main(experiment="teleport")
    out = capsys.readouterr().out
    assert "experiment" in out.lower()
    assert main_module.backend.jobs == 0  # nothing submitted for an invalid request


def test_off_qollab_fallback_backend_exists() -> None:
    import importlib

    import main

    importlib.reload(main)
    assert main.backend is not None


# --- Qollab's platform rules, checked from the files ---------------------------


def _source() -> str:
    return (PROJECT / "main.py").read_text()


def test_main_signature_is_one_line_at_column_zero_with_simple_types() -> None:
    lines = [ln for ln in _source().splitlines() if ln.startswith("def main(")]
    assert len(lines) == 1, "def main( must be on one line at column 0"
    tree = ast.parse(_source())
    fn = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"
    )
    for arg in fn.args.args:
        assert isinstance(arg.annotation, ast.Name) and arg.annotation.id in {
            "int",
            "float",
            "str",
            "bool",
        }, arg.arg
    assert len(fn.args.defaults) == len(fn.args.args), "every parameter needs a default"


def test_main_is_never_called_from_the_file() -> None:
    tree = ast.parse(_source())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "main"
        ):
            pytest.fail("main() must not be called from main.py: Qollab calls it")


def test_one_backend_run_call_site_and_no_own_remote_backend() -> None:
    text = "\n".join(p.read_text() for p in PROJECT.glob("*.py"))
    assert text.count("backend.run(") == 1
    assert not re.search(r"IonQProvider\(|\.get_backend\(|QiskitRuntimeService\(", text)


def test_local_simulator_only_when_qollab_provided_no_backend() -> None:
    lines = _source().splitlines()
    for i, line in enumerate(lines):
        if re.search(
            r"\b(AerSimulator|BasicSimulator|StatevectorSampler)\(", line
        ) and not line.strip().startswith("#"):
            assert any("if backend is None" in p for p in lines[max(0, i - 4) : i]), (
                line
            )


def test_a_backend_provided_by_qollab_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins
    import importlib
    import sys

    sentinel = object()
    monkeypatch.setattr(builtins, "backend", sentinel, raising=False)
    # A fresh import, as on Qollab: reload() would keep the old module globals.
    monkeypatch.delitem(sys.modules, "main", raising=False)
    fresh = importlib.import_module("main")
    assert fresh.backend is sentinel
    monkeypatch.delitem(sys.modules, "main", raising=False)


def test_imports_are_only_what_qollab_pyodide_provides() -> None:
    allowed = {
        "qiskit",
        "numpy",
        "math",
        "dataclasses",
        "typing",
        "builtins",
        "__future__",
        "dqd",
        "qubit",
        "report",
    }
    for path in PROJECT.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                assert name in allowed, f"{path.name} imports {name}"


def test_requirements_lines_are_plain() -> None:
    pattern = re.compile(
        r"^[A-Za-z0-9][A-Za-z0-9._-]*\s*((==|>=|<=|~=|!=|<|>)\s*[A-Za-z0-9.*+!-]+(\s*,\s*(==|>=|<=|~=|!=|<|>)\s*[A-Za-z0-9.*+!-]+)*)?$"
    )
    lines = [
        ln.strip()
        for ln in (PROJECT / "requirements.txt").read_text().splitlines()
        if ln.strip()
    ]
    assert any(ln.startswith("qiskit") for ln in lines)
    assert all(pattern.match(ln) for ln in lines)


def test_license_and_size_limits() -> None:
    assert "MIT License" in (PROJECT / "LICENSE").read_text()
    files = [
        p for p in PROJECT.rglob("*") if p.is_file() and "__pycache__" not in p.parts
    ]
    assert len(files) <= 100
    assert all(p.stat().st_size <= 2 * 1024 * 1024 for p in files)


def test_readme_is_a_complete_project_page() -> None:
    md = (PROJECT / "README.md").read_text()
    assert len(md) <= 65000
    assert "This effort is supported by Qollab & IonQ" in md
    for section in (
        "How to run",
        "What's new here",
        "Built during the hackathon",
        "Accessibility",
        "License",
    ):
        assert re.search(
            rf"^#+\s.*{re.escape(section)}", md, re.MULTILINE | re.IGNORECASE
        ), section
    assert "FILL" not in md
    # One paragraph per line: Qollab renders each newline as a line break.
    prose = re.compile(r"^\s*([#>|!*+-]|\d+[.)]\s|```|<|\[[^\]]*\]:)")
    fence, previous = False, False
    for line in md.splitlines():
        if line.strip().startswith("```"):
            fence, previous = not fence, False
            continue
        is_prose = not fence and line.strip() != "" and not prose.match(line)
        assert not (is_prose and previous), f"hard-wrapped paragraph near: {line[:40]}"
        previous = is_prose


def test_no_secrets() -> None:
    for p in PROJECT.rglob("*"):
        if p.is_file() and p.suffix in {".py", ".md", ".txt", ".json"}:
            assert not re.search(
                r"(IONQ_API_KEY|API_TOKEN)\s*[=:]\s*['\"][^'\"]+", p.read_text()
            )


def test_sweet_spot_reports_frequency_shift_per_group(
    main_module: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    main_module.main(experiment="sweet_spot", charge_noise_ueV=10.0, pulse_ps=300.0)
    out = capsys.readouterr().out
    shifts = dict(
        re.findall(
            r"(sweet spot|off sweet spot): .*?frequency shift ([0-9.]+) GHz", out
        )
    )
    assert set(shifts) == {"sweet spot", "off sweet spot"}, out
    assert float(shifts["sweet spot"]) < float(shifts["off sweet spot"])
    assert "noise-free" in out
    assert main_module.backend.jobs == 1
