"""The Level model and the shared scoring rule."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from trainer.workflows import Step

if TYPE_CHECKING:
    from trainer.game.attempt import Attempt

_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


HINT_PENALTY = 0.1
"""Fraction of the score each revealed hint costs."""


def apply_hint_penalty(points: int, hints: int) -> int:
    """Score after ``hints`` hints, never below zero."""
    return max(0, round(points * (1.0 - HINT_PENALTY * hints)))


def score(accuracy: float, measurements: int, budget: int) -> int:
    """Points in [0, 1000]: accuracy times efficiency.

    Efficiency is 1 within the measurement budget and ``budget / measurements``
    beyond it, so a score never rises with extra measurements.
    """
    if not 0.0 <= accuracy <= 1.0:
        raise ValueError(f"accuracy must be in [0, 1], got {accuracy}")
    if measurements < 0:
        raise ValueError(f"measurements must be >= 0, got {measurements}")
    efficiency = 1.0 if measurements <= budget else budget / measurements
    return round(1000 * accuracy * efficiency)


@dataclass(frozen=True)
class Evaluation:
    success: bool
    accuracy: float
    score: int
    measurements: int
    feedback: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "accuracy": self.accuracy,
            "score": self.score,
            "measurements": self.measurements,
            "feedback": list(self.feedback),
        }


@dataclass(frozen=True)
class Level(ABC):
    """One level: the concept it teaches, what to do, how it is judged and scored.

    ``setup`` steps run (as upstream routines) before the player starts.
    """

    id: str
    order: int
    title: str
    concept: str
    objective: str
    device: str
    hints: tuple[str, ...]
    measurement_budget: int
    setup: tuple[Step, ...] = field(default_factory=tuple)
    explanation: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not _SLUG.match(self.id):
            raise ValueError(f"id must be a lowercase slug, got {self.id!r}")
        if self.order < 1:
            raise ValueError(f"order must be >= 1, got {self.order}")
        for name in ("title", "concept", "objective", "device"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be empty")
        if not self.hints:
            raise ValueError("hints must not be empty")
        if self.measurement_budget < 1:
            raise ValueError(
                f"measurement_budget must be >= 1, got {self.measurement_budget}"
            )

    @abstractmethod
    def judge(self, attempt: Attempt) -> Evaluation:
        """Evaluate the device state the player submitted."""

    def baseline(self, attempt: Attempt) -> dict[str, Any]:
        """Ground truth recorded right after setup, for judging later."""
        return {}

    def explain(self, attempt: Attempt) -> list[str]:
        """The physics behind the level, shown after submitting. Levels can add
        specifics about the player's own device and attempt."""
        return list(self.explanation)

    def public(self) -> dict[str, Any]:
        """What a player sees before starting (hints come one at a time)."""
        return {
            "id": self.id,
            "order": self.order,
            "title": self.title,
            "concept": self.concept,
            "objective": self.objective,
            "device": self.device,
            "hint_count": len(self.hints),
            "measurement_budget": self.measurement_budget,
        }
