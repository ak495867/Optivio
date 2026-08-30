import pandas as pd
import pytest
from pydantic import ValidationError

from options_agent.contracts import OrderIntent, Quote, RiskSnapshot, Side
from options_agent.data.point_in_time import assert_no_future_rows
from options_agent.execution.risk_gate import RiskGate, RiskLimits
from options_agent.validation.backtest import OptionsBacktester
from tests.test_safety import contract, ts


def test_cutoff_rejects_future_data():
    df = pd.DataFrame({"asof": [ts(2)], "available_at": [ts(2)]})
    with pytest.raises(ValueError):
        assert_no_future_rows(df, ts(1))


def test_quote_requires_positive_both_sides():
    """A quote with a zero bid or ask is invalid (the falsy-0 check in the old
    validator let zip through). Both sides must be strictly positive and ask
    must be >= bid."""
    with pytest.raises(ValidationError):
        Quote(
            contract=contract(),
            asof=ts(2),
            available_at=ts(2),
            bid=0.0,
            ask=1.10,
            bid_size=10,
            ask_size=10,
        )
    with pytest.raises(ValidationError):
        Quote(
            contract=contract(),
            asof=ts(2),
            available_at=ts(2),
            bid=1.00,
            ask=1.10,
            bid_size=0,
            ask_size=10,
        )
    # Any bid=0 (even as first arg) still rejected.
    with pytest.raises(ValidationError):
        Quote(
            contract=contract(),
            asof=ts(2),
            available_at=ts(2),
            bid=1.00,
            ask=1.10,
            bid_size=0,
            ask_size=0,
        )
    # Valid both-sides-1 quote remains accepted.
    Quote(
        contract=contract(),
        asof=ts(2),
        available_at=ts(2),
        bid=1.00,
        ask=1.10,
        bid_size=1,
        ask_size=1,
    )


def test_risk_gate_rejects_large_order():
    intent = OrderIntent(
        client_order_id="x",
        contract=contract(),
        side=Side.BUY,
        quantity=2,
        limit_price=20.0,
        rationale="test",
        model_version="v1",
        signal_asof=ts(2),
        created_at=ts(2),
    )
    ok, reason = RiskGate(RiskLimits(max_order_notional=1000)).approve(
        intent,
        RiskSnapshot(
            equity=10000, buying_power=10000, open_option_notional=0, daily_loss=0
        ),
    )
    assert not ok and "limit" in reason


def test_backtester_uses_ask_for_buy_and_costs():
    q = Quote(
        contract=contract(),
        asof=ts(2),
        available_at=ts(2),
        bid=1.00,
        ask=1.10,
        bid_size=10,
        ask_size=10,
    )
    intent = OrderIntent(
        client_order_id="x",
        contract=contract(),
        side=Side.BUY,
        quantity=1,
        limit_price=1.10,
        rationale="test",
        model_version="v1",
        signal_asof=ts(2),
        created_at=ts(2),
    )
    result = OptionsBacktester(
        initial_cash=1000, commission_per_contract=0.65, slippage_bps=0
    ).run({ts(2): [q]}, {ts(2): [intent]})
    assert len(result.fills) == 1
    assert result.fills[0].price == 1.10
    assert result.equity_curve.iloc[-1] < 1000


def test_backtester_buy_limit_does_not_fill_when_above_ask():
    """A resting BUY limit must NOT fill while ask > limit (correct broker semantics)."""
    q = Quote(
        contract=contract(),
        asof=ts(2),
        available_at=ts(2),
        bid=1.00,
        ask=1.10,
        bid_size=10,
        ask_size=10,
    )
    intent = OrderIntent(
        client_order_id="mid",
        contract=contract(),
        side=Side.BUY,
        quantity=1,
        limit_price=round((1.00 + 1.10) / 2, 2),  # 1.05 < ask 1.10 → rest, no fill
        rationale="test",
        model_version="v1",
        signal_asof=ts(2),
        created_at=ts(2),
    )
    result = OptionsBacktester(
        initial_cash=1000, commission_per_contract=0.65, slippage_bps=0
    ).run({ts(2): [q]}, {ts(2): [intent]})
    assert len(result.fills) == 0


def test_backtester_marketable_buy_fills_at_ask():
    """A marketable BUY limit (ask + tiny buffer) fills at ask, never above limit."""
    q = Quote(
        contract=contract(),
        asof=ts(2),
        available_at=ts(2),
        bid=1.00,
        ask=1.10,
        bid_size=10,
        ask_size=10,
    )
    intent = OrderIntent(
        client_order_id="marketable",
        contract=contract(),
        side=Side.BUY,
        quantity=1,
        limit_price=round(1.10 * 1.001, 2),  # just above ask → crosses
        rationale="test",
        model_version="v1",
        signal_asof=ts(2),
        created_at=ts(2),
    )
    result = OptionsBacktester(
        initial_cash=1000, commission_per_contract=0.65, slippage_bps=0
    ).run({ts(2): [q]}, {ts(2): [intent]})
    assert len(result.fills) == 1
    assert result.fills[0].price == 1.10
    assert result.equity_curve.iloc[-1] < 1000


def test_backtester_marketable_sell_fills_at_bid():
    """A marketable SELL limit (bid - tiny buffer) fills at bid, never below limit."""
    q = Quote(
        contract=contract(),
        asof=ts(2),
        available_at=ts(2),
        bid=1.00,
        ask=1.10,
        bid_size=10,
        ask_size=10,
    )
    intent = OrderIntent(
        client_order_id="marketable-sell",
        contract=contract(),
        side=Side.SELL,
        quantity=1,
        limit_price=round(1.00 * 0.999, 2),  # just below bid → crosses
        rationale="test",
        model_version="v1",
        signal_asof=ts(2),
        created_at=ts(2),
    )
    result = OptionsBacktester(
        initial_cash=1000, commission_per_contract=0.65, slippage_bps=0
    ).run({ts(2): [q]}, {ts(2): [intent]})
    assert len(result.fills) == 1
    assert result.fills[0].price == 1.00
    assert result.equity_curve.iloc[-1] > 1000
