from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from options_agent.execution.lifecycle_engine import BrokerSnapshot, MultiLegPackage


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    ok: bool
    reason: str
    unknown_orders: tuple[str, ...] = ()
    position_drift: Mapping[str, int] | None = None


class BrokerReconciler:
    def __init__(self, quantity_tolerance: int = 0):
        self.quantity_tolerance = quantity_tolerance
        self.blocked = False
        self.last_result: ReconciliationResult | None = None

    def reconcile(
        self, packages: Mapping[str, MultiLegPackage], broker: BrokerSnapshot
    ) -> ReconciliationResult:
        actual_orders = {order.client_id: order.filled for order in broker.orders}
        # An order is only "unknown" if it matches no local leg at all. A broker
        # order under a client_id the engine has (even a PLANNED leg — e.g. after
        # local state was rebuilt) is claimed and is not a surprise.
        claimed = {
            leg.client_id for package in packages.values() for leg in package.legs
        }
        unknown = tuple(sorted(set(actual_orders) - claimed))
        # Only legs that should have an order at the broker count as drift. A leg that
        # is PLANNED is not yet submitted (the engine submits legs), and a CANCELLED /
        # REJECTED / EXPIRED leg has no live broker order by definition — so a missing
        # broker order for them is normal, not drift.
        no_order_expected = {"planned", "cancelled", "rejected", "expired"}
        order_drift = any(
            abs(actual_orders.get(leg.client_id, -1) - leg.filled)
            > self.quantity_tolerance
            for package in packages.values()
            for leg in package.legs
            if leg.state.value not in no_order_expected
        )
        expected_positions: dict[str, int] = {}
        for package in packages.values():
            for leg in package.legs:
                expected_positions[leg.symbol] = (
                    expected_positions.get(leg.symbol, 0) + leg.side * leg.filled
                )
        symbols = set(expected_positions) | set(broker.positions)
        drift = {
            symbol: broker.positions.get(symbol, 0) - expected_positions.get(symbol, 0)
            for symbol in symbols
            if abs(broker.positions.get(symbol, 0) - expected_positions.get(symbol, 0))
            > self.quantity_tolerance
        }
        ok = not unknown and not order_drift and not drift
        self.blocked = not ok
        reason = "reconciled" if ok else "material broker/local state divergence"
        self.last_result = ReconciliationResult(ok, reason, unknown, drift)
        for package in packages.values():
            package.blocked = not ok
        return self.last_result

    def clear_after_verified_sync(self) -> None:
        if self.last_result is None or not self.last_result.ok:
            raise RuntimeError("cannot clear reconciliation block before verified sync")
        self.blocked = False
