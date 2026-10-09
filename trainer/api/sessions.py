"""Lab sessions behind the API: one simulated device each, one run at a time.

Upstream routines run through ``SimulatedLab`` (``RoutineRunner``) in a worker
thread. Virtual time patches process-wide modules, so routine execution is also
serialised across sessions by a global lock.
"""

from __future__ import annotations

import inspect
import math
import threading
import typing
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from stanza.routines import get_registered_routines
from trainer.api.events import EventLog, jsonable
from trainer.api.schemas import ParameterInfo, RoutineInfo
from trainer.api.streaming import StreamingDataLogger
from trainer.game.attempt import Attempt, AttemptClosed
from trainer.game.level import Level
from trainer.lab import SimulatedLab
from trainer.routines import register_builtin_routines

_RUN_LOCK = threading.Lock()
"""Only one routine executes at a time per process (virtual time is global)."""

_RUNNER_PARAMS = {"group", "session_suffix"}


class SessionBusy(Exception):
    """A run is in progress; the device cannot be changed now."""


class BadRequest(Exception):
    """Invalid input from the client; carries pydantic-style error details."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        super().__init__(errors)
        self.errors = errors


def _error(loc: list[str], msg: str) -> BadRequest:
    return BadRequest([{"loc": loc, "msg": msg, "type": "value_error"}])


def _type_name(annotation: Any) -> str:
    if annotation is inspect.Parameter.empty:
        return "Any"
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def _routine_parameters(func: Callable[..., Any]) -> list[inspect.Parameter]:
    params = list(inspect.signature(func).parameters.values())[1:]  # drop ctx
    return [
        p
        for p in params
        if p.name != "session"
        and p.kind
        not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
    ]


def describe_routine(name: str, func: Callable[..., Any]) -> RoutineInfo:
    hints = typing.get_type_hints(func)
    return RoutineInfo(
        name=name,
        parameters=[
            ParameterInfo(
                name=p.name,
                type=_type_name(hints.get(p.name, p.annotation)),
                required=p.default is inspect.Parameter.empty,
                default=None
                if p.default is inspect.Parameter.empty
                else jsonable(p.default),
            )
            for p in _routine_parameters(func)
        ],
    )


def _parameter_model(
    name: str, func: Callable[..., Any], configured: dict[str, Any]
) -> type[BaseModel]:
    hints = typing.get_type_hints(func)
    fields: dict[str, Any] = {}
    for p in _routine_parameters(func):
        annotation = hints.get(p.name, Any)
        if p.name in configured:
            default: Any = configured[p.name]
        elif p.default is inspect.Parameter.empty:
            default = ...
        else:
            default = p.default
        fields[p.name] = (annotation, default)
    for extra in _RUNNER_PARAMS:
        fields[extra] = (str | None, None)
    return create_model(
        f"{name}_parameters",
        __config__=ConfigDict(extra="forbid", arbitrary_types_allowed=True),
        **fields,
    )


@dataclass
class Run:
    id: str
    routine: str
    parameters: dict[str, Any]
    first_seq: int
    status: str = "running"
    result: Any = None
    error: str | None = None
    restored_voltages: bool | None = None
    last_seq: int | None = None
    done: threading.Event = field(default_factory=threading.Event)

    def info(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "routine": self.routine,
            "parameters": jsonable(self.parameters),
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "restored_voltages": self.restored_voltages,
            "first_seq": self.first_seq,
            "last_seq": self.last_seq,
        }


class LabSession:
    """One student's simulated device, its event log and its runs."""

    def __init__(self, device: str, device_file: Path, data_dir: Path) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.device = device
        self.lab = SimulatedLab.from_yaml(device_file, base_dir=data_dir / self.id)
        self.events = EventLog(clock=self.lab.simulator.clock.now)
        self.lab.runner.resources.add(
            "logger",
            StreamingDataLogger(
                routine_name="device", base_dir=data_dir / self.id, events=self.events
            ),
        )
        self.runs: dict[str, Run] = {}
        self._busy = threading.Lock()

    # --- device access -----------------------------------------------------

    @contextmanager
    def busy(self) -> Iterator[None]:
        if not self._busy.acquire(blocking=False):
            raise SessionBusy()
        try:
            yield
        finally:
            self._busy.release()

    @property
    def channel_configs(self) -> dict[str, Any]:
        configs: dict[str, Any] = self.lab.device.channel_configs
        return configs

    def voltages(self) -> dict[str, float]:
        return dict(self.lab.simulator.state)

    def set_voltages(self, requested: dict[str, float]) -> dict[str, float]:
        for pad, value in requested.items():
            cfg = self.channel_configs.get(pad)
            if cfg is None:
                raise _error(["body", "voltages", pad], f"unknown pad {pad}")
            if cfg.control_channel is None:
                raise _error(["body", "voltages", pad], f"{pad} cannot be set")
            low, high = cfg.voltage_range
            if not math.isfinite(value):
                raise _error(["body", "voltages", pad], "voltage must be finite")
            if (low is not None and value < low) or (high is not None and value > high):
                raise _error(
                    ["body", "voltages", pad], f"{value} V is outside [{low}, {high}] V"
                )
        with self.busy():
            self.lab.device.jump(requested)
        self.events.append("voltages", None, "voltages", requested)
        return self.voltages()

    def measure(self, pads: list[str]) -> dict[str, float]:
        for pad in pads:
            cfg = self.channel_configs.get(pad)
            if cfg is None:
                raise _error(["body", "pads"], f"unknown pad {pad}")
            if cfg.measure_channel is None:
                raise _error(["body", "pads"], f"{pad} cannot be measured")
        with self.busy():
            return {pad: float(self.lab.device.measure(pad)) for pad in pads}

    # --- routines ----------------------------------------------------------

    def validate_run(self, routine: str, params: dict[str, Any]) -> dict[str, Any]:
        register_builtin_routines()
        registered = get_registered_routines()
        if routine not in registered:
            raise _error(["body", "routine"], f"unknown routine {routine}")
        model = _parameter_model(
            routine, registered[routine], self.lab.runner.configs.get(routine, {})
        )
        try:
            validated = model.model_validate(params)
        except ValidationError as e:
            raise BadRequest(
                [
                    {**err, "loc": ["body", "parameters", *err["loc"]]}
                    for err in e.errors(include_url=False)
                ]
            ) from e
        group = params.get("group")
        if group is not None and group not in self.lab.config.groups:
            raise _error(["body", "parameters", "group"], f"unknown group {group}")
        dumped: dict[str, Any] = validated.model_dump(exclude_unset=True)
        return dumped

    def start_run(self, routine: str, params: dict[str, Any]) -> Run:
        validated = self.validate_run(routine, params)
        if not self._busy.acquire(blocking=False):
            raise SessionBusy()
        run = Run(
            id=uuid.uuid4().hex[:12],
            routine=routine,
            parameters=validated,
            first_seq=self.events.last_seq + 1,
        )
        self.runs[run.id] = run
        threading.Thread(target=self._execute, args=(run,), daemon=True).start()
        return run

    def _execute(self, run: Run) -> None:
        snapshot = self.voltages()
        self.events.append(
            "run_started",
            run.routine,
            run.routine,
            {"run_id": run.id, "parameters": run.parameters},
        )
        try:
            with _RUN_LOCK:
                result = self.lab.run(run.routine, **run.parameters)
            run.result = jsonable(result)
            run.status = "succeeded"
            self.events.append(
                "run_finished", run.routine, run.routine, {"run_id": run.id}
            )
        except Exception as e:
            run.error = str(e)
            run.status = "failed"
            run.restored_voltages = self._restore(snapshot)
            self.events.append(
                "run_failed",
                run.routine,
                run.routine,
                {
                    "run_id": run.id,
                    "error": run.error,
                    "restored_voltages": run.restored_voltages,
                },
            )
        finally:
            run.last_seq = self.events.last_seq
            self._busy.release()
            run.done.set()

    def _restore(self, snapshot: dict[str, float]) -> bool:
        try:
            self.lab.device.jump(snapshot)
            return True
        except Exception:
            return False


class SessionRegistry:
    def __init__(self, devices_dir: Path, data_dir: Path) -> None:
        self.devices_dir = devices_dir
        self.data_dir = data_dir
        self._sessions: dict[str, LabSession] = {}
        self._lock = threading.Lock()

    def device_files(self) -> dict[str, Path]:
        return {p.stem: p for p in sorted(self.devices_dir.glob("*.yaml"))}

    def create(self, device: str) -> LabSession:
        files = self.device_files()
        if device not in files:
            raise _error(
                ["body", "device"], f"unknown device {device}; have {sorted(files)}"
            )
        session = LabSession(device, files[device], self.data_dir)
        with self._lock:
            self._sessions[session.id] = session
        return session

    def get(self, sid: str) -> LabSession:
        with self._lock:
            return self._sessions[sid]

    def delete(self, sid: str) -> None:
        with self._lock:
            del self._sessions[sid]


@dataclass
class AttemptRecord:
    id: str
    attempt: Attempt
    session: LabSession

    def info(self) -> dict[str, Any]:
        a = self.attempt
        return {
            "id": self.id,
            "level_id": a.level.id,
            "session_id": self.session.id,
            "status": "active" if a.result is None else "submitted",
            "measurements": a.measurements,
            "hints_shown": a.hints_shown,
            "evaluation": None if a.result is None else a.result.to_dict(),
        }


class AttemptRegistry:
    """Attempts at levels, each on its own session."""

    def __init__(self, sessions: SessionRegistry) -> None:
        self.sessions = sessions
        self._attempts: dict[str, AttemptRecord] = {}
        self._lock = threading.Lock()

    def start(self, level: Level) -> AttemptRecord:
        session = self.sessions.create(level.device)
        with session.busy(), _RUN_LOCK:
            attempt = Attempt.start(
                level,
                self.sessions.devices_dir,
                self.sessions.data_dir,
                lab=session.lab,
            )
        record = AttemptRecord(uuid.uuid4().hex[:12], attempt, session)
        with self._lock:
            self._attempts[record.id] = record
        return record

    def get(self, aid: str) -> AttemptRecord:
        with self._lock:
            return self._attempts[aid]

    def submit(self, aid: str) -> AttemptRecord:
        record = self.get(aid)
        with record.session.busy():
            record.attempt.submit()
        return record


__all__ = ["AttemptClosed", "AttemptRegistry", "AttemptRecord"]
