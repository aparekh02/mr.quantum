"""Test-only routines, registered on demand (upstream tests clear the registry)."""

from typing import Any

import numpy as np

from stanza.routines import routine


def moves_then_raises(ctx: Any, gate: str, voltage: float, **kwargs: Any) -> None:
    ctx.resources.device.jump({gate: voltage})
    raise RuntimeError("mid-run failure")


def sweep(ctx: Any, n: int, session: Any = None, **kwargs: Any) -> int:
    ctx.resources.device.jump({"IN_B": 0.001})
    ctx.resources.device.sweep_1d(
        "PB", list(np.linspace(-1.0, -0.5, n)), "OUT_B", session=session
    )
    return n


def register() -> None:
    routine(moves_then_raises, name="api_test_moves_then_raises")
    routine(sweep, name="api_test_sweep")
