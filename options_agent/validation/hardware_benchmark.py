from __future__ import annotations

import platform
from collections.abc import Callable
from dataclasses import asdict, dataclass
from time import perf_counter_ns
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class LatencyResult:
    name: str
    iterations: int
    p50_us: float
    p95_us: float
    p99_us: float
    mean_us: float
    throughput_per_second: float
    host: str
    python: str


def benchmark(name: str, fn: Callable[[], Any], iterations: int = 1000, warmup: int = 100) -> LatencyResult:
    if iterations <= 0 or warmup < 0:
        raise ValueError("invalid benchmark counts")
    for _ in range(warmup):
        fn()
    samples = np.empty(iterations, dtype=np.int64)
    for i in range(iterations):
        start = perf_counter_ns(); fn(); samples[i] = perf_counter_ns() - start
    mean_ns = float(samples.mean())
    p50, p95, p99 = [float(np.percentile(samples, q) / 1000) for q in (50, 95, 99)]
    return LatencyResult(name, iterations, p50, p95, p99, mean_ns / 1000, 1e9 / mean_ns if mean_ns > 0 else 0.0, platform.machine(), platform.python_version())


def compare(functions: dict[str, Callable[[], Any]], iterations: int = 1000) -> list[dict]:
    return [asdict(benchmark(name, fn, iterations=iterations)) for name, fn in functions.items()]
