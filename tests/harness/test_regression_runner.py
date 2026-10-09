"""Tests for `make regression`, which must not pass vacuously once tests exist."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_regression(regression_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "make",
            "-s",
            "-C",
            str(REPO_ROOT),
            "regression",
            f"REGRESSION_DIR={regression_dir}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_empty_regression_dir_passes_with_notice(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("append-only\n")
    result = _make_regression(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no regression tests yet" in result.stdout


def test_passing_regression_test_passes(tmp_path: Path) -> None:
    (tmp_path / "test_ok.py").write_text("def test_ok() -> None:\n    assert True\n")
    result = _make_regression(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


def test_failing_regression_test_fails(tmp_path: Path) -> None:
    (tmp_path / "test_bad.py").write_text("def test_bad() -> None:\n    assert False\n")
    result = _make_regression(tmp_path)
    assert result.returncode != 0


def test_test_files_collecting_nothing_fails(tmp_path: Path) -> None:
    # A regression file exists but no test runs: that is a broken suite, not empty.
    (tmp_path / "test_hollow.py").write_text("x = 1\n")
    result = _make_regression(tmp_path)
    assert result.returncode != 0
    assert "collected no tests" in result.stdout + result.stderr
