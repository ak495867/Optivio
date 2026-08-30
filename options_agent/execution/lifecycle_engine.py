from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from options_agent.execution.multileg import (
    Greeks,
    GreeksRiskGate,
    Leg,
    LifecycleEvent,
    strategy_state,
)
from options_agent.execution.reconciliation import BrokerReconciler


@dataclass(frozen=True, slots=True)
class BrokerLegState:
    client_id: str
    filled: int
    state: str


@dataclass(frozen=True, slots=True)
class BrokerSnapshot:
    orders: tuple[BrokerLegState, ...]
    positions: dict[str, int]
    cash: float
    buying_power: float


class PaperBroker(Protocol):
    def submit_leg(self, leg: Leg) -> str: ...
    def cancel_leg(self, client_id: str) -> None: ...
    def snapshot(self) -> BrokerSnapshot: ...


@dataclass
class MultiLegPackage:
    package_id: str
    legs: list[Leg]
    current_greeks: Greeks = field(default_factory=Greeks)
    blocked: bool = False

    @property
    def state(self) -> str:
        return strategy_state(self.legs)


class MultiLegExecutionEngine:
    """Stateful package manager; any uncertain broker state blocks new exposure."""

    def __init__(
        self,
        broker: PaperBroker,
        greeks_gate: GreeksRiskGate | None = None,
        reconciler: BrokerReconciler | None = None,
    ):
        self.broker, self.greeks_gate = broker, greeks_gate or GreeksRiskGate()
        self.reconciler = reconciler or BrokerReconciler()
        self.packages: dict[str, MultiLegPackage] = {}
        self.submitted_ids: set[str] = set()
        self.reconciliation_blocked = True

    def register(
        self, package: MultiLegPackage, proposed_greeks: Greeks
    ) -> tuple[bool, str]:
        if package.package_id in self.packages:
            return False, "duplicate package"
        # Approve against the *portfolio* greeks after this addition, not just this
        # package's own edge: a single package under the limit can still push the
        # aggregate over it once other registered packages are included. The new
        # package's own pre-existing holdings (current_greeks) count as part of the
        # baseline it adds to the portfolio.
        portfolio_current = self._portfolio_greeks() + package.current_greeks
        approved, reason = self.greeks_gate.approve(portfolio_current, proposed_greeks)
        if not approved:
            return False, reason
        # Persist the approved exposure so the portfolio aggregate reflects it.
        package.current_greeks = proposed_greeks
        self.packages[package.package_id] = package
        return True, "registered"

    def _portfolio_greeks(self) -> Greeks:
        """Sum the current greeks across every active registered package."""
        total = Greeks()
        for pkg in self.packages.values():
            total = total + pkg.current_greeks
        return total

    def submit(self, package_id: str) -> tuple[bool, str]:
        if self.reconciliation_blocked:
            return False, "reconciliation blocked"
        package = self.packages[package_id]
        if package.blocked or package.state != "working":
            return False, f"package state {package.state} not submittable"
        for leg in package.legs:
            if leg.client_id in self.submitted_ids:
                continue
            self.broker.submit_leg(leg)
            self.submitted_ids.add(leg.client_id)
            leg.apply(LifecycleEvent.SUBMIT_ACK)
        return True, "submitted"

    def apply_fill(self, package_id: str, client_id: str, quantity: int) -> None:
        package = self.packages[package_id]
        leg = next(item for item in package.legs if item.client_id == client_id)
        leg.apply(LifecycleEvent.FILL, quantity)

    def reconcile(self) -> bool:
        result = self.reconciler.reconcile(self.packages, self.broker.snapshot())
        self.reconciliation_blocked = not result.ok
        return result.ok

    def recover_unknown(self) -> None:
        self.reconciliation_blocked = True
        for package in self.packages.values():
            package.blocked = True
