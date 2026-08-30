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
    e = lambda n: MarketEvent("quote", "A", t, t, n, {})
    assert bus.publish_nowait(e(1))
    assert not bus.publish_nowait(e(1))


def test_contract_master_filters_active_contracts():
    master = ContractMaster()
    master.upsert(OptionContractRecord("A1", "A", date(2026, 2, 1), 100, "call", 100, 100, "active", True, "american"))
    assert len(master.active_for("A", date(2026, 1, 1))) == 1


def test_offline_rl_report_requires_support():
    t = LoggedTransition(0, 1, 1.0, 1, False, 1.0, 1)
    report = OfflineRLEvaluator(min_support_rate=.5).evaluate([t], lambda _: 1)
    assert report.safe and report.weighted_importance_sampling == 1.0


def test_hardware_benchmark_reports_latency():
    report = benchmark("noop", lambda: None, iterations=5, warmup=1)
    assert report.p99_us >= report.p50_us and report.throughput_per_second > 0


def test_reconciliation_blocks_on_fill_drift():
    class Broker:
        def submit_leg(self, leg): return leg.client_id
        def cancel_leg(self, client_id): pass
        def snapshot(self): return BrokerSnapshot((BrokerLegState("x", 0, "submitted"),), {}, 0, 0)
    engine = MultiLegExecutionEngine(Broker(), GreeksRiskGate())
    package = MultiLegPackage("p", [Leg("x", "A", 1, 1)])
    assert engine.register(package, Greeks())[0]
    assert not engine.submit("p")[0]
    assert engine.reconcile()
    assert engine.submit("p")[0]
    engine.apply_fill("p", "x", 1)
    assert not engine.reconcile() and engine.reconciliation_blocked
