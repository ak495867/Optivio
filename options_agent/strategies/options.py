from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from options_agent.contracts import (
    OptionRight,
    OrderIntent,
    Quote,
    RiskSnapshot,
    Side,
    Signal,
)


@dataclass(frozen=True)
class StrategyConfig:
    min_dte: int = 14
    max_dte: int = 60
    max_spread_pct: float = 0.08
    max_contract_notional: float = 2500.0
    max_daily_loss: float = 0.02
    min_confidence: float = 0.55


def put_call_ratio(put_volume: float, call_volume: float) -> float:
    return float(put_volume / max(call_volume, 1e-9))


def vix_regime_signal(
    vix: float, vix_sma: float, asof: datetime, symbol: str
) -> Signal:
    score = 1.0 if vix < vix_sma else -1.0
    confidence = min(0.95, 0.5 + abs(vix - vix_sma) / max(vix_sma, 1e-9))
    return Signal(
        symbol=symbol,
        asof=asof,
        score=score,
        confidence=confidence,
        expected_move=abs(vix - vix_sma) / 100,
        rationale="VIX relative to its point-in-time moving average",
        features={"vix": vix, "vix_sma": vix_sma},
    )


def select_liquid_contract(
    quotes: list[Quote], signal: Signal, cfg: StrategyConfig
) -> Quote | None:
    now = signal.asof
    eligible: list[Quote] = []
    for q in quotes:
        dte = (q.contract.expiration.date() - now.date()).days
        mid = (q.bid + q.ask) / 2 if q.bid and q.ask else max(q.bid, q.ask)
        spread = (q.ask - q.bid) / max(mid, 1e-9) if mid else math.inf
        if (
            cfg.min_dte <= dte <= cfg.max_dte
            and spread <= cfg.max_spread_pct
            and min(q.bid_size, q.ask_size) > 0
        ):
            eligible.append(q)
    if not eligible:
        return None
    target_right = OptionRight.CALL if signal.score > 0 else OptionRight.PUT
    same_right = [q for q in eligible if q.contract.right == target_right]
    return max(same_right or eligible, key=lambda q: min(q.bid_size, q.ask_size))


def build_order(
    signal: Signal,
    quote: Quote,
    risk: RiskSnapshot,
    cfg: StrategyConfig,
    model_version: str,
) -> OrderIntent | None:
    if signal.confidence < cfg.min_confidence or risk.kill_switch:
        return None
    mid = (quote.bid + quote.ask) / 2
    if mid <= 0 or mid * quote.contract.multiplier > cfg.max_contract_notional:
        return None
    if risk.daily_loss > cfg.max_daily_loss * max(risk.equity, 1.0):
        return None
    side = Side.BUY if signal.score > 0 else Side.SELL
    return OrderIntent(
        client_order_id=f"oa-{quote.contract.symbol}-{int(signal.asof.timestamp())}",
        contract=quote.contract,
        side=side,
        quantity=1,
        limit_price=round(mid, 2),
        rationale=signal.rationale,
        model_version=model_version,
        signal_asof=signal.asof,
        created_at=signal.asof,
    )
