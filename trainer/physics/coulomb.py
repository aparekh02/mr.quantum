"""Constant-interaction model of gate-defined quantum dots.

Each dot has a charging energy ``Ec`` (eV), lever arms ``alpha_g`` (eV/V) to every
gate it feels (the cross-capacitance matrix, row by row), and a background charge
offset. Gate voltages induce a charge ``n0 = p * sum_g alpha_g V_g / Ec + offset`` in
units of the elementary charge; ``p`` is the carrier polarity. The electrostatic
energy of an occupation vector ``n`` is ``E(n) = 1/2 (n - n0)^T U (n - n0)`` with
``U_ii = Ec_i`` and ``U_ij`` the mutual charging energy.

Transport uses the thermally broadened (sech^2) Coulomb peak, the same lineshape
upstream Stanza fits in ``stanza.routines.builtins.utils.peak_fitting``.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

DEFAULT_WINDOW = 3
"""Charge states considered on each side of the nearest integer to ``n0``."""


@dataclass(frozen=True)
class Dot:
    """One quantum dot.

    Attributes:
        charging_energy: Single-dot charging energy Ec (eV). Must be positive.
        lever_arms: Gate name -> lever arm (eV/V). Gates not listed couple with 0.
        charge_offset: Background induced charge (units of e).
    """

    charging_energy: float
    lever_arms: Mapping[str, float] = field(default_factory=dict)
    charge_offset: float = 0.0

    def __post_init__(self) -> None:
        if self.charging_energy <= 0:
            raise ValueError(
                f"charging_energy must be positive, got {self.charging_energy}"
            )
        for gate, alpha in self.lever_arms.items():
            if alpha < 0:
                raise ValueError(f"lever arm for {gate} must be >= 0, got {alpha}")


def induced_charge(dot: Dot, voltages: Mapping[str, float], polarity: int) -> float:
    """Gate-induced charge n0 on a dot (units of e)."""
    coupling = sum(alpha * voltages.get(g, 0.0) for g, alpha in dot.lever_arms.items())
    return polarity * coupling / dot.charging_energy + dot.charge_offset


def effective_induced_charge(
    n0: float, charging_energy: float, neighbours: Iterable[tuple[float, float]]
) -> float:
    """Shift n0 by neighbouring charges: each ``(mutual_energy, extra_charge)`` pair
    moves the dot's transitions by ``-mutual_energy * extra_charge / Ec``."""
    return n0 - sum(em * dq for em, dq in neighbours) / charging_energy


def resonance(mu: float, kT: float) -> float:
    """Thermal Coulomb-peak lineshape sech^2(mu / 2kT), 1 on resonance."""
    if kT <= 0:
        raise ValueError(f"kT must be positive, got {kT}")
    x = abs(mu) / (2.0 * kT)
    e = math.exp(-2.0 * x)
    return 4.0 * e / (1.0 + e) ** 2


def _charge_window(n0: float, window: int) -> range:
    centre = math.floor(n0)
    low = max(0, centre - window)
    high = max(low + 1, centre + window + 2)
    return range(low, high)


def coulomb_resonance(
    n0_eff: float, charging_energy: float, kT: float, window: int = DEFAULT_WINDOW
) -> float:
    """Sum of Coulomb peaks of one dot at induced charge ``n0_eff``, clipped to 1.

    The ``n -> n+1`` transition is resonant at ``n0 = n + 1/2``; occupations are
    never negative, so nothing conducts below the first charge.
    """
    total = 0.0
    for n in _charge_window(n0_eff, window):
        total += resonance(charging_energy * (n + 0.5 - n0_eff), kT)
    return min(total, 1.0)


def thermal_occupation(
    n0: NDArray[np.float64],
    interaction: NDArray[np.float64],
    kT: float,
    window: int = DEFAULT_WINDOW,
) -> NDArray[np.float64]:
    """Thermal average occupation of a set of coupled dots.

    Args:
        n0: Induced charge on each dot, shape (k,).
        interaction: Charging-energy matrix U (eV), shape (k, k).
        kT: Thermal energy (eV), positive.
        window: Charge states considered around each dot's induced charge.
    """
    n0 = np.asarray(n0, dtype=np.float64)
    u = np.asarray(interaction, dtype=np.float64)
    k = n0.shape[0]
    if n0.ndim != 1 or u.shape != (k, k):
        raise ValueError(f"shape mismatch: n0 {n0.shape}, interaction {u.shape}")
    if kT <= 0:
        raise ValueError(f"kT must be positive, got {kT}")
    ranges = [_charge_window(float(x), window) for x in n0]
    states = np.array(list(itertools.product(*ranges)), dtype=np.float64)
    d = states - n0
    energies = 0.5 * np.einsum("si,ij,sj->s", d, u, d)
    weights = np.exp(-(energies - energies.min()) / kT)
    result: NDArray[np.float64] = (weights[:, None] * states).sum(
        axis=0
    ) / weights.sum()
    return result


def dot_transmission(res: float, openness: float) -> float:
    """Transmission of one dot: blockade weighted by how closed the dot is.

    ``openness`` is the product of the turn-ons of the gates defining the dot: 1
    means an open wire (no blockade), 0 a fully isolated dot (peaks only).
    """
    if not 0.0 <= openness <= 1.0:
        raise ValueError(f"openness must be in [0, 1], got {openness}")
    return openness + (1.0 - openness) * res


def two_dot_transmission(
    res_1: float,
    res_2: float,
    openness_1: float,
    openness_2: float,
    merge: float,
    merged_transmission: float,
) -> float:
    """Transmission through two dots in series.

    Separate dots need both resonant (triple points, ``res_1 * res_2``); partly open
    dots also conduct along the other dot's lines. ``merge`` in [0, 1] blends in the
    single merged island as the inner barrier opens.
    """
    separate = dot_transmission(res_1, openness_1) * dot_transmission(res_2, openness_2)
    return (1.0 - merge) * separate + merge * merged_transmission


def merged_dot(a: Dot, b: Dot, mutual_energy: float) -> Dot:
    """The single island formed when two dots fully merge.

    Its charging energy is ``1 / sum(U^-1)`` and its induced charge is the sum of
    the two dots' induced charges.
    """
    ec_1, ec_2, em = a.charging_energy, b.charging_energy, mutual_energy
    ec_m = (ec_1 * ec_2 - em**2) / (ec_1 + ec_2 - 2.0 * em)
    gates = set(a.lever_arms) | set(b.lever_arms)
    lever_arms = {
        g: ec_m * (a.lever_arms.get(g, 0.0) / ec_1 + b.lever_arms.get(g, 0.0) / ec_2)
        for g in gates
    }
    return Dot(
        charging_energy=ec_m,
        lever_arms=lever_arms,
        charge_offset=a.charge_offset + b.charge_offset,
    )


def _sensing_centres(
    n0: NDArray[np.float64],
    interaction: NDArray[np.float64],
    sensing: NDArray[np.float64],
    iterations: int = 50,
) -> NDArray[np.float64]:
    """Rough charge estimate under occupation coupling, to centre the enumeration."""
    ec = np.diag(interaction)
    centre = n0.copy()
    for _ in range(iterations):
        occupied = np.clip(np.rint(centre), 0.0, None)
        updated = n0 - (sensing @ occupied) / ec
        if np.allclose(updated, centre):
            break
        centre = updated
    return centre


def joint_occupation(
    n0: NDArray[np.float64],
    interaction: NDArray[np.float64],
    sensing: NDArray[np.float64],
    kT: float,
    window: int = DEFAULT_WINDOW,
) -> NDArray[np.float64]:
    """Exact thermal occupation of all dots on a device.

    ``E(n) = sum_i Ec_i/2 (n_i - n0_i)^2 + sum_{i<j} U_ij (n_i - m_i)(n_j - m_j)
    + 1/2 n^T W n`` with ``m = max(n0, 0)``. ``U`` couples dots that share a channel
    through their charge deviations (constant interaction). The floor at zero keeps a
    depleted neighbour (gate-induced charge <= 0, no island) from pushing through the
    mutual term; its gate still acts through the direct lever arms. ``W``
    (symmetric, zero diagonal) couples dots in different channels through their
    actual charges, which is how a sensor feels a neighbouring dot.
    """
    n0 = np.asarray(n0, dtype=np.float64)
    u = np.asarray(interaction, dtype=np.float64)
    w = np.asarray(sensing, dtype=np.float64)
    k = n0.shape[0]
    if n0.ndim != 1 or u.shape != (k, k) or w.shape != (k, k):
        raise ValueError(
            f"shape mismatch: n0 {n0.shape}, interaction {u.shape}, sensing {w.shape}"
        )
    if kT <= 0:
        raise ValueError(f"kT must be positive, got {kT}")
    centres = _sensing_centres(n0, u, w)
    ranges = [_charge_window(float(c), window) for c in centres]
    states = np.array(list(itertools.product(*ranges)), dtype=np.float64)
    ec = np.diag(u)
    off = u - np.diag(ec)
    d_own = states - n0
    d_pair = states - np.clip(n0, 0.0, None)
    energies = (
        0.5 * (d_own**2 * ec).sum(axis=1)
        + 0.5 * np.einsum("si,ij,sj->s", d_pair, off, d_pair)
        + 0.5 * np.einsum("si,ij,sj->s", states, w, states)
    )
    weights = np.exp(-(energies - energies.min()) / kT)
    result: NDArray[np.float64] = (weights[:, None] * states).sum(
        axis=0
    ) / weights.sum()
    return result
