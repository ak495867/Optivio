import pandas as pd
import pytest

from options_agent.contracts import OrderIntent, Quote, RiskSnapshot, Side
from options_agent.data.point_in_time import assert_no_future_rows
from options_agent.execution.risk_gate import RiskGate, RiskLimits
from options_agent.validation.backtest import OptionsBacktester
from tests.test_safety import contract, ts


def test_cutoff_rejects_future_data():
    df = pd.DataFrame({"asof": [ts(2)], "available_at": [ts(2)]})
    with pytest.raises(ValueError):
        assert_no_future_rows(df, ts(1))


def test_risk_gate_rejects_large_order():
    intent = OrderIntent(client_order_id="x", contract=contract(), side=Side.BUY, quantity=2, limit_price=20.0, rationale="test", model_version="v1", signal_asof=ts(2), created_at=ts(2))
    ok, reason = RiskGate(RiskLimits(max_order_notional=1000)).approve(intent, RiskSnapshot(equity=10000, buying_power=10000, open_option_notional=0, daily_loss=0))
    assert not ok and "limit" in reason


def test_backtester_uses_ask_for_buy_and_costs():
    q = Quote(contract=contract(), asof=ts(2), available_at=ts(2), bid=1.00, ask=1.10, bid_size=10, ask_size=10)
    intent = OrderIntent(client_order_id="x", contract=contract(), side=Side.BUY, quantity=1, limit_price=1.10, rationale="test", model_version="v1", signal_asof=ts(2), created_at=ts(2))
    result = OptionsBacktester(initial_cash=1000, commission_per_contract=.65, slippage_bps=0).run({ts(2): [q]}, {ts(2): [intent]})
    assert len(result.fills) == 1
    assert result.fills[0].price == 1.10
    assert result.equity_curve.iloc[-1] < 1000
