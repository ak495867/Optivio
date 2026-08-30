from __future__ import annotations

from dataclasses import dataclass

from options_agent.contracts import OrderIntent, RiskSnapshot


@dataclass(frozen=True)
class RiskLimits:
    max_order_notional: float = 2500.0
    max_open_notional: float = 10000.0
    max_daily_loss_fraction: float = 0.02


class RiskGate:
    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()

    def approve(self, intent: OrderIntent, snapshot: RiskSnapshot) -> tuple[bool, str]:
        notional = (
            (intent.limit_price or 0.0) * intent.quantity * intent.contract.multiplier
        )
        if snapshot.kill_switch:
            return False, "kill switch is active"
        if notional <= 0 or notional > self.limits.max_order_notional:
            return False, "order notional exceeds limit or is unavailable"
        if snapshot.open_option_notional + notional > self.limits.max_open_notional:
            return False, "open options notional limit exceeded"
        if snapshot.daily_loss > snapshot.equity * self.limits.max_daily_loss_fraction:
            return False, "daily loss limit exceeded"
        return True, "approved"
