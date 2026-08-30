from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

import pandas as pd

from options_agent.contracts import OrderIntent, Quote, Side


@dataclass
class Fill:
    timestamp: datetime
    symbol: str
    side: str
    quantity: int
    price: float
    fee: float
    slippage: float


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    fills: list[Fill]
    total_return: float
    sharpe: float
    max_drawdown: float


class OptionsBacktester:
    def __init__(
        self,
        initial_cash: float = 100_000.0,
        commission_per_contract: float = 0.65,
        slippage_bps: float = 5.0,
    ):
        self.initial_cash = initial_cash
        self.commission = commission_per_contract
        self.slippage_bps = slippage_bps

    def run(
        self,
        quotes_by_time: dict[datetime, list[Quote]],
        intents_by_time: dict[datetime, list[OrderIntent]],
    ) -> BacktestResult:
        cash = self.initial_cash
        curve: list[tuple[datetime, float]] = []
        fills: list[Fill] = []
        for ts in sorted(quotes_by_time):
            quote_map = {q.contract.symbol: q for q in quotes_by_time[ts]}
            for intent in intents_by_time.get(ts, []):
                q = quote_map.get(intent.contract.symbol)
                if q is None:
                    continue
                if intent.limit_price is not None:
                    if intent.side == Side.BUY:
                        if q.ask > intent.limit_price:
                            continue
                        base = min(intent.limit_price, q.ask)
                    else:
                        if q.bid < intent.limit_price:
                            continue
                        base = max(intent.limit_price, q.bid)
                else:
                    base = q.ask if intent.side == Side.BUY else q.bid
                slip = base * self.slippage_bps / 10_000
                px = base + slip if intent.side == Side.BUY else max(0.0, base - slip)
                gross = px * intent.quantity * intent.contract.multiplier
                fee = self.commission * intent.quantity
                cash += -gross - fee if intent.side == Side.BUY else gross - fee
                fills.append(
                    Fill(
                        ts,
                        intent.contract.symbol,
                        intent.side.value,
                        intent.quantity,
                        px,
                        fee,
                        slip,
                    )
                )
            curve.append((ts, cash))
        series = pd.Series({ts: value for ts, value in curve}, dtype=float)
        rets = series.pct_change().dropna()
        sharpe = (
            float((rets.mean() / rets.std()) * (252**0.5))
            if len(rets) > 1 and rets.std() > 0
            else 0.0
        )
        dd = series / series.cummax() - 1.0
        return BacktestResult(
            series,
            fills,
            float(series.iloc[-1] / self.initial_cash - 1 if len(series) else 0),
            sharpe,
            float(dd.min() if len(dd) else 0),
        )


def result_json(result: BacktestResult) -> dict:
    return {
        "total_return": result.total_return,
        "sharpe": result.sharpe,
        "max_drawdown": result.max_drawdown,
        "fills": [asdict(x) for x in result.fills],
    }
