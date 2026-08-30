from datetime import UTC, datetime

import pandas as pd
import pytest

from options_agent.contracts import (
    OptionContract,
    OptionRight,
    OrderIntent,
    Quote,
    Side,
)
from options_agent.data.point_in_time import purged_walk_forward, validate_point_in_time
from options_agent.orchestration.groq_manager import AltDataAssessment


def ts(day):
    return datetime(2025, 1, day, tzinfo=UTC)


def contract():
    return OptionContract(symbol="AAPL250221C00200000", underlying="AAPL", expiration=ts(21), strike=200, right=OptionRight.CALL)


def test_future_availability_rejected():
    df = pd.DataFrame({"asof": [ts(2)], "available_at": [ts(3)]})
    with pytest.raises(ValueError, match="future availability"):
        validate_point_in_time(df)


def test_walk_forward_has_purge_and_embargo():
    folds = list(purged_walk_forward(100, 40, 10, purge=3, embargo=2))
    assert folds[0].train_end + 3 == folds[0].test_start
    assert folds[0].embargo_end == folds[0].test_end + 2


def test_quote_rejects_crossed_market():
    with pytest.raises(ValueError, match="ask"):
        Quote(contract=contract(), asof=ts(2), available_at=ts(2), bid=2.0, ask=1.0)


def test_order_intent_is_paper_only():
    intent = OrderIntent(client_order_id="x", contract=contract(), side=Side.BUY, quantity=1, limit_price=2.0, rationale="test", model_version="v1", signal_asof=ts(2), created_at=ts(2))
    assert intent.mode.value == "paper"


def test_alt_data_schema_bounds():
    with pytest.raises(ValueError):
        AltDataAssessment(topic="x", sentiment=2, relevance=.5, novelty=.5, event_time=ts(1).isoformat(), source_ids=["s"], uncertainty=.2, abstain=True, rationale="x")
