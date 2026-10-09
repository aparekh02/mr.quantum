"""Signal analysis behind the local models.

These functions see only measured data (current traces and current maps), exactly
like the cloud models they stand in for. They never read simulator state.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import gaussian_filter, gaussian_filter1d
from scipy.signal import find_peaks

ArrayLike = Sequence[float] | NDArray[np.floating]

MIN_SNR_1D = 12.0
"""Full trace range must exceed this many noise standard deviations."""
MIN_PROMINENCE = 0.08
"""Minimum peak prominence as a fraction of the trace range."""
BLOCKADE_CONTRAST = 0.5
"""Median peak-to-valley contrast needed to call a trace Coulomb blockade."""
DQD_SECOND_FAMILY = 0.2
"""Weight fraction a second line orientation needs for a double-dot verdict."""
DQD_MIN_SEPARATION_DEG = 35.0


def _oriented(x: NDArray[np.float64]) -> NDArray[np.float64]:
    """Flip mostly-negative signals (e.g. current read at the source)."""
    return -x if abs(x.min()) > abs(x.max()) else x


def _robust_noise(diffs: NDArray[np.float64]) -> float:
    if diffs.size == 0:
        return 0.0
    mad = float(np.median(np.abs(diffs - np.median(diffs))))
    return 1.4826 * mad / math.sqrt(2.0)


def detect_coulomb_peaks(trace: ArrayLike) -> list[int]:
    """Indices of Coulomb peaks in a current trace, sorted."""
    x = np.asarray(trace, dtype=np.float64).ravel()
    if x.size < 5:
        return []
    x = _oriented(x)
    span = float(np.ptp(x))
    if span == 0.0:
        return []
    y = (x - x.min()) / span
    noise = _robust_noise(np.diff(y))
    if noise > 0 and 1.0 / noise < MIN_SNR_1D:
        return []
    smooth = gaussian_filter1d(y, 1.0)
    peaks, _ = find_peaks(
        smooth, prominence=max(6.0 * noise, MIN_PROMINENCE), distance=3
    )
    return [int(p) for p in peaks]


def _contrasts(x: NDArray[np.float64], peaks: list[int]) -> list[float]:
    if len(peaks) == 1:
        p = peaks[0]
        left = x[:p].min() if p > 0 else x[p]
        right = x[p + 1 :].min() if p + 1 < x.size else x[p]
        valley, top = max(left, right), x[p]
        return [float((top - valley) / top) if top > 0 else 0.0]
    out = []
    for a, b in zip(peaks[:-1], peaks[1:], strict=True):
        top = min(x[a], x[b])
        valley = x[a : b + 1].min()
        out.append(float((top - valley) / top) if top > 0 else 0.0)
    return out


def classify_coulomb_blockade(trace: ArrayLike) -> tuple[bool, float]:
    """Is this trace Coulomb blockade? Returns (verdict, score in [0, 1]).

    Blockade means peaks with current falling close to zero between them, so the
    score is the median peak-to-valley contrast measured from zero current.
    """
    x = np.asarray(trace, dtype=np.float64).ravel()
    peaks = detect_coulomb_peaks(x)
    if not peaks:
        return False, 0.0
    x = _oriented(x)
    score = float(np.clip(np.median(_contrasts(x, peaks)), 0.0, 1.0))
    return score >= BLOCKADE_CONTRAST, score


def _line_orientations(
    image: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    n = image.shape[0]
    sigma = max(0.7, n / 32.0)
    hxx = gaussian_filter(image, sigma, order=(0, 2))
    hyy = gaussian_filter(image, sigma, order=(2, 0))
    hxy = gaussian_filter(image, sigma, order=(1, 1))
    half_trace = 0.5 * (hxx + hyy)
    radius = np.sqrt((0.5 * (hxx - hyy)) ** 2 + hxy**2)
    ridge = np.clip(-(half_trace - radius), 0.0, None)  # -lambda_min
    angle = np.mod(0.5 * np.arctan2(2.0 * hxy, hxx - hyy), np.pi)
    margin = max(1, n // 16)
    inner = (slice(margin, n - margin), slice(margin, n - margin))
    return ridge[inner].ravel(), angle[inner].ravel()


def classify_double_dot(image: ArrayLike) -> tuple[bool, float]:
    """Does this current map show a double dot? Returns (verdict, score in [0, 1]).

    A double dot's charge-stability diagram has transition lines in two distinct
    orientations (one per dot); a single dot has one family of parallel lines.
    """
    a = np.asarray(image, dtype=np.float64)
    if a.ndim != 2 or a.shape[0] != a.shape[1]:
        raise ValueError(f"expected a square 2D image, got shape {a.shape}")
    span = float(np.ptp(a))
    if span == 0.0:
        return False, 0.0
    a = _oriented(a)
    a = (a - a.min()) / span
    noise = _robust_noise(np.diff(a, axis=1).ravel())
    if noise > 0 and 1.0 / noise < 6.0:
        return False, 0.0

    ridge, angle = _line_orientations(a)
    strong = ridge > 0.25 * ridge.max() if ridge.max() > 0 else ridge > 0
    if strong.sum() < 4:
        return False, 0.0
    bins = 18
    raw, _ = np.histogram(
        angle[strong], bins=bins, range=(0, np.pi), weights=ridge[strong]
    )
    total = float(raw.sum())
    if total == 0:
        return False, 0.0
    # Smooth circularly to locate modes; measure weights on the raw histogram.
    smooth = raw + 0.5 * (np.roll(raw, 1) + np.roll(raw, -1))

    bin_deg = 180.0 / bins
    first = int(np.argmax(smooth))
    offsets = (np.arange(bins) - first + bins // 2) % bins - bins // 2
    separation = np.abs(offsets) * bin_deg
    second = int(np.argmax(np.where(separation >= DQD_MIN_SEPARATION_DEG, smooth, 0.0)))
    window = [(second + k) % bins for k in (-1, 0, 1)]
    fraction = float(raw[window].sum() / total)
    score = float(np.clip(fraction / (2 * DQD_SECOND_FAMILY), 0.0, 1.0))
    return fraction >= DQD_SECOND_FAMILY, score
