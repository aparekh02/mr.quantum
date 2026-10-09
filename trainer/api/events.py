"""An append-only, sequence-numbered event log shared by a session's runs.

Every event gets the next integer ``seq``. Readers ask for events after a cursor,
so a client that reconnects resumes exactly where it stopped: no loss, no reorder.
"""

from __future__ import annotations

import dataclasses
import math
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

KINDS = frozenset(
    {
        "run_started",
        "run_finished",
        "run_failed",
        "sweep_point",
        "sweep",
        "measurement",
        "analysis",
        "voltages",
    }
)


def jsonable(value: Any) -> Any:
    """Convert routine results and logged data into plain JSON values.

    NaN and infinities become ``None``; unknown objects become their ``repr``.
    """
    if value is None or isinstance(value, bool | str | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return jsonable(dataclasses.asdict(value))
    return repr(value)


@dataclass(frozen=True)
class Event:
    seq: int
    time: float
    kind: str
    routine: str | None
    name: str
    data: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "time": self.time,
            "kind": self.kind,
            "routine": self.routine,
            "name": self.name,
            "data": self.data,
        }


class EventLog:
    """Thread-safe log. ``clock`` stamps events (the simulator's virtual time)."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or (lambda: 0.0)
        self._events: list[Event] = []
        self._lock = threading.Lock()
        self._listeners: list[Callable[[Event], None]] = []

    @property
    def last_seq(self) -> int:
        with self._lock:
            return len(self._events)

    def append(self, kind: str, routine: str | None, name: str, data: Any) -> Event:
        if kind not in KINDS:
            raise ValueError(f"unknown event kind {kind!r}")
        with self._lock:
            event = Event(
                seq=len(self._events) + 1,
                time=float(self._clock()),
                kind=kind,
                routine=routine,
                name=name,
                data=jsonable(data),
            )
            self._events.append(event)
            listeners = list(self._listeners)
        for listener in listeners:
            listener(event)
        return event

    def since(self, cursor: int) -> list[Event]:
        """Events with ``seq > cursor``, in order."""
        if cursor < 0:
            raise ValueError(f"cursor must be >= 0, got {cursor}")
        with self._lock:
            return self._events[cursor:]

    def subscribe(self, listener: Callable[[Event], None]) -> Callable[[], None]:
        """Call ``listener`` after every append; returns an unsubscribe function."""
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe
