from __future__ import annotations

from collections import Counter, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime

from options_agent.contracts import OrderIntent, Quote, RiskSnapshot
from options_agent.execution.risk_gate import RiskGate


@dataclass
class RuntimeMetrics:
    counters: Counter = field(default_factory=Counter)
    latencies_ns: deque[int] = field(default_factory=lambda: deque(maxlen=10000))

    def increment(self, name: str, amount: int = 1) -> None:
        self.counters[name] += amount


class LivePaperLoop:
    """Broker-agnostic bounded loop. Network adapters feed validated quote batches into it."""
    def __init__(self, risk_gate: RiskGate, clock: Callable[[], datetime], max_queue: int = 10000, max_quote_age_seconds: float = 15.0):
        self.risk_gate = risk_gate
        self.clock = clock
        self.max_queue = max_queue
        self.max_quote_age_seconds = max_quote_age_seconds
        self.queue: deque[list[Quote]] = deque(maxlen=max_queue)
        self.metrics = RuntimeMetrics()
        self.halted = False

    def halt(self, reason: str) -> None:
        self.halted = True
        self.metrics.increment(f"halt:{reason}")

    def push_quotes(self, quotes: list[Quote]) -> bool:
        if self.halted:
            self.metrics.increment("reject:halted")
            return False
        now = self.clock()
        if any((now - q.available_at).total_seconds() > self.max_quote_age_seconds for q in quotes):
            self.metrics.increment("reject:stale")
            return False
        if len(self.queue) == self.max_queue:
            self.metrics.increment("reject:backpressure")
            return False
        self.queue.append(quotes)
        self.metrics.increment("quotes_batches")
        return True

    def process_once(self, intent_factory: Callable[[list[Quote], RiskSnapshot], Iterable[OrderIntent]], snapshot: RiskSnapshot, submit: Callable[[OrderIntent], object]) -> int:
        if self.halted or not self.queue:
            return 0
        quotes = self.queue.popleft()
        submitted = 0
        for intent in intent_factory(quotes, snapshot):
            ok, reason = self.risk_gate.approve(intent, snapshot)
            if not ok:
                self.metrics.increment(f"reject:risk:{reason}")
                continue
            submit(intent)
            self.metrics.increment("paper_orders_submitted")
            submitted += 1
        return submitted
