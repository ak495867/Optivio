from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


class LegState(str, Enum):
    PLANNED = "planned"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class LifecycleEvent(str, Enum):
    SUBMIT_ACK = "submit_ack"
    FILL = "fill"
    CANCEL_ACK = "cancel_ack"
    REJECT = "reject"
    EXPIRE = "expire"
    UNCERTAIN = "uncertain"


@dataclass
class Leg:
    client_id: str
    symbol: str
    side: int
    quantity: int
    filled: int = 0
    state: LegState = LegState.PLANNED

    def apply(self, event: LifecycleEvent, fill_quantity: int = 0) -> None:
        if event == LifecycleEvent.SUBMIT_ACK and self.state == LegState.PLANNED:
            self.state = LegState.SUBMITTED
        elif event == LifecycleEvent.FILL and self.state in {LegState.SUBMITTED, LegState.PARTIALLY_FILLED}:
            if fill_quantity <= 0 or self.filled + fill_quantity > self.quantity:
                raise ValueError("invalid fill quantity")
            self.filled += fill_quantity
            self.state = LegState.FILLED if self.filled == self.quantity else LegState.PARTIALLY_FILLED
        elif event == LifecycleEvent.CANCEL_ACK and self.state in {LegState.SUBMITTED, LegState.PARTIALLY_FILLED, LegState.CANCEL_PENDING}:
            self.state = LegState.CANCELLED
        elif event == LifecycleEvent.REJECT:
            self.state = LegState.REJECTED
        elif event == LifecycleEvent.EXPIRE:
            self.state = LegState.EXPIRED
        elif event == LifecycleEvent.UNCERTAIN:
            self.state = LegState.UNKNOWN
        else:
            raise ValueError(f"illegal transition {self.state.value} + {event.value}")


@dataclass(frozen=True)
class Greeks:
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0

    def __add__(self, other: Greeks) -> Greeks:
        return Greeks(self.delta + other.delta, self.gamma + other.gamma, self.theta + other.theta, self.vega + other.vega, self.rho + other.rho)

    def scale(self, multiplier: float) -> Greeks:
        return Greeks(*(multiplier * x for x in (self.delta, self.gamma, self.theta, self.vega, self.rho)))


@dataclass(frozen=True)
class GreeksRiskLimits:
    max_abs_delta: float = 1000.0
    max_abs_gamma: float = 500.0
    max_abs_theta: float = 5000.0
    max_abs_vega: float = 5000.0
    max_abs_rho: float = 5000.0


class GreeksRiskGate:
    def __init__(self, limits: GreeksRiskLimits | None = None):
        self.limits = limits or GreeksRiskLimits()

    def approve(self, current: Greeks, proposed_change: Greeks) -> tuple[bool, str]:
        total = current + proposed_change
        limits = self.limits
        checks = (("delta", total.delta, limits.max_abs_delta), ("gamma", total.gamma, limits.max_abs_gamma), ("theta", total.theta, limits.max_abs_theta), ("vega", total.vega, limits.max_abs_vega), ("rho", total.rho, limits.max_abs_rho))
        for name, value, limit in checks:
            if abs(value) > limit:
                return False, f"{name} limit exceeded"
        return True, "approved"


def strategy_state(legs: Iterable[Leg]) -> str:
    states = {leg.state for leg in legs}
    if LegState.UNKNOWN in states:
        return "blocked_unknown"
    if LegState.REJECTED in states:
        return "rejected"
    if all(state == LegState.FILLED for state in states):
        return "filled"
    if any(state == LegState.PARTIALLY_FILLED for state in states):
        return "partially_filled"
    return "working"
