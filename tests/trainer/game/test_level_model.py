"""The Level model and scoring (trainer/game/level.py)."""

from typing import Any

import pytest

from trainer.game.level import Evaluation, Level, score


def _kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "demo-level",
        "order": 1,
        "title": "Demo",
        "concept": "A physical idea worth learning.",
        "objective": "Do the thing.",
        "device": "dqd_with_sensor",
        "hints": ("First hint.",),
        "measurement_budget": 100,
    }
    return {**base, **overrides}


class _Demo(Level):
    def judge(self, attempt: Any) -> Evaluation:  # pragma: no cover - not called
        raise NotImplementedError


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("concept", ""),
        ("concept", "   "),
        ("objective", ""),
        ("title", ""),
        ("hints", ()),
        ("id", "Not A Slug"),
        ("measurement_budget", 0),
        ("order", 0),
    ],
)
def test_level_definition_is_validated(field: str, value: Any) -> None:
    with pytest.raises(ValueError, match=field):
        _Demo(**_kwargs(**{field: value}))


def test_valid_level() -> None:
    level = _Demo(**_kwargs())
    assert level.public()["concept"] == "A physical idea worth learning."
    assert "hints" not in level.public()  # hints are revealed one at a time
    assert level.public()["hint_count"] == 1


@pytest.mark.parametrize("accuracy", [0.0, 0.3, 0.5, 0.8, 1.0])
def test_score_is_bounded(accuracy: float) -> None:
    assert 0 <= score(accuracy, measurements=50, budget=100) <= 1000


def test_score_is_monotonic_in_accuracy() -> None:
    scores = [score(a / 20, measurements=150, budget=100) for a in range(21)]
    assert scores == sorted(scores)
    assert scores[0] == 0
    assert scores[-1] > scores[10] > 0


def test_score_does_not_reward_extra_measurements() -> None:
    scores = [
        score(0.9, measurements=m, budget=100) for m in (10, 100, 150, 400, 10_000)
    ]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == scores[1]  # within budget, no penalty


def test_score_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError, match="accuracy"):
        score(1.5, measurements=1, budget=1)
    with pytest.raises(ValueError, match="measurements"):
        score(0.5, measurements=-1, budget=1)


def test_evaluation_is_json_ready() -> None:
    e = Evaluation(
        success=True, accuracy=0.9, score=900, measurements=10, feedback=["ok"]
    )
    assert e.to_dict() == {
        "success": True,
        "accuracy": 0.9,
        "score": 900,
        "measurements": 10,
        "feedback": ["ok"],
    }
