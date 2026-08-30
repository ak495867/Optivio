from pathlib import Path

from options_agent.orchestration.runtime import (
    OptivioOrchestrator,
    RuntimeCredentials,
    RuntimeMode,
    RuntimeState,
)


def test_credentials_require_paper_endpoint(tmp_path: Path):
    runtime = OptivioOrchestrator(tmp_path / "audit.tsv")
    ok, detail = runtime.start(
        RuntimeCredentials(
            "key", "secret", paper_endpoint="https://api.alpaca.markets"
        ),
        RuntimeMode.SIGNAL_ONLY,
    )
    assert not ok
    assert "paper endpoint" in detail
    assert runtime.snapshot.state == RuntimeState.HALTED


def test_kill_switch_halts_preflight(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPTIVIO_KILL_SWITCH", "true")
    runtime = OptivioOrchestrator(tmp_path / "audit.tsv")
    gates = runtime.preflight(
        RuntimeCredentials("key", "secret"), RuntimeMode.SIGNAL_ONLY
    )
    kill = next(g for g in gates if g.name == "kill_switch_clear")
    assert not kill.passed and "KILL_SWITCH" in kill.detail
    ok, _ = runtime.start(RuntimeCredentials("key", "secret"), RuntimeMode.SIGNAL_ONLY)
    assert not ok and runtime.snapshot.state == RuntimeState.HALTED


def test_native_dependencies_is_advisory(tmp_path: Path, monkeypatch):
    """A missing Tk runtime must not hard-stop headless runs."""

    import importlib.util

    monkeypatch.delenv("OPTIVIO_KILL_SWITCH", raising=False)
    real_find = importlib.util.find_spec

    def fake_find_spec(name, *args, **kwargs):
        if name == "tkinter":
            return None
        return real_find(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    runtime = OptivioOrchestrator(tmp_path / "audit.tsv")
    gates = runtime.preflight(
        RuntimeCredentials("key", "secret"), RuntimeMode.SIGNAL_ONLY
    )
    native = next(g for g in gates if g.name == "native_dependencies")
    assert not native.passed  # reports the real (missing) Tk state
    ok, _ = runtime.start(RuntimeCredentials("key", "secret"), RuntimeMode.SIGNAL_ONLY)
    assert ok  # native_dependencies is advisory, so start still proceeds


def test_constrained_paper_waits_for_sync(tmp_path: Path):
    runtime = OptivioOrchestrator(tmp_path / "audit.tsv")
    ok, detail = runtime.start(
        RuntimeCredentials("key", "secret"), RuntimeMode.CONSTRAINED_PAPER
    )
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
