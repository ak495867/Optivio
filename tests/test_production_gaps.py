import threading

import pytest

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


def test_durable_store_concurrent_appends_serialize(tmp_path):
    """Concurrent appends must not interleave: BEGIN IMMEDIATE takes the write
    lock during the read-modify-write, so every append chains onto the tail the
    previous writer committed. The hash chain must stay contiguous and intact."""
    store = DurableEventStore(tmp_path / "events.db")

    def hammer(writer: int):
        con = DurableEventStore(tmp_path / "events.db")
        for i in range(25):
            con.append(
                "quote",
                f"2026-01-01T00:00:{writer:02d}:{i:02d}+00:00",
                "available",
                {"writer": writer, "i": i},
            )

    threads = [threading.Thread(target=hammer, args=(w,)) for w in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert store.verify()
    events = list(store.replay())
    assert len(events) == 4 * 25
    # Contiguous sequence; each record references the prior one's hash.
    assert [e.sequence for e in events] == list(range(1, len(events) + 1))
    # No two records may share a predecessor: had two writers read the same
    # tail, both would chain to one previous_hash, forking the chain. verify()
    # catches it too, but assert it directly.
    for index, event in enumerate(events[1:], start=1):
        assert event.previous_hash == events[index - 1].record_hash


def test_model_manifest_signature():
    manifest = ModelManifest("m", "1", "git", "data", "config", "artifact")
    signed = manifest.sign(b"secret")
    assert signed.verify(b"secret") and not signed.verify(b"wrong")


def test_scenario_loss():
    results = evaluate_scenarios(
        Greeks(delta=10), [Scenario("down", delta_shock=-2)], max_loss=15
    )
    assert results["down"].breached


def test_scenario_theta_is_per_day_not_annualized():
    """An annualized theta must be scaled to per-day before a (days-based)
    theta_shock, otherwise time decay is overstated 252x."""
    from options_agent.risk.scenario import (
        evaluate_scenarios,
    )

    results = evaluate_scenarios(
        Greeks(theta=-252 * 50),
        [Scenario("decay", theta_shock=1)],
        max_loss=1e9,
    )
    # greeks.theta = -12600 per year -> -50 per day; one day of decay loses 50.
    assert results["decay"].pnl_change == pytest.approx(-50.0)
    assert results["decay"].pnl_change > -252 * 50  # no 252x overstatement
