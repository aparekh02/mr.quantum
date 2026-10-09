"""A DataLogger that also publishes everything it logs to an EventLog.

Upstream's writers only see data when a session flushes. To stream live, this
subclass wraps each new session's public logging methods on the instance, so
upstream's files are still written exactly as before.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from stanza.logger.data_logger import DataLogger
from stanza.logger.session import LoggerSession, SweepContext
from trainer.api.events import EventLog


class StreamingDataLogger(DataLogger):
    """Drop-in for the runner's ``logger`` resource."""

    def __init__(
        self, routine_name: str, base_dir: str | Path, events: EventLog, **kwargs: Any
    ) -> None:
        super().__init__(routine_name=routine_name, base_dir=base_dir, **kwargs)
        self.events = events

    def create_session(
        self, session_id: str | None = None, group_name: str | None = None
    ) -> LoggerSession:
        session = super().create_session(session_id=session_id, group_name=group_name)
        _tee(session, self.events)
        return session


def _tee(session: LoggerSession, events: EventLog) -> None:
    routine = session.session_id
    namespace = vars(session)
    log_measurement = session.log_measurement
    log_sweep = session.log_sweep
    open_sweep = session.sweep

    def measurement(
        name: str,
        data: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        routine_name: str | None = None,
    ) -> None:
        log_measurement(name, data, metadata, routine_name)
        kind = (
            "analysis"
            if (metadata or {}).get("data_type") == "analysis"
            else "measurement"
        )
        events.append(kind, routine, name, data)

    def sweep_logged(
        name: str,
        x_data: Any,
        y_data: Any,
        x_label: str,
        y_label: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        log_sweep(name, x_data, y_data, x_label, y_label, metadata)
        events.append(
            "sweep",
            routine,
            name,
            {
                "x_label": x_label,
                "y_label": y_label,
                "x_data": x_data,
                "y_data": y_data,
            },
        )

    def sweep_context(
        name: str,
        x_label: str | list[str],
        y_label: str,
        metadata: dict[str, Any] | None = None,
    ) -> SweepContext:
        context = open_sweep(name, x_label, y_label, metadata)
        _tee_sweep(context, events, routine)
        return context

    namespace["log_measurement"] = measurement
    namespace["log_sweep"] = sweep_logged
    namespace["sweep"] = sweep_context


def _tee_sweep(context: SweepContext, events: EventLog, routine: str) -> None:
    namespace = vars(context)
    append: Callable[[Any, Any], None] = context.append
    end: Callable[[], None] = context.end
    xs: list[Any] = []
    ys: list[Any] = []

    def point(x_data: Any, y_data: Any) -> None:
        append(x_data, y_data)
        xs.append(list(x_data))
        ys.extend(list(y_data))
        events.append("sweep_point", routine, context.name, {"x": x_data, "y": y_data})

    def finished() -> None:
        end()
        events.append(
            "sweep",
            routine,
            context.name,
            {
                "x_label": context.x_label,
                "y_label": context.y_label,
                "x_data": xs,
                "y_data": ys,
            },
        )

    namespace["append"] = point
    namespace["end"] = finished
