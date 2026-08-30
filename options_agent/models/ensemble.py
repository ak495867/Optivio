from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class GraphNetwork:
    """Cross-asset message passing over a fixed, supplied adjacency matrix."""

    adjacency: np.ndarray
    ridge: float = 1e-3
    weights: np.ndarray | None = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> GraphNetwork:
        if x.ndim != 3 or y.ndim != 2 or x.shape[:2] != y.shape:
            raise ValueError(
                "x must be [samples, assets, features], y [samples, assets]"
            )
        a = np.asarray(self.adjacency, dtype=float)
        if a.shape != (x.shape[1], x.shape[1]):
            raise ValueError("adjacency shape must match asset count")
        design = self._design(x)
        flat_x = design.reshape(len(x) * x.shape[1], -1)
        flat_y = y.reshape(-1)
        gram = flat_x.T @ flat_x + self.ridge * np.eye(flat_x.shape[1])
        self.weights = np.linalg.solve(gram, flat_x.T @ flat_y)
        return self

    def _design(self, x: np.ndarray) -> np.ndarray:
        a = np.asarray(self.adjacency, dtype=float)
        deg = a.sum(axis=1, keepdims=True).clip(min=1)
        msg = (a / deg) @ x.mean(axis=0)
        node_feat = np.broadcast_to(x.mean(axis=1)[:, None, :], (len(x), *msg.shape))
        msg_feat = np.broadcast_to(msg[None, ...], (len(x), *msg.shape))
        return np.concatenate([node_feat, msg_feat], axis=2)

    def predict(self, x: np.ndarray) -> np.ndarray:
        if self.weights is None:
            raise RuntimeError("graph network is not fit")
        design = self._design(x)
        return (design.reshape(len(x) * x.shape[1], -1) @ self.weights).reshape(
            len(x), x.shape[1]
        )


@dataclass
class DeepGBM:
    """Leakage-safe wrapper around sklearn HistGradientBoosting when available."""

    max_iter: int = 150
    learning_rate: float = 0.05
    max_depth: int = 4
    model: Any = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> DeepGBM:
        try:
            from sklearn.ensemble import HistGradientBoostingRegressor
        except ImportError as exc:
            raise ImportError(
                "install scikit-learn optional dependency to use DeepGBM"
            ) from exc
        self.model = HistGradientBoostingRegressor(
            max_iter=self.max_iter,
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            random_state=7,
        )
        self.model.fit(np.asarray(x), np.asarray(y))
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("DeepGBM is not fit")
        return np.asarray(self.model.predict(np.asarray(x)))


@dataclass
class HybridSignalModel:
    graph: GraphNetwork
    gbm: DeepGBM
    graph_weight: float = 0.35

    def predict(self, graph_x: np.ndarray, tabular_x: np.ndarray) -> np.ndarray:
        g = np.asarray(self.graph.predict(graph_x))
        b = np.asarray(self.gbm.predict(tabular_x))
        if g.ndim == 2 and b.ndim == 1 and g.shape[1] == 1:
            b = b[:, None]
        if b.ndim == 1 and g.ndim == 2:
            b = np.broadcast_to(b[:, None], g.shape)
        return self.graph_weight * g + (1.0 - self.graph_weight) * b
