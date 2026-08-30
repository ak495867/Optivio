from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Kalman1D:
    process_var: float = 1e-5
    measurement_var: float = 1e-3
    mean: float = 0.0
    variance: float = 1.0
    initialized: bool = False

    def update(self, observation: float) -> float:
        z = float(observation)
        if not self.initialized:
            self.mean, self.initialized = z, True
            return self.mean
        prior_var = self.variance + self.process_var
        gain = prior_var / (prior_var + self.measurement_var)
        self.mean = self.mean + gain * (z - self.mean)
        self.variance = (1.0 - gain) * prior_var
        return self.mean

    def filter(self, observations: np.ndarray) -> np.ndarray:
        return np.array([self.update(x) for x in np.asarray(observations, dtype=float)])


def mathematical_factors(close: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    """Construct causal momentum, reversal, volatility, and range factors."""
    ret = close.pct_change()
    out = pd.DataFrame(index=close.index)
    out["momentum"] = close / close.shift(lookback) - 1.0
    out["reversal"] = -ret.rolling(5, min_periods=5).sum()
    out["volatility"] = ret.rolling(lookback, min_periods=lookback).std()
    out["trend_strength"] = out["momentum"] / out["volatility"].replace(0, np.nan)
    return out.replace([np.inf, -np.inf], np.nan)


def bayesian_decay(
    weights: np.ndarray,
    age: np.ndarray,
    half_life: float = 20.0,
    prior_strength: float = 0.25,
) -> np.ndarray:
    """Shrink older evidence toward a neutral prior; age must be known at decision time."""
    if half_life <= 0 or prior_strength < 0 or prior_strength > 1:
        raise ValueError("invalid decay parameters")
    w = np.asarray(weights, dtype=float)
    a = np.maximum(np.asarray(age, dtype=float), 0.0)
    decay = np.exp(-np.log(2.0) * a / half_life)
    return (1.0 - prior_strength) * w * decay


class ActiveRegimeClassifier:
    """Fast rule-based regime state; thresholds must be frozen before evaluation."""

    def __init__(self, vol_threshold: float = 0.025, trend_threshold: float = 0.01):
        self.vol_threshold, self.trend_threshold = vol_threshold, trend_threshold

    def classify(self, trend: float, volatility: float) -> str:
        if volatility >= self.vol_threshold:
            return "high_volatility"
        if abs(trend) >= self.trend_threshold:
            return "trending_up" if trend > 0 else "trending_down"
        return "range_bound"

    def exposure_scale(self, regime: str) -> float:
        return {
            "high_volatility": 0.35,
            "trending_up": 1.0,
            "trending_down": 0.60,
            "range_bound": 0.70,
        }.get(regime, 0.25)
