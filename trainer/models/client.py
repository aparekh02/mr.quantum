"""A drop-in for ``conductorquantum.ConductorQuantum`` that runs locally.

Upstream routines call ``ctx.resources.models_client.models.execute(model=..., data=...)``
and read ``.output``. This client offers the same shape for the four model ids
upstream uses, backed by :mod:`trainer.models.analysis`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from trainer.models.analysis import (
    classify_coulomb_blockade,
    classify_double_dot,
    detect_coulomb_peaks,
)


@dataclass(frozen=True)
class ModelResult:
    output: dict[str, Any]


def _cb_classifier(data: Any) -> dict[str, Any]:
    verdict, score = classify_coulomb_blockade(data)
    return {"classification": verdict, "score": score}


def _peak_detector(data: Any) -> dict[str, Any]:
    return {"peak_indices": detect_coulomb_peaks(data)}


def _csd_classifier(size: int) -> Callable[[Any], dict[str, Any]]:
    def run(data: Any) -> dict[str, Any]:
        image = np.asarray(data, dtype=np.float64)
        if image.shape != (size, size):
            raise ValueError(f"expected a {size}x{size} map, got shape {image.shape}")
        verdict, score = classify_double_dot(image)
        return {"classification": verdict, "score": score}

    return run


SUPPORTED_MODELS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "coulomb-blockade-classifier-v3": _cb_classifier,
    "coulomb-blockade-peak-detector-v2": _peak_detector,
    "charge-stability-diagram-binary-classifier-v2-16x16": _csd_classifier(16),
    "charge-stability-diagram-binary-classifier-v1-48x48": _csd_classifier(48),
}


class _Models:
    def __init__(self, calls: Counter[str]) -> None:
        self._calls = calls

    def execute(self, model: str, data: Any) -> ModelResult:
        if model not in SUPPORTED_MODELS:
            raise ValueError(
                f"Unknown model '{model}'. Supported: {sorted(SUPPORTED_MODELS)}"
            )
        self._calls[model] += 1
        return ModelResult(output=SUPPORTED_MODELS[model](data))


class LocalModelsClient:
    """Register as the ``models_client`` resource in place of the cloud SDK."""

    name = "models_client"

    def __init__(self) -> None:
        self._calls: Counter[str] = Counter()
        self.models = _Models(self._calls)

    @property
    def calls(self) -> dict[str, int]:
        """How many times each model was executed (every call counts)."""
        return dict(self._calls)
