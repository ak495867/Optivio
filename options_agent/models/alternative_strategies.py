from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ArbitrageSignal:
    kind: str
    edge: float
    confidence: float
    legs: tuple[str, ...]
    reason: str


class SurfaceArbitrageModel:
    """Detect parity and vertical/calendar inconsistencies from one timestamp only."""
    def __init__(self, risk_free_rate: float = 0.0, min_edge: float = 0.02):
        self.risk_free_rate, self.min_edge = risk_free_rate, min_edge

    def put_call_parity(self, call_mid: float, put_mid: float, spot: float, strike: float, time_to_expiry: float) -> ArbitrageSignal | None:
        rhs = spot - strike * np.exp(-self.risk_free_rate * time_to_expiry)
        edge = float((call_mid - put_mid) - rhs)
        if abs(edge) < self.min_edge:
            return None
        return ArbitrageSignal("put_call_parity", abs(edge), min(1.0, abs(edge) / max(self.min_edge, 1e-9) / 5), ("call", "put", "underlying"), "parity residual exceeds threshold")

    def vertical_monotonicity(self, lower_mid: float, higher_mid: float, lower_strike: float, higher_strike: float) -> ArbitrageSignal | None:
        if higher_strike <= lower_strike:
            raise ValueError("strikes must be increasing")
        violation = higher_mid - lower_mid
        if violation <= self.min_edge:
            return None
        return ArbitrageSignal("vertical_monotonicity", float(violation), min(1.0, violation / 0.10), ("lower_strike", "higher_strike"), "higher-strike call is priced above lower-strike call")


@dataclass
class GaussianHMM:
    """Small diagonal Gaussian HMM with EM fit on a training fold and filtered inference."""
    states: int = 3
    iterations: int = 25
    seed: int = 7
    means: np.ndarray | None = None
    variances: np.ndarray | None = None
    transition: np.ndarray | None = None
    initial: np.ndarray | None = None

    def fit(self, observations: np.ndarray) -> GaussianHMM:
        x = np.asarray(observations, dtype=float).reshape(-1)
        if len(x) < self.states * 3:
            raise ValueError("not enough observations for HMM")
        self.means = np.quantile(x, np.linspace(.15, .85, self.states))
        self.variances = np.full(self.states, max(float(np.var(x)), 1e-6))
        self.transition = np.full((self.states, self.states), .15 / max(self.states - 1, 1))
        np.fill_diagonal(self.transition, .85)
        self.initial = np.full(self.states, 1 / self.states)
        for _ in range(self.iterations):
            emissions = self._emissions(x)
            alpha = np.zeros((len(x), self.states)); scale = np.zeros(len(x))
            alpha[0] = self.initial * emissions[0]; scale[0] = alpha[0].sum() + 1e-12; alpha[0] /= scale[0]
            for t in range(1, len(x)):
                alpha[t] = (alpha[t - 1] @ self.transition) * emissions[t]
                scale[t] = alpha[t].sum() + 1e-12; alpha[t] /= scale[t]
            beta = np.ones_like(alpha)
            for t in range(len(x) - 2, -1, -1):
                beta[t] = self.transition @ (emissions[t + 1] * beta[t + 1]); beta[t] /= scale[t + 1]
            gamma = alpha * beta; gamma /= gamma.sum(axis=1, keepdims=True) + 1e-12
            self.means = (gamma.T @ x) / (gamma.sum(axis=0) + 1e-12)
            self.variances = (gamma.T @ ((x[:, None] - self.means) ** 2)).sum(axis=0) / (gamma.sum(axis=0) + 1e-12)
            self.variances = np.maximum(self.variances, 1e-8)
            self.initial = gamma[0]
        return self

    def _emissions(self, x: np.ndarray) -> np.ndarray:
        if self.means is None or self.variances is None:
            raise RuntimeError("HMM must be fit")
        return np.exp(-.5 * (x[:, None] - self.means) ** 2 / self.variances) / np.sqrt(2 * np.pi * self.variances)

    def filtered_probabilities(self, observations: np.ndarray) -> np.ndarray:
        if self.transition is None or self.initial is None:
            raise RuntimeError("HMM must be fit")
        x = np.asarray(observations, dtype=float).reshape(-1)
        emissions = self._emissions(x)
        probs = np.zeros((len(x), self.states)); probs[0] = self.initial * emissions[0]; probs[0] /= probs[0].sum() + 1e-12
        for t in range(1, len(x)):
            probs[t] = (probs[t - 1] @ self.transition) * emissions[t]; probs[t] /= probs[t].sum() + 1e-12
        return probs

    def regime(self, observation: float) -> int:
        return int(np.argmax(self.filtered_probabilities(np.array([observation]))[-1]))


@dataclass
class PairsTradingModel:
    entry_z: float = 2.0
    exit_z: float = .5
    hedge: float | None = None
    spread_mean: float | None = None
    spread_std: float | None = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> PairsTradingModel:
        x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
        if x.shape != y.shape or x.size < 10:
            raise ValueError("pair series must be aligned and long enough")
        design = np.column_stack([np.ones(len(x)), x])
        self.hedge = float(np.linalg.lstsq(design, y, rcond=None)[0][1])
        spread = y - self.hedge * x
        self.spread_mean, self.spread_std = float(spread.mean()), max(float(spread.std()), 1e-8)
        return self

    def zscore(self, x: float, y: float) -> float:
        if self.hedge is None or self.spread_mean is None or self.spread_std is None:
            raise RuntimeError("pairs model must be fit")
        return float((y - self.hedge * x - self.spread_mean) / self.spread_std)

    def signal(self, x: float, y: float) -> int:
        z = self.zscore(x, y)
        return -1 if z > self.entry_z else 1 if z < -self.entry_z else 0
