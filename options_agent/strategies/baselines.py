from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from options_agent.contracts import Signal


@dataclass(frozen=True)
class BaselineContext:
    symbol: str
    asof: datetime
    close: float
    sma: float
    vix: float
    vix_sma: float
    pcr: float
    trin: float
    atr: float
    high_n: float
    low_n: float


def pcr_signal(ctx: BaselineContext) -> Signal:
    score = -1.0 if ctx.pcr > 1.2 else 1.0 if ctx.pcr < 0.8 else 0.0
    return Signal(
        symbol=ctx.symbol,
        asof=ctx.asof,
        score=score,
        confidence=min(0.95, 0.5 + abs(ctx.pcr - 1)),
        expected_move=0.0,
        rationale="PCR baseline",
        features={"pcr": ctx.pcr},
    )


def vix_signal(ctx: BaselineContext) -> Signal:
    score = 1.0 if ctx.vix < ctx.vix_sma else -1.0
    return Signal(
        symbol=ctx.symbol,
        asof=ctx.asof,
        score=score,
        confidence=min(0.95, 0.5 + abs(ctx.vix - ctx.vix_sma) / max(ctx.vix_sma, 1e-9)),
        expected_move=0.0,
        rationale="VIX baseline",
        features={"vix": ctx.vix, "vix_sma": ctx.vix_sma},
    )


def trin_signal(ctx: BaselineContext) -> Signal:
    score = -1.0 if ctx.trin > 1.2 else 1.0 if ctx.trin < 0.8 else 0.0
    return Signal(
        symbol=ctx.symbol,
        asof=ctx.asof,
        score=score,
        confidence=min(0.95, 0.5 + abs(ctx.trin - 1)),
        expected_move=0.0,
        rationale="TRIN baseline",
        features={"trin": ctx.trin},
    )


def turtle_signal(ctx: BaselineContext) -> Signal:
    score = 1.0 if ctx.close > ctx.high_n else -1.0 if ctx.close < ctx.low_n else 0.0
    confidence = min(0.95, 0.5 + abs(ctx.close - ctx.sma) / max(ctx.atr, 1e-9) / 10)
    return Signal(
        symbol=ctx.symbol,
        asof=ctx.asof,
        score=score,
        confidence=confidence,
        expected_move=0.0,
        rationale="Turtle breakout baseline",
        features={"high_n": ctx.high_n, "low_n": ctx.low_n},
    )


def baseline_registry() -> dict[str, Callable[[BaselineContext], Signal]]:
    return {
        "pcr": pcr_signal,
        "vix": vix_signal,
        "trin": trin_signal,
        "turtle": turtle_signal,
    }


def monte_carlo_terminal_prices(
    spot: float,
    drift: float,
    volatility: float,
    horizon_years: float,
    paths: int = 10000,
    seed: int = 7,
) -> np.ndarray:
    if spot <= 0 or volatility < 0 or horizon_years <= 0 or paths <= 0:
        raise ValueError("invalid Monte Carlo parameters")
    rng = np.random.default_rng(seed)
    shocks = rng.normal(size=paths)
    return spot * np.exp(
        (drift - 0.5 * volatility**2) * horizon_years
        + volatility * np.sqrt(horizon_years) * shocks
    )
