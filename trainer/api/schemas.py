"""Request and response models for the trainer API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceInfo(_Model):
    name: str
    title: str


class CreateSession(_Model):
    device: str


class SessionInfo(_Model):
    id: str
    device: str
    title: str
    groups: dict[str, list[str]]


class PadInfo(_Model):
    name: str
    pad_type: str
    electrode_type: str
    v_lower_bound: float | None
    v_upper_bound: float | None
    controllable: bool
    measurable: bool
    group: str | None


class SetVoltages(_Model):
    voltages: dict[str, float] = Field(min_length=1)


class MeasureRequest(_Model):
    pads: list[str] = Field(min_length=1)


class MeasureResponse(_Model):
    currents: dict[str, float]


class ParameterInfo(_Model):
    name: str
    type: str
    required: bool
    default: Any = None


class RoutineInfo(_Model):
    name: str
    parameters: list[ParameterInfo]


class RunRequest(_Model):
    routine: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class RunInfo(_Model):
    id: str
    routine: str
    parameters: dict[str, Any]
    status: Literal["running", "succeeded", "failed"]
    result: Any = None
    error: str | None = None
    restored_voltages: bool | None = None
    first_seq: int
    last_seq: int | None = None


class EventOut(_Model):
    seq: int
    time: float
    kind: str
    routine: str | None
    name: str
    data: Any


class LevelInfo(_Model):
    id: str
    order: int
    title: str
    concept: str
    objective: str
    device: str
    hint_count: int
    measurement_budget: int


class EvaluationOut(_Model):
    success: bool
    accuracy: float
    score: int
    measurements: int
    feedback: list[str]


class AttemptInfo(_Model):
    id: str
    level_id: str
    session_id: str
    status: Literal["active", "submitted"]
    measurements: int
    hints_shown: int
    evaluation: EvaluationOut | None = None
    explanation: list[str] = Field(default_factory=list)
    player: str | None = None


class StartAttempt(_Model):
    player: str | None = None


class LevelProgress(_Model):
    id: str
    order: int
    unlocked: bool
    completed: bool
    attempts: int
    best_score: int
    best_accuracy: float
    hints_used: int


class HintOut(_Model):
    hint: str | None
    hints_shown: int
