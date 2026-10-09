"""Hint penalty and post-level physics explanations."""

from pathlib import Path

import pytest

from trainer.game.attempt import Attempt
from trainer.game.level import HINT_PENALTY, Level, apply_hint_penalty
from trainer.game.levels import LEVELS, get_level

DEVICES = Path(__file__).resolve().parents[3] / "trainer" / "devices"
SENSOR = {
    "peak_spacing": 0.02,
    "sensor_group_name": "side_B",
    "sensor_plunger_gate": "PB",
    "measure_electrode": "OUT_B",
    "bias_gate": "IN_B",
    "bias_voltage": 0.001,
    "settling_time_s": 0.0,
}


@pytest.mark.parametrize(("hints", "expected"), [(0, 900), (1, 810), (3, 630), (20, 0)])
def test_each_hint_costs_a_tenth(hints: int, expected: int) -> None:
    assert HINT_PENALTY == pytest.approx(0.1)
    assert apply_hint_penalty(900, hints) == expected


def test_hints_lower_the_submitted_score(tmp_path: Path) -> None:
    level = get_level("coulomb-peak")
    plain = Attempt.start(level, DEVICES, tmp_path / "a")
    hinted = Attempt.start(level, DEVICES, tmp_path / "b")
    for a in (plain, hinted):
        a.lab.run("find_sensor_peak", **SENSOR)
    hinted.next_hint()
    hinted.next_hint()
    p, h = plain.submit(), hinted.submit()
    assert p.success and h.success
    assert h.score == apply_hint_penalty(p.score, 2)
    assert h.accuracy == p.accuracy  # hints cost points, not accuracy


@pytest.mark.parametrize("level", LEVELS, ids=lambda lv: lv.id)
def test_every_level_explains_its_physics(level: Level, tmp_path: Path) -> None:
    attempt = Attempt.start(level, DEVICES, tmp_path)
    attempt.submit()
    paragraphs = attempt.explanation()
    assert len(paragraphs) >= 2
    assert all(p.strip() for p in paragraphs)


def test_explanation_is_only_available_after_submitting(tmp_path: Path) -> None:
    attempt = Attempt.start(get_level("coulomb-peak"), DEVICES, tmp_path)
    assert attempt.explanation() == []


def test_level_one_explanation_uses_this_device(tmp_path: Path) -> None:
    attempt = Attempt.start(get_level("coulomb-peak"), DEVICES, tmp_path)
    attempt.lab.run("find_sensor_peak", **SENSOR)
    attempt.submit()
    text = " ".join(attempt.explanation())
    assert "20.0 mV" in text  # Ec / alpha_PB of this sensor dot
    assert "charging energy" in text
