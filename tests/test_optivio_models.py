import numpy as np
import pandas as pd

from options_agent.execution.portfolio import PortfolioManager
from options_agent.models.regime_factor import (
    ActiveRegimeClassifier,
    Kalman1D,
    bayesian_decay,
    mathematical_factors,
)
from options_agent.validation.benchmark import zero_shot_metrics


def test_kalman_converges_toward_observation():
    k = Kalman1D()
    values = k.filter(np.concatenate(([0.0], np.ones(19))))
    assert values[-1] > values[0]
    assert abs(values[-1] - 1) < 0.1


def test_factors_are_causal():
    idx = pd.date_range("2020-01-01", periods=30, tz="UTC")
    close = pd.DataFrame({"A": np.arange(1, 31, dtype=float)}, index=idx)
    f = mathematical_factors(close, lookback=5)
    assert pd.isna(f.iloc[0]["momentum"])
    assert pd.isna(f.iloc[0]["volatility"])


def test_bayesian_decay_reduces_old_evidence():
    assert bayesian_decay(np.array([1.0]), np.array([40.0]), half_life=20)[0] < 0.5


def test_regime_scale_is_conservative_in_high_vol():
    c = ActiveRegimeClassifier()
    assert c.exposure_scale(c.classify(0.0, 0.10)) < c.exposure_scale("trending_up")


def test_portfolio_weights_are_capped():
    w = PortfolioManager().target_weights(np.array([10.0, 1.0]), np.array([0.1, 0.1]))
    assert np.max(np.abs(w)) <= 0.20 + 1e-12


def test_zero_shot_report_marks_frozen_evaluation():
    report = zero_shot_metrics(
        np.array([0.01, -0.005, 0.002]), np.array([1000, 2000, 1500])
    )
    assert report.zero_shot and report.p95_latency_us > 0
