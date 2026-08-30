from datetime import UTC, datetime, timedelta
from pathlib import Path

from options_agent.execution.state_store import ExecutionEvent, ExecutionStateStore


def test_state_store_hash_and_delayed_feedback(tmp_path: Path):
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    store = ExecutionStateStore(tmp_path / "events.jsonl")
    store.append(ExecutionEvent("e1", "fill", "o1", "AAPL", t0, t0 + timedelta(minutes=1), 1, 2.0, realized_pnl=3.0))
    store.append(ExecutionEvent("e2", "fill", "o2", "AAPL", t0, t0 + timedelta(minutes=3), 1, 2.0, realized_pnl=-1.0))
    assert store.verify_chain()
    assert len(store.feedback(t0 + timedelta(minutes=2))) == 1
    features = store.feedback_features(t0 + timedelta(minutes=2))
    assert features["realized_pnl_sum"] == 3.0 and features["win_rate"] == 1.0
