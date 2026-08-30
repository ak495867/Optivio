from options_agent.data.durable_store import DurableEventStore
from options_agent.execution.multileg import Greeks
from options_agent.models.artifacts import ModelManifest
from options_agent.risk.scenario import Scenario, evaluate_scenarios


def test_durable_store_replay_and_verify(tmp_path):
    store = DurableEventStore(tmp_path / "events.db")
    store.append(
        "quote",
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:00:00+00:00",
        {"symbol": "A", "bid": 1},
    )
    store.append(
        "fill",
        "2026-01-01T00:00:01+00:00",
        "2026-01-01T00:00:02+00:00",
        {"order": "o1"},
    )
    assert store.verify() and len(list(store.replay())) == 2


def test_model_manifest_signature():
    manifest = ModelManifest("m", "1", "git", "data", "config", "artifact")
    signed = manifest.sign(b"secret")
    assert signed.verify(b"secret") and not signed.verify(b"wrong")


def test_scenario_loss():
    results = evaluate_scenarios(
        Greeks(delta=10), [Scenario("down", delta_shock=-2)], max_loss=15
    )
    assert results["down"].breached
