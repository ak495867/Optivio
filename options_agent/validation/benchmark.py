from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter_ns

import numpy as np


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    name: str
    observations: int
    mean_return: float
    sharpe: float
    hit_rate: float
    max_drawdown: float
    p50_latency_us: float
    p95_latency_us: float
    p99_latency_us: float
    zero_shot: bool


def zero_shot_metrics(
    returns: np.ndarray, latencies_ns: np.ndarray, name: str = "frozen-model"
) -> BenchmarkReport:
    r = np.asarray(returns, dtype=float)
    lat = np.asarray(latencies_ns, dtype=float)  # <--- Changed 'l' to 'lat'
    
    if r.size == 0 or lat.size == 0:             # <--- Updated the check below
        raise ValueError("benchmark arrays must be non-empty")
    curve = np.cumprod(1.0 + r)
    dd = curve / np.maximum.accumulate(curve) - 1.0
    sd = r.std(ddof=1) if r.size > 1 else 0.0
    p50, p95, p99 = [float(np.percentile(lat, q) / 1000.0) for q in (50, 95, 99)]
    return BenchmarkReport(
        name,
        int(r.size),
        float(r.mean()),
        float(np.sqrt(252) * r.mean() / sd) if sd else 0.0,
        float((r > 0).mean()),
        float(dd.min()),
        p50,
        p95,
        p99,
        True,
    )


def benchmark_callable(fn, iterations: int = 1000) -> np.ndarray:
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    out = np.empty(iterations, dtype=np.int64)
    for i in range(iterations):
        t0 = perf_counter_ns()
        fn()
        out[i] = perf_counter_ns() - t0
    return out


def report_json(report: BenchmarkReport) -> dict:
    return asdict(report)
