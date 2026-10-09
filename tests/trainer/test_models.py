"""Local stand-ins for the Conductor Quantum models (trainer/models/)."""

from typing import Any

import numpy as np
import pytest

from trainer.models.analysis import (
    classify_coulomb_blockade,
    classify_double_dot,
    detect_coulomb_peaks,
)
from trainer.models.client import SUPPORTED_MODELS, LocalModelsClient

N = 256


def _sech2(x: np.ndarray, centre: float, width: float) -> np.ndarray:
    result: np.ndarray = 1.0 / np.cosh((x - centre) / width) ** 2
    return result


def _coulomb_trace(
    rng: np.random.Generator,
    centres: list[float],
    noise: float = 0.01,
    background: float = 0.0,
) -> np.ndarray:
    x = np.arange(N, dtype=np.float64)
    y = sum(_sech2(x, c, 3.0) for c in centres) + background * x / N
    trace: np.ndarray = 1e-9 * (y + noise * rng.standard_normal(N))
    return trace


# --- 1D peak detection --------------------------------------------------------


def test_detects_every_peak_position(rng: np.random.Generator) -> None:
    centres = [30.0, 80.0, 130.0, 180.0, 230.0]
    peaks = detect_coulomb_peaks(_coulomb_trace(rng, centres))
    assert len(peaks) == 5
    assert np.abs(np.array(peaks) - np.array(centres)).max() <= 2


def test_detects_peaks_on_a_sloped_background(rng: np.random.Generator) -> None:
    centres = [40.0, 100.0, 160.0, 220.0]
    peaks = detect_coulomb_peaks(_coulomb_trace(rng, centres, background=3.0))
    assert len(peaks) == 4


def test_peak_indices_are_sorted_python_ints(rng: np.random.Generator) -> None:
    peaks = detect_coulomb_peaks(_coulomb_trace(rng, [200.0, 50.0]))
    assert peaks == sorted(peaks)
    assert all(type(p) is int for p in peaks)


def test_noise_has_no_peaks(rng: np.random.Generator) -> None:
    assert detect_coulomb_peaks(1e-12 * rng.standard_normal(N)) == []


def test_constant_trace_has_no_peaks() -> None:
    assert detect_coulomb_peaks(np.full(N, 1e-9)) == []


def test_pinchoff_curve_has_no_peaks(rng: np.random.Generator) -> None:
    x = np.linspace(-1, 1, N)
    trace = 1e-9 * (0.5 * (1 + np.tanh(x / 0.2)) + 0.005 * rng.standard_normal(N))
    assert detect_coulomb_peaks(trace) == []


def test_short_or_empty_trace() -> None:
    assert detect_coulomb_peaks(np.array([])) == []
    assert detect_coulomb_peaks(np.array([1.0, 2.0])) == []


def test_accepts_lists_and_float32(rng: np.random.Generator) -> None:
    trace = _coulomb_trace(rng, [60.0, 190.0])
    assert detect_coulomb_peaks(list(trace)) == detect_coulomb_peaks(
        trace.astype(np.float32)
    )


# --- 1D classification ------------------------------------------------------


def test_coulomb_oscillations_classified_true(rng: np.random.Generator) -> None:
    is_cb, score = classify_coulomb_blockade(_coulomb_trace(rng, [40.0, 120.0, 200.0]))
    assert is_cb
    assert 0.5 < score <= 1.0


def test_pinchoff_classified_false(rng: np.random.Generator) -> None:
    x = np.linspace(-1, 1, N)
    is_cb, score = classify_coulomb_blockade(
        1e-9 * (0.5 * (1 + np.tanh(x / 0.2)) + 0.005 * rng.standard_normal(N))
    )
    assert not is_cb
    assert 0.0 <= score < 0.5


def test_noise_classified_false(rng: np.random.Generator) -> None:
    is_cb, _ = classify_coulomb_blockade(1e-12 * rng.standard_normal(N))
    assert not is_cb


def test_shallow_ripples_on_open_channel_classified_false(
    rng: np.random.Generator,
) -> None:
    # Peaks riding on a large constant background: no blockade, current never
    # drops between "peaks". A real classifier rejects this.
    x = np.arange(N, dtype=np.float64)
    y = 1.0 + 0.05 * sum(_sech2(x, c, 3.0) for c in [50.0, 120.0, 190.0])
    is_cb, _ = classify_coulomb_blockade(1e-9 * (y + 0.002 * rng.standard_normal(N)))
    assert not is_cb


def test_single_isolated_peak_classified_true(rng: np.random.Generator) -> None:
    is_cb, _ = classify_coulomb_blockade(_coulomb_trace(rng, [128.0]))
    assert is_cb


def test_score_increases_with_contrast(rng: np.random.Generator) -> None:
    x = np.arange(N, dtype=np.float64)
    peaks = sum(_sech2(x, c, 3.0) for c in [50.0, 120.0, 190.0])
    noise = 0.005 * rng.standard_normal(N)
    _, deep = classify_coulomb_blockade(1e-9 * (peaks + noise))
    _, shallow = classify_coulomb_blockade(1e-9 * (0.4 + peaks + noise))
    assert deep > shallow


# --- 2D double-dot classification ----------------------------------------------


def _lines(
    n: int, slope_deg: float, period: float, width: float, phase: float = 0.0
) -> np.ndarray:
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    theta = np.deg2rad(slope_deg)
    # Signed distance across a family of parallel lines at angle theta.
    d = -xx * np.sin(theta) + yy * np.cos(theta) + phase
    d = (d % period) - period / 2
    result: np.ndarray = 1.0 / np.cosh(d / width) ** 2
    return result


@pytest.mark.parametrize("n", [16, 48])
def test_two_line_families_is_double_dot(n: int, rng: np.random.Generator) -> None:
    period, width = n / 2.5, n / 24
    image = _lines(n, 100.0, period, width) + _lines(n, 165.0, period, width, 1.3)
    is_dqd, score = classify_double_dot(image + 0.03 * rng.standard_normal((n, n)))
    assert is_dqd
    assert 0.5 < score <= 1.0


@pytest.mark.parametrize("n", [16, 48])
def test_one_line_family_is_not_double_dot(n: int, rng: np.random.Generator) -> None:
    image = _lines(n, 135.0, n / 2.5, n / 24)
    is_dqd, score = classify_double_dot(image + 0.03 * rng.standard_normal((n, n)))
    assert not is_dqd
    assert score < 0.5


@pytest.mark.parametrize("n", [16, 48])
def test_noise_is_not_double_dot(n: int, rng: np.random.Generator) -> None:
    is_dqd, _ = classify_double_dot(rng.standard_normal((n, n)))
    assert not is_dqd


def test_blank_image_is_not_double_dot() -> None:
    is_dqd, score = classify_double_dot(np.zeros((16, 16)))
    assert not is_dqd
    assert score == 0.0


def test_double_dot_rejects_non_square() -> None:
    with pytest.raises(ValueError, match="2D"):
        classify_double_dot(np.zeros(16))


# --- client --------------------------------------------------------------------


def test_client_shape_matches_upstream_usage(rng: np.random.Generator) -> None:
    client = LocalModelsClient()
    assert client.name == "models_client"
    trace = _coulomb_trace(rng, [40.0, 120.0, 200.0])

    out: dict[str, Any] = client.models.execute(
        model="coulomb-blockade-classifier-v3", data=trace
    ).output
    assert out["classification"] is True
    assert isinstance(out["score"], float)

    peaks = client.models.execute(
        model="coulomb-blockade-peak-detector-v2", data=trace
    ).output
    assert len(peaks["peak_indices"]) == 3


@pytest.mark.parametrize(
    ("model", "n"),
    [
        ("charge-stability-diagram-binary-classifier-v2-16x16", 16),
        ("charge-stability-diagram-binary-classifier-v1-48x48", 48),
    ],
)
def test_client_csd_models(model: str, n: int, rng: np.random.Generator) -> None:
    image = _lines(n, 100.0, n / 2.5, n / 24) + _lines(n, 165.0, n / 2.5, n / 24, 1.3)
    out = LocalModelsClient().models.execute(model=model, data=image).output
    assert out["classification"] is True
    assert 0.0 <= out["score"] <= 1.0


def test_client_rejects_wrong_csd_size() -> None:
    with pytest.raises(ValueError, match="16x16"):
        LocalModelsClient().models.execute(
            model="charge-stability-diagram-binary-classifier-v2-16x16",
            data=np.zeros((48, 48)),
        )


def test_client_rejects_unknown_model() -> None:
    with pytest.raises(ValueError, match="Unknown model"):
        LocalModelsClient().models.execute(model="gpt-dots", data=[1.0])


def test_supported_models_are_the_four_upstream_uses() -> None:
    assert set(SUPPORTED_MODELS) == {
        "coulomb-blockade-classifier-v3",
        "coulomb-blockade-peak-detector-v2",
        "charge-stability-diagram-binary-classifier-v2-16x16",
        "charge-stability-diagram-binary-classifier-v1-48x48",
    }


def test_client_counts_calls() -> None:
    client = LocalModelsClient()
    client.models.execute(model="coulomb-blockade-peak-detector-v2", data=[0.0] * 8)
    client.models.execute(model="coulomb-blockade-peak-detector-v2", data=[0.0] * 8)
    assert client.calls == {"coulomb-blockade-peak-detector-v2": 2}
