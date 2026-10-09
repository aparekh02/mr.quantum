"""Gate leakage and charge-noise physics."""

import math

import numpy as np
import pytest

from trainer.physics.leakage import GROUND, LeakageLink, leakage_currents
from trainer.physics.noise import ou_step

# --- leakage ------------------------------------------------------------------


def test_no_links_no_leakage() -> None:
    assert leakage_currents({"A": 1.0, "B": -1.0}, []) == {}


def test_ohmic_link_between_two_gates() -> None:
    link = LeakageLink("A", "B", resistance=1e8, onset=0.0)
    out = leakage_currents({"A": 0.5, "B": -0.5}, [link])
    assert out["A"] == pytest.approx(1e-8)
    assert out["B"] == pytest.approx(-1e-8)


def test_leakage_below_onset_is_zero() -> None:
    link = LeakageLink("A", "B", resistance=1e8, onset=0.6)
    out = leakage_currents({"A": 0.5, "B": 0.0}, [link])
    assert out == {"A": 0.0, "B": 0.0}


def test_leakage_above_onset_is_linear_in_excess() -> None:
    link = LeakageLink("A", "B", resistance=1e8, onset=0.6)
    out = leakage_currents({"A": -1.0, "B": 0.0}, [link])
    assert out["A"] == pytest.approx(-0.4 / 1e8)
    assert out["B"] == pytest.approx(0.4 / 1e8)


def test_leakage_to_ground() -> None:
    link = LeakageLink("A", GROUND, resistance=1e9, onset=0.0)
    out = leakage_currents({"A": 2.0}, [link])
    assert out == {"A": pytest.approx(2e-9)}


def test_links_superpose() -> None:
    links = [
        LeakageLink("A", "B", resistance=1e8, onset=0.0),
        LeakageLink("A", GROUND, resistance=1e8, onset=0.0),
    ]
    out = leakage_currents({"A": 1.0, "B": 0.0}, links)
    assert out["A"] == pytest.approx(2e-8)
    assert out["B"] == pytest.approx(-1e-8)


def test_missing_gate_voltage_reads_as_zero() -> None:
    out = leakage_currents({"A": 1.0}, [LeakageLink("A", "B", 1e8, 0.0)])
    assert out["B"] == pytest.approx(-1e-8)


@pytest.mark.parametrize(
    ("resistance", "onset", "match"),
    [(0.0, 0.0, "resistance"), (-1.0, 0.0, "resistance"), (1e8, -0.1, "onset")],
)
def test_link_validation(resistance: float, onset: float, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        LeakageLink("A", "B", resistance=resistance, onset=onset)


def test_link_to_itself_rejected() -> None:
    with pytest.raises(ValueError, match="itself"):
        LeakageLink("A", "A", resistance=1e8, onset=0.0)


# --- Ornstein-Uhlenbeck charge noise ----------------------------------------


def test_ou_zero_dt_is_unchanged_and_draws_nothing() -> None:
    rng = np.random.default_rng(7)
    before = rng.bit_generator.state
    assert ou_step(0.3, 0.0, tau=1.0, sigma=0.01, rng=rng) == 0.3
    assert rng.bit_generator.state == before


def test_ou_zero_sigma_decays_deterministically() -> None:
    x = ou_step(1.0, 0.5, tau=1.0, sigma=0.0, rng=np.random.default_rng(0))
    assert x == pytest.approx(math.exp(-0.5))


def test_ou_golden_step(rng: np.random.Generator) -> None:
    xi = np.random.default_rng(12345).standard_normal()
    a = math.exp(-0.1 / 2.0)
    expected = 0.2 * a + 0.05 * math.sqrt(1 - a * a) * xi
    assert ou_step(0.2, 0.1, tau=2.0, sigma=0.05, rng=rng) == pytest.approx(expected)


def test_ou_stationary_statistics(rng: np.random.Generator) -> None:
    x, samples = 0.0, []
    for _ in range(20000):
        x = ou_step(x, 0.5, tau=1.0, sigma=0.02, rng=rng)
        samples.append(x)
    assert np.std(samples) == pytest.approx(0.02, rel=0.05)
    # Correlation at lag dt is exp(-dt/tau).
    s = np.array(samples)
    lag1 = np.corrcoef(s[:-1], s[1:])[0, 1]
    assert lag1 == pytest.approx(math.exp(-0.5), abs=0.03)


@pytest.mark.parametrize(
    ("dt", "tau", "sigma", "match"),
    [(-1.0, 1.0, 0.1, "dt"), (1.0, 0.0, 0.1, "tau"), (1.0, 1.0, -0.1, "sigma")],
)
def test_ou_validation(dt: float, tau: float, sigma: float, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        ou_step(0.0, dt, tau=tau, sigma=sigma, rng=np.random.default_rng(0))
