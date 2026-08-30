from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ModelSignal:
    name: str
    score: float
    confidence: float
    latency_ns: int
    error: str | None = None


class ParallelSignalEngine:
    """Persistent fan-out/fan-in engine; the executor is created once, not per market event."""

    def __init__(
        self,
        models: dict[str, Callable[[Any], tuple[float, float]]],
        workers: int | None = None,
        executor: Executor | None = None,
    ):
        if not models:
            raise ValueError("at least one model is required")
        self.models = models
        self.executor = executor or ThreadPoolExecutor(
            max_workers=workers or len(models), thread_name_prefix="optivio-signal"
        )
        self._owns_executor = executor is None

    def infer(self, payload: Any) -> list[ModelSignal]:
        futures = {}
        for name, model in self.models.items():
            futures[name] = self.executor.submit(model, payload)
        signals = []
        for name, future in futures.items():
            try:
                score, confidence = future.result()
                signals.append(
                    ModelSignal(name, float(score), float(np.clip(confidence, 0, 1)), 0)
                )
            except Exception as exc:
                signals.append(ModelSignal(name, 0.0, 0.0, 0, type(exc).__name__))
        return signals

    def aggregate(
        self, signals: list[ModelSignal], min_confidence: float = 0.5
    ) -> tuple[float, float]:
        valid = [
            s for s in signals if s.error is None and s.confidence >= min_confidence
        ]
        if not valid:
            return 0.0, 0.0
        weights = np.array([s.confidence for s in valid])
        scores = np.array([s.score for s in valid])
        return float(np.average(scores, weights=weights)), float(np.mean(weights))

    def close(self) -> None:
        if self._owns_executor:
            self.executor.shutdown(wait=True, cancel_futures=True)
