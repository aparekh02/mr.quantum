"""Sprint demos run end to end and print what they show."""

from pathlib import Path

import pytest

from trainer.demos import sprint01


def test_sprint01_demo_prints_noise_floor_and_turn_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sprint01.main(base_dir=tmp_path)
    out = capsys.readouterr().out
    assert "noise_floor_measurement" in out
    assert "global_accumulation" in out
    assert "turn-on" in out


def test_sprint02_demo_runs_the_full_tune_up(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from trainer.demos import sprint02

    sprint02.main(base_dir=tmp_path)
    out = capsys.readouterr().out
    for routine in (
        "leakage_test",
        "reservoir_characterization",
        "find_sensor_peak",
        "find_stable_sensor_peak",
        "run_compensation",
        "run_dqd_search",
    ):
        assert routine in out
    assert "double dot found" in out
