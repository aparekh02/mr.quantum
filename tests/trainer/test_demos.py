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
