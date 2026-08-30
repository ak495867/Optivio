from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter_ns

from options_agent.contracts import OrderIntent, Quote, Side


@dataclass(frozen=True, slots=True)
class RouteDecision:
    symbol: str
    limit_price: float
    expected_cost: float
    score: float
    reason: str
    decision_ns: int


class SmartRouter:
    """Bounded in-memory route selection; no network calls or LLMs on the hot path."""

    def choose(self, quotes: list[Quote], intent: OrderIntent) -> RouteDecision | None:
        t0 = perf_counter_ns()
        best: RouteDecision | None = None
        for q in quotes:
            if (
                q.contract.symbol != intent.contract.symbol
                or min(q.bid_size, q.ask_size) < intent.quantity
            ):
                continue
            mid = (q.bid + q.ask) / 2
            spread = max(0.0, q.ask - q.bid)
            px = q.ask if intent.side == Side.BUY else q.bid
            cost = spread / max(mid, 1e-12) + 1.0 / max(min(q.bid_size, q.ask_size), 1)
            score = -cost
            candidate = RouteDecision(
                q.contract.symbol,
                px,
                cost,
                score,
                "best available size/spread quote",
                perf_counter_ns() - t0,
            )
            if best is None or candidate.score > best.score:
                best = candidate
        return best
