from pathlib import Path

from options_agent.orchestration.runtime import (
    OptivioOrchestrator,
    RuntimeCredentials,
    RuntimeMode,
    RuntimeState,
)


def test_credentials_require_paper_endpoint(tmp_path: Path):
    runtime = OptivioOrchestrator(tmp_path / "audit.tsv")
    ok, detail = runtime.start(RuntimeCredentials("key", "secret", paper_endpoint="https://api.alpaca.markets"), RuntimeMode.SIGNAL_ONLY)
    assert not ok
    assert "paper endpoint" in detail
    assert runtime.snapshot.state == RuntimeState.HALTED


def test_constrained_paper_waits_for_sync(tmp_path: Path):
    runtime = OptivioOrchestrator(tmp_path / "audit.tsv")
    ok, detail = runtime.start(RuntimeCredentials("key", "secret"), RuntimeMode.CONSTRAINED_PAPER)
    assert ok and "paper execution remains behind" in detail
    assert runtime.snapshot.state == RuntimeState.SYNCING
    ok, _ = runtime.mark_synchronized(stream_fresh=False, broker_synced=True)
    assert not ok and runtime.snapshot.state == RuntimeState.HALTED


def test_component_invocation_is_audited(tmp_path: Path):
    runtime = OptivioOrchestrator(tmp_path / "audit.tsv")
    runtime.invoke("point_in_time")
    runtime.invoke("contract_master")
    runtime.invoke("event_bus")
    assert runtime.invoke("persistence") == "persistence checked"
    runtime.invoke("hybrid_model")
    assert runtime.snapshot.counters["component_invocations"] == 5
    assert "component.invoke" in (tmp_path / "audit.tsv").read_text()
