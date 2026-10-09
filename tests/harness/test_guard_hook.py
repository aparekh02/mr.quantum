"""Tests for the PreToolUse guard hook in .claude/hooks/guard.py."""

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = REPO_ROOT / ".claude" / "hooks" / "guard.py"

# Built by concatenation so this file never contains the literal markers itself.
TYPE_IGNORE = "# type" + ": ignore"
SKIP_MARK = "@pytest.mark." + "skip"
SKIPIF_MARK = "@pytest.mark." + "skipif(True, reason='x')"
XFAIL_MARK = "@pytest.mark." + "xfail"
SKIP_CALL = "pytest." + "skip('later')"
XFAIL_CALL = "pytest." + "xfail('later')"
UNITTEST_SKIP = "@unittest." + "skip('later')"

UPSTREAM = frozenset({"stanza/device.py", "tests/test_device.py", "pyproject.toml"})


def _load_guard() -> ModuleType:
    spec = importlib.util.spec_from_file_location("guard", GUARD_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module via sys.modules
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard() -> ModuleType:
    return _load_guard()


def _decide(
    guard: ModuleType,
    rel_path: str,
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    current_text: str | None = None,
    upstream: frozenset[str] = UPSTREAM,
) -> Any:
    return guard.decide(
        rel_path,
        tool_name,
        tool_input,
        current_text=current_text,
        upstream_files=upstream,
    )


# --- no opinion -------------------------------------------------------------


def test_new_trainer_file_is_allowed(guard: ModuleType) -> None:
    assert (
        _decide(guard, "trainer/physics/pinchoff.py", "Write", {"content": "x = 1\n"})
        is None
    )


def test_simulator_driver_is_allowed_new_file_under_stanza(guard: ModuleType) -> None:
    assert (
        _decide(guard, "stanza/drivers/simulator.py", "Write", {"content": "x = 1\n"})
        is None
    )


def test_new_regression_file_is_allowed(guard: ModuleType) -> None:
    assert (
        _decide(
            guard,
            "tests/regression/test_level_01.py",
            "Write",
            {"content": "def test_x() -> None: ...\n"},
        )
        is None
    )


def test_non_python_content_is_not_pattern_checked(guard: ModuleType) -> None:
    assert (
        _decide(guard, "DECISIONS.md", "Write", {"content": f"we forbid {TYPE_IGNORE}"})
        is None
    )


# --- upstream files: ask -----------------------------------------------------


@pytest.mark.parametrize("rel_path", sorted(UPSTREAM))
def test_editing_upstream_file_asks(guard: ModuleType, rel_path: str) -> None:
    decision = _decide(guard, rel_path, "Edit", {"old_string": "a", "new_string": "b"})
    assert decision is not None
    assert decision.permission == "ask"
    assert "upstream" in decision.reason.lower()


def test_new_file_under_stanza_package_asks(guard: ModuleType) -> None:
    decision = _decide(guard, "stanza/routines/mine.py", "Write", {"content": ""})
    assert decision is not None
    assert decision.permission == "ask"


def test_notebook_edit_on_upstream_asks(guard: ModuleType) -> None:
    upstream = UPSTREAM | {"cookbooks/demo.ipynb"}
    decision = _decide(
        guard,
        "cookbooks/demo.ipynb",
        "NotebookEdit",
        {"new_source": "print(1)"},
        upstream=upstream,
    )
    assert decision is not None
    assert decision.permission == "ask"


# --- regression suite is append-only: deny ----------------------------------


def test_modifying_existing_regression_file_denies(guard: ModuleType) -> None:
    decision = _decide(
        guard,
        "tests/regression/test_level_01.py",
        "Edit",
        {"old_string": "assert a", "new_string": "assert b"},
        current_text="assert a\n",
    )
    assert decision is not None
    assert decision.permission == "deny"
    assert "append-only" in decision.reason


def test_overwriting_existing_regression_file_denies(guard: ModuleType) -> None:
    decision = _decide(
        guard,
        "tests/regression/README.md",
        "Write",
        {"content": "new"},
        current_text="old",
    )
    assert decision is not None
    assert decision.permission == "deny"


# --- forbidden escape hatches: deny ----------------------------------------


@pytest.mark.parametrize(
    "marker",
    [
        TYPE_IGNORE,
        SKIP_MARK,
        SKIPIF_MARK,
        XFAIL_MARK,
        SKIP_CALL,
        XFAIL_CALL,
        UNITTEST_SKIP,
    ],
)
def test_adding_escape_hatch_denies(guard: ModuleType, marker: str) -> None:
    decision = _decide(
        guard, "trainer/x.py", "Write", {"content": f"x = 1\n{marker}\n"}
    )
    assert decision is not None
    assert decision.permission == "deny"


def test_type_ignore_with_code_denies(guard: ModuleType) -> None:
    decision = _decide(
        guard, "trainer/x.py", "Write", {"content": f"x = f()  {TYPE_IGNORE}[misc]\n"}
    )
    assert decision is not None
    assert decision.permission == "deny"


def test_edit_adding_escape_hatch_denies(guard: ModuleType) -> None:
    decision = _decide(
        guard,
        "trainer/x.py",
        "Edit",
        {"old_string": "x = f()", "new_string": f"x = f()  {TYPE_IGNORE}"},
    )
    assert decision is not None
    assert decision.permission == "deny"


def test_multiedit_adding_escape_hatch_denies(guard: ModuleType) -> None:
    edits = [
        {"old_string": "a = 1", "new_string": "a = 2"},
        {"old_string": "def t():", "new_string": f"{XFAIL_MARK}\ndef t():"},
    ]
    decision = _decide(guard, "trainer/x.py", "MultiEdit", {"edits": edits})
    assert decision is not None
    assert decision.permission == "deny"


def test_edit_preserving_existing_marker_is_allowed(guard: ModuleType) -> None:
    # Moving text around an already-present marker does not add a new one.
    old = f"x = f()  {TYPE_IGNORE}"
    new = f"x = f()  {TYPE_IGNORE}\ny = 2"
    assert (
        _decide(guard, "trainer/x.py", "Edit", {"old_string": old, "new_string": new})
        is None
    )


def test_write_preserving_existing_marker_count_is_allowed(guard: ModuleType) -> None:
    current = f"x = f()  {TYPE_IGNORE}\n"
    assert (
        _decide(
            guard,
            "trainer/x.py",
            "Write",
            {"content": current + "y = 2\n"},
            current_text=current,
        )
        is None
    )


def test_escape_hatch_beats_upstream_ask(guard: ModuleType) -> None:
    decision = _decide(
        guard,
        "tests/test_device.py",
        "Edit",
        {"old_string": "def test_a():", "new_string": f"{SKIP_MARK}\ndef test_a():"},
    )
    assert decision is not None
    assert decision.permission == "deny"


# --- upstream file discovery --------------------------------------------------


def test_upstream_files_lists_tracked_upstream_paths(guard: ModuleType) -> None:
    files = guard.upstream_files(REPO_ROOT)
    assert "stanza/device.py" in files
    assert "pyproject.toml" in files
    assert "CLAUDE.md" not in files


def test_upstream_files_falls_back_when_git_unavailable(
    guard: ModuleType, tmp_path: Path
) -> None:
    (tmp_path / "stanza").mkdir()
    (tmp_path / "stanza" / "device.py").write_text("")
    (tmp_path / "trainer").mkdir()
    (tmp_path / "trainer" / "x.py").write_text("")
    files = guard.upstream_files(tmp_path)
    assert "stanza/device.py" in files
    assert "trainer/x.py" not in files


# --- end to end via stdin/stdout --------------------------------------------


def _run_hook(payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )


def test_hook_asks_for_upstream_file_end_to_end() -> None:
    result = _run_hook(
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(REPO_ROOT / "stanza" / "device.py"),
                "old_string": "a",
                "new_string": "b",
            },
        }
    )
    assert result.returncode == 0
    out = json.loads(result.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "ask"


def test_hook_silent_for_allowed_file_end_to_end() -> None:
    result = _run_hook(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(REPO_ROOT / "trainer" / "new.py"),
                "content": "x = 1\n",
            },
        }
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_hook_ignores_paths_outside_repo(tmp_path: Path) -> None:
    result = _run_hook(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(tmp_path / "x.py"),
                "content": f"{TYPE_IGNORE}\n",
            },
        }
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_hook_ignores_payload_without_path() -> None:
    result = _run_hook({"tool_name": "Write", "tool_input": {}})
    assert result.returncode == 0
    assert result.stdout == ""


# --- main() in process, so coverage sees it ----------------------------------


def _run_main(
    guard: ModuleType,
    payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> str:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert guard.main() == 0
    return capsys.readouterr().out


def test_main_asks_for_existing_upstream_file(
    guard: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(REPO_ROOT / "stanza" / "device.py"),
            "old_string": "a",
            "new_string": "b",
        },
    }
    out = json.loads(_run_main(guard, payload, monkeypatch, capsys))
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_main_denies_escape_hatch_in_new_file(
    guard: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(REPO_ROOT / "trainer" / "new.py"),
            "content": f"x = 1  {TYPE_IGNORE}\n",
        },
    }
    out = json.loads(_run_main(guard, payload, monkeypatch, capsys))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_main_uses_notebook_path(
    guard: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    notebooks = sorted((REPO_ROOT / "cookbooks").glob("*.ipynb"))
    assert notebooks, "upstream ships cookbook notebooks"
    payload = {
        "tool_name": "NotebookEdit",
        "tool_input": {"notebook_path": str(notebooks[0]), "new_source": "1"},
    }
    out = json.loads(_run_main(guard, payload, monkeypatch, capsys))
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"


@pytest.mark.parametrize(
    "payload",
    [
        {"tool_name": "Write", "tool_input": {}},
        {"tool_name": "Write", "tool_input": None},
        {"tool_name": "Write", "tool_input": {"file_path": "/elsewhere/x.py"}},
        {
            "tool_name": "Write",
            "tool_input": {"file_path": str(REPO_ROOT / "trainer" / "ok.py")},
        },
    ],
)
def test_main_silent_without_opinion(
    guard: ModuleType,
    payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run_main(guard, payload, monkeypatch, capsys) == ""
