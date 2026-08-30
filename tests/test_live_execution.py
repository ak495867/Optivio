from datetime import UTC, date, datetime

from options_agent.data.live_market import (
    BoundedEventBus,
    ContractMaster,
    MarketEvent,
    OptionContractRecord,
)
from options_agent.execution.lifecycle_engine import (
    BrokerLegState,
    BrokerSnapshot,
    MultiLegExecutionEngine,
    MultiLegPackage,
)
from options_agent.execution.multileg import Greeks, GreeksRiskGate, Leg
from options_agent.validation.hardware_benchmark import benchmark
from options_agent.validation.offline_rl import LoggedTransition, OfflineRLEvaluator


def test_event_bus_rejects_non_monotonic_sequence():

    bus = BoundedEventBus(2)
    t = datetime(2026, 1, 1, tzinfo=UTC)
    
    # Replace the lambda with a standard function definition
    def e(n):
        return MarketEvent("quote", "A", t, t, n, {})
        
    assert bus.publish_nowait(e(1))
    assert not bus.publish_nowait(e(1))


def test_contract_master_filters_active_contracts():
    master = ContractMaster()
    master.upsert(
        OptionContractRecord(
            "A1",
            "A",
            date(2026, 2, 1),
            100,
            "call",
            100,
            100,
            "active",
            True,
            "american",
        )
    )
    assert len(master.active_for("A", date(2026, 1, 1))) == 1


def test_greeks_gate_aggregates_across_packages():
    """Two individually-allowable packages must be rejected when their *combined*
    delta exceeds the portfolio limit — the gate must aggregate, not check each
    edge in isolation."""
    from options_agent.execution.multileg import (
        Greeks,
        GreeksRiskGate,
        GreeksRiskLimits,
    )

    class StubBroker:
        def submit_leg(self, leg):
            return leg.client_id

        def cancel_leg(self, client_id):
            pass

        def snapshot(self):
            return BrokerSnapshot((), {}, 0, 0)

    gate = GreeksRiskGate(GreeksRiskLimits(max_abs_delta=100))
    engine = MultiLegExecutionEngine(StubBroker(), gate)
    # Each package has delta 60 (< 100). Individually BOTH would pass the old per-package
    # gate. Combined (120 > 100) they must fail.
    p1 = MultiLegPackage("p1", [Leg("a", "A", 1, 1)])
    assert engine.register(p1, Greeks(delta=60))[0]
    p2 = MultiLegPackage("p2", [Leg("b", "B", 1, 1)])
    ok, reason = engine.register(p2, Greeks(delta=60))
    assert not ok and "delta" in reason


def test_offline_rl_report_requires_support():
    # target policy picks action 2; the logged transition took action 1 -> the
    # transition is NOT supported by the logging behavior, so the evaluation
    # must report unsafe with zero support rather than a trivially-safe 1.0.
    log_transition = LoggedTransition(0, 1, 1.0, 1, False, 1.0, 1)
    report = OfflineRLEvaluator(min_support_rate=0.5).evaluate(
        [log_transition], lambda _: 2
    )
    assert not report.safe
    # Acknowledge it with a small assert so the test documents intent.
    assert report.weighted_importance_sampling == 0.0 and report.support_rate == 0


def test_hardware_benchmark_reports_latency():
    report = benchmark("noop", lambda: None, iterations=5, warmup=1)
    assert report.p99_us >= report.p50_us and report.throughput_per_second > 0


def test_reconciliation_blocks_on_fill_drift():
    class Broker:
        def submit_leg(self, leg):
            return leg.client_id

        def cancel_leg(self, client_id):
            pass

        def snapshot(self):
            return BrokerSnapshot((BrokerLegState("x", 0, "submitted"),), {}, 0, 0)

    engine = MultiLegExecutionEngine(Broker(), GreeksRiskGate())
    package = MultiLegPackage("p", [Leg("x", "A", 1, 1)])
    assert engine.register(package, Greeks())[0]
    assert not engine.submit("p")[0]
    assert engine.reconcile()
    assert engine.submit("p")[0]
    engine.apply_fill("p", "x", 1)
    assert not engine.reconcile() and engine.reconciliation_blocked


def test_planned_leg_without_broker_order_does_not_deadlock():
    """A package that is all-PLANNED must reconcile clean even though the broker has no
    order for it — the engine submits legs itself, so 'not yet at broker' is normal."""

    class Broker:
        def __init__(self):
            self.orders = []

        def submit_leg(self, leg):
            self.orders.append(BrokerLegState(leg.client_id, 0, "submitted"))
            return leg.client_id

        def cancel_leg(self, client_id):
            pass

        def snapshot(self):
            return BrokerSnapshot(tuple(self.orders), {}, 0, 0)

    broker = Broker()
    engine = MultiLegExecutionEngine(broker, GreeksRiskGate())
    package = MultiLegPackage("p", [Leg("x", "A", 1, 1)])
    assert engine.register(package, Greeks())[0]
    # Fully-planned: no drift, no unknown orders -> reconciliation clears the block.
    assert engine.reconcile()
    # Now the engine can actually submit, and the broker sees the order.
    assert engine.submit("p")[0]
    assert engine.reconcile()


def test_unknown_broker_order_blocks_reconciliation():
    """A broker order whose client_id matches no local leg is an unknown order; it must
    block new exposure until the operator resolves it."""

    class Broker:
        def submit_leg(self, leg):
            return leg.client_id

        def cancel_leg(self, client_id):
            pass

        def snapshot(self):
            return BrokerSnapshot((BrokerLegState("ghost", 0, "submitted"),), {}, 0, 0)

    engine = MultiLegExecutionEngine(Broker(), GreeksRiskGate())
    package = MultiLegPackage("p", [Leg("x", "A", 1, 1)])
    assert engine.register(package, Greeks())[0]
    assert not engine.reconcile() and engine.reconciliation_blocked


def test_submitted_leg_without_broker_order_is_drift():
    """A leg the engine believes is submitted must have a matching broker order; missing
    it means the broker never accepted our order and blocks exposure."""

    class Broker:
        def submit_leg(self, leg):
            return leg.client_id

        def cancel_leg(self, client_id):
            pass

        def snapshot(self):
            return BrokerSnapshot((), {}, 0, 0)  # broker lost/never saw the order

    engine = MultiLegExecutionEngine(Broker(), GreeksRiskGate())
    package = MultiLegPackage("p", [Leg("x", "A", 1, 1)])
    assert engine.register(package, Greeks())[0]
    assert not engine.submit("p")[0]  # blocked initially
    assert engine.reconcile()  # planned -> clears
    assert engine.submit("p")[0]  # now submitted
    assert not engine.reconcile() and engine.reconciliation_blocked
    assert engine.reconciler.last_result.unknown_orders == ()
