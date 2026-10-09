"""Time-correlated noise processes."""

from __future__ import annotations

import math

import numpy as np


def ou_step(
    x: float, dt: float, tau: float, sigma: float, rng: np.random.Generator
) -> float:
    """Advance an Ornstein-Uhlenbeck process exactly by ``dt``.

    Stationary standard deviation ``sigma``, correlation time ``tau``. A zero
    ``dt`` returns ``x`` unchanged without consuming randomness.
    """
    if dt < 0:
        raise ValueError(f"dt must be non-negative, got {dt}")
    if tau <= 0:
        raise ValueError(f"tau must be positive, got {tau}")
    if sigma < 0:
        raise ValueError(f"sigma must be non-negative, got {sigma}")
    if dt == 0:
        return x
    decay = math.exp(-dt / tau)
    if sigma == 0:
        return x * decay
    return x * decay + sigma * math.sqrt(1.0 - decay * decay) * float(
        rng.standard_normal()
    )
