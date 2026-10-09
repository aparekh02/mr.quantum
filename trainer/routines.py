"""Routines available to the trainer.

Upstream registers routines in a process-global registry at import time, and some
callers (upstream's own tests among them) clear that registry. Anything in the
trainer that runs routines calls :func:`register_builtin_routines` first, so it
never depends on import order.

Besides upstream's built-ins there is one trainer routine,
``charge_stability_diagram``: a thin wrapper that exposes upstream's own
``Device.sweep_2d`` through ``RoutineRunner``, so 2D maps are measured (and logged
and streamed) like everything else. It holds no tune-up logic.
"""

from typing import Any

import numpy as np

import stanza.routines.builtins as builtins
from stanza.exceptions import RoutineError
from stanza.logger.session import LoggerSession
from stanza.routines import RoutineContext, routine

MAX_POINTS_PER_AXIS = 256


def charge_stability_diagram(
    ctx: RoutineContext,
    gate_x: str,
    gate_y: str,
    x_range: list[float],
    y_range: list[float],
    points: int,
    measure_electrode: str,
    session: LoggerSession | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Measure current on a points x points grid of two gate voltages.

    Returns ``x`` and ``y`` axis voltages and ``current[i_y][i_x]``.
    """
    device = ctx.resources.device
    if not 2 <= points <= MAX_POINTS_PER_AXIS:
        raise RoutineError(
            f"points must be in [2, {MAX_POINTS_PER_AXIS}], got {points}"
        )
    for gate in (gate_x, gate_y):
        if gate not in device.control_gates:
            raise RoutineError(f"{gate} is not a controllable gate")
    if gate_x == gate_y:
        raise RoutineError("gate_x and gate_y must be different gates")
    for name, span in (("x_range", x_range), ("y_range", y_range)):
        if len(span) != 2 or span[0] == span[1]:
            raise RoutineError(f"{name} must be two different voltages, got {span}")
    xs = np.linspace(x_range[0], x_range[1], points)
    ys = np.linspace(y_range[0], y_range[1], points)
    # Device.sweep_2d loops gate_1 outermost; sweep y outer so rows follow y.
    _, currents = device.sweep_2d(
        gate_y, list(ys), gate_x, list(xs), measure_electrode, session=session
    )
    grid = np.array(currents).reshape(points, points)
    return {"x": xs.tolist(), "y": ys.tolist(), "current": grid.tolist()}


def register_builtin_routines() -> None:
    """(Re)register every upstream built-in routine, plus the trainer routines."""
    for name in builtins.__all__:
        routine(getattr(builtins, name))
    routine(charge_stability_diagram)
