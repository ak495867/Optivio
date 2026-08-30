from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class HybridOutput:
    direction: np.ndarray
    expected_move: np.ndarray
    volatility: np.ndarray
    liquidity: np.ndarray
    embedding: np.ndarray


class KronosStyleTokenizer:
    """Causal hierarchical quantization of OHLCV/derived features.

    Quantization bounds must be estimated on the training fold and then frozen.
    """
    def __init__(self, levels: tuple[int, int] = (32, 16), low: np.ndarray | None = None, high: np.ndarray | None = None):
        self.levels = levels
        self.low, self.high = low, high

    def fit(self, x: np.ndarray) -> KronosStyleTokenizer:
        if x.ndim != 3:
            raise ValueError("expected [samples, time, features]")
        self.low = np.nanpercentile(x, 1, axis=(0, 1))
        self.high = np.nanpercentile(x, 99, axis=(0, 1))
        self.high = np.maximum(self.high, self.low + 1e-8)
        return self

    def transform(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if self.low is None or self.high is None:
            raise RuntimeError("tokenizer must be fitted on training data")
        z = np.clip((x - self.low) / (self.high - self.low), 0, 1)
        coarse = np.floor(z * self.levels[0]).astype(np.int64).clip(0, self.levels[0] - 1)
        fine = np.floor(z * self.levels[1]).astype(np.int64).clip(0, self.levels[1] - 1)
        return coarse, fine


class HiveStyleRingEncoder:
    """Numpy reference implementation of Hive’s ring-coupled recurrent dynamics."""
    def __init__(self, feature_dim: int, hidden_dim: int = 16, neighbors: int = 3, seed: int = 7):
        if neighbors < 1 or neighbors % 2 == 0:
            raise ValueError("neighbors must be a positive odd number")
        rng = np.random.default_rng(seed)
        self.hidden_dim, self.neighbors = hidden_dim, neighbors
        self.w_in = rng.normal(0, 0.12, (feature_dim, hidden_dim))
        self.w_rec = rng.normal(0, 0.08, (hidden_dim, hidden_dim))
        self.w_msg = rng.normal(0, 0.08, (hidden_dim, hidden_dim))
        self.bias = np.zeros(hidden_dim)
        self.tau = 0.15

    def encode(self, x: np.ndarray) -> np.ndarray:
        if x.ndim != 4:
            raise ValueError("expected [samples, assets, time, features]")
        b, assets, steps, _ = x.shape
        h = np.zeros((b, assets, self.hidden_dim))
        half = self.neighbors // 2
        for t in range(steps):
            mean_msg = np.zeros_like(h)
            for shift in range(-half, half + 1):
                mean_msg += np.roll(h, shift, axis=1)
            mean_msg /= self.neighbors
            z = x[:, :, t, :] @ self.w_in + h @ self.w_rec + mean_msg @ self.w_msg + self.bias
            h = (1 - self.tau) * h + self.tau * np.tanh(z)
        return h


class OptivioHybridModel:
    """Frozen-feature hybrid model for options signals.

    Kronos-style token statistics capture hierarchical OHLCV structure; Hive-style
    recurrence captures cross-asset and temporal interactions. The heads are fit
    with ridge regression on training folds only, then frozen for zero-shot tests.
    """
    def __init__(self, feature_dim: int, hidden_dim: int = 16, seed: int = 7):
        self.tokenizer = KronosStyleTokenizer()
        self.encoder = HiveStyleRingEncoder(feature_dim + 2, hidden_dim=hidden_dim, seed=seed)
        self.heads: dict[str, np.ndarray] = {}
        self.bias: dict[str, float] = {}
        self.fitted = False

    def _features(self, x: np.ndarray) -> np.ndarray:
        coarse, fine = self.tokenizer.transform(x)
        token_stats = np.stack([coarse.mean(axis=-1), fine.mean(axis=-1)], axis=-1)
        return np.concatenate([x, token_stats], axis=-1)

    def fit(self, x: np.ndarray, y: dict[str, np.ndarray], ridge: float = 1e-2) -> OptivioHybridModel:
        if x.ndim != 4:
            raise ValueError("x must be [samples, assets, time, features]")
        self.tokenizer.fit(x.reshape(-1, x.shape[2], x.shape[3]))
        emb = self.encoder.encode(self._features(x))
        design = np.concatenate([emb, np.ones((*emb.shape[:2], 1))], axis=-1).reshape(-1, emb.shape[-1] + 1)
        for name, target in y.items():
            target = np.asarray(target).reshape(-1)
            if target.shape[0] != design.shape[0]:
                raise ValueError(f"target {name} has incompatible shape")
            gram = design.T @ design + ridge * np.eye(design.shape[1])
            coef = np.linalg.solve(gram, design.T @ target)
            self.heads[name], self.bias[name] = coef[:-1], float(coef[-1])
        self.fitted = True
        return self

    def predict(self, x: np.ndarray) -> HybridOutput:
        if not self.fitted:
            raise RuntimeError("model must be fit on a training fold")
        emb = self.encoder.encode(self._features(x))
        flat = emb.reshape(-1, emb.shape[-1])
        def head(name: str) -> np.ndarray:
            return (flat @ self.heads[name] + self.bias[name]).reshape(emb.shape[:2])
        return HybridOutput(direction=np.tanh(head("direction")), expected_move=np.maximum(0, head("expected_move")), volatility=np.maximum(1e-6, head("volatility")), liquidity=1 / (1 + np.exp(-head("liquidity"))), embedding=emb)
