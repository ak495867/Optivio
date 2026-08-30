"""Coverage for previously-untested execution coordinator surfaces:

- SmartRouter: bounded in-memory quote/route selection (no network).
- GroqManager: structured alt-data interpretation + the temperature knob.
- AlpacaPaperAdapter: account snapshot, bars request guard, paper-only submission.
"""
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from options_agent.contracts import OrderIntent, OptionContract, OptionRight, Quote, Side
from options_agent.execution.alpaca_adapter import AlpacaPaperAdapter
from options_agent.execution.smart_router import SmartRouter
from options_agent.orchestration.groq_manager import GroqManager
from tests.test_safety import ts


def quote(symbol: str, bid: float, ask: float, size: int = 10) -> Quote:
    return Quote(
        contract=OptionContract(
            symbol=symbol,
            underlying="AAPL",
            expiration=ts(21),
            strike=200,
            right=OptionRight.CALL,
        ),
        asof=ts(2),
        available_at=ts(2),
        bid=bid,
        ask=ask,
        bid_size=size,
        ask_size=size,
    )


def order(
    symbol: str = "AAPL250221C00200000",
    quantity: int = 1,
    side: Side = Side.BUY,
) -> OrderIntent:
    return OrderIntent(
        client_order_id="x",
        contract=OptionContract(
            symbol=symbol,
            underlying="AAPL",
            expiration=ts(21),
            strike=200,
            right=OptionRight.CALL,
        ),
        side=side,
        quantity=quantity,
        limit_price=2.0,
        rationale="test",
        model_version="v1",
        signal_asof=ts(2),
        created_at=ts(2),
    )


# --------------------------------------------------------------------------- #
# SmartRouter
# --------------------------------------------------------------------------- #
def test_smart_router_picks_lowest_cost_quote():
    router = SmartRouter()
    quotes = [
        quote("AAPL250221C00200000", bid=1.00, ask=1.10, size=5),
        quote("AAPL250221C00200000", bid=1.90, ask=2.10, size=5),  # wider spread -> higher cost
    ]
    dec = router.choose(quotes, order())
    assert dec is not None and dec.symbol == "AAPL250221C00200000"
    assert dec.limit_price == 1.10  # buy side uses ask
    assert dec.score < 0  # cost is positive -> negative score
    assert dec.reason == "best available size/spread quote"


def test_smart_router_skips_mismatched_symbol_and_insufficient_size():
    router = SmartRouter()
    quotes = [
        quote("WRONG_SYMBOL", bid=1.0, ask=1.1, size=100),
        # right symbol but only 1 lot against a 5-lot order
        quote("AAPL250221C00200000", bid=1.0, ask=1.1, size=1),
        quote("AAPL250221C00200000", bid=1.0, ask=1.2, size=100),
    ]
    dec = router.choose(quotes, order(quantity=5))
    assert dec is not None
    # Walks past both invalid quotes; uses the matching + sufficiently-sized one.
    assert dec.symbol == "AAPL250221C00200000" and dec.limit_price == 1.2
    assert dec.score < 0


def test_smart_router_uses_bid_for_sell_side():
    router = SmartRouter()
    quote_obj = quote("AAPL250221C00200000", bid=0.95, ask=1.05, size=10)
    dec = router.choose([quote_obj], order(side=Side.SELL))
    assert dec is not None and dec.limit_price == 0.95


def test_smart_router_returns_none_when_no_quotes():
    assert SmartRouter().choose([], order()) is None


# --------------------------------------------------------------------------- #
# GroqManager
# --------------------------------------------------------------------------- #
class _FakeGroq:
    def __init__(self, text: str, temperature: float):
        self.received_temperature = None
        self.received_response_format = None
        self._text = text
        self._temperature = temperature
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.received_temperature = kwargs.get("temperature")
        self.received_response_format = kwargs.get("response_format")
        msg = SimpleNamespace(message=SimpleNamespace(content=self._text))
        return SimpleNamespace(choices=[msg])


def test_groq_manager_assesses_alt_data_and_passes_temperature(monkeypatch):
    mgr = GroqManager(model="some-model")
    mgr.client = _FakeGroq(
        '{"topic":"earnings","sentiment":0.4,"relevance":0.7,"novelty":0.3,'
        '"event_time":"2026-08-30T00:00:00+00:00","source_ids":["src-a"],'
        '"uncertainty":0.2,"abstain":false,"rationale":"earnings beat"}',
        0.0,
    )
    # Ensure connect() is never invoked (client is pre-set).
    monkeypatch.setattr(mgr, "connect", lambda: pytest.fail("should not reconnect"))
    assessment = mgr.assess_alt_data("some text", ["src-a"], "2026-08-30T00:00:00+00:00")
    assert assessment.topic == "earnings" and assessment.sentiment == pytest.approx(0.4)
    assert assessment.source_ids == ["src-a"] and assessment.abstain is False
    assert mgr.client.received_temperature == 0.0
    assert mgr.client.received_response_format == {"type": "json_object"}


def test_groq_manager_connect_requires_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    mgr = GroqManager()
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        mgr.connect()


def test_groq_manager_rejects_altered_provenance(monkeypatch):
    mgr = GroqManager()
    mgr.client = _FakeGroq(
        '{"topic":"x","sentiment":0.0,"relevance":0.5,"novelty":0.5,'
        '"event_time":"2026-08-30T00:00:00+00:00","source_ids":["EVIL"],'
        '"uncertainty":0.2,"abstain":false,"rationale":"x"}',
        0.0,
    )
    monkeypatch.setattr(mgr, "connect", lambda: pytest.fail("should not reconnect"))
    with pytest.raises(ValueError, match="provenance"):
        mgr.assess_alt_data("text", ["src-a"], "2026-08-30T00:00:00+00:00")


def test_groq_temperature_reads_env(monkeypatch):
    monkeypatch.setenv("GROQ_TEMPERATURE", "0.7")
    assert GroqManager().temperature == pytest.approx(0.7)


def test_groq_model_defaults_from_env(monkeypatch):
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.delenv("GROQ_TEMPERATURE", raising=False)
    # No env: documented default.
    assert GroqManager().model == "llama-3.3-70b-versatile"
    monkeypatch.setenv("GROQ_MODEL", "my-model")
    assert GroqManager().model == "my-model"


# --------------------------------------------------------------------------- #
# AlpacaPaperAdapter
# --------------------------------------------------------------------------- #
class _FakeTrading:
    def __init__(self, positions=(), activities=(), equity="1000", buying_power="500"):
        self.positions = positions
        self.activities = activities
        self.equity, self.buying_power = equity, buying_power
        self.submitted = []

    def get_account(self):
        return SimpleNamespace(equity=self.equity, buying_power=self.buying_power)

    def get_all_positions(self):
        return self.positions

    def get_account_activities(self, **kwargs):
        return self.activities

    def submit_order(self, request):
        self.submitted.append(request)
        return request


def test_alpaca_account_snapshot_requires_credentials():
    with pytest.raises(RuntimeError, match="ALPACA_API_KEY"):
        AlpacaPaperAdapter(api_key=None, secret_key=None)


def test_alpaca_account_snapshot_returns_risk(monkeypatch):
    from alpaca.trading.enums import AssetClass

    adapter = AlpacaPaperAdapter(api_key="k", secret_key="s")
    trading = _FakeTrading()
    adapter._trading = trading
    matching_pos = SimpleNamespace(
        asset_class=AssetClass.US_OPTION, qty="2", multiplier=100,
        market_value="600.0",
    )
    other_pos = SimpleNamespace(
        asset_class=AssetClass.US_EQUITY, qty="1", multiplier=1, market_value="50.0"
    )
    trading.positions = [matching_pos, other_pos]
    trading.activities = [
        SimpleNamespace(
            transaction_time=datetime.now(UTC),
            net_amount="-25.0",
        )
    ]
    snap = adapter.account_snapshot()
    assert snap.equity == 1000.0 and snap.buying_power == 500.0
    assert snap.open_option_notional == 600.0  # only option position
    # -25.0 realized PnL is a 25.0 loss magnitude; profits don't count.
    assert snap.daily_loss == 25.0
    assert snap.kill_switch is False


def test_alpaca_option_notional_includes_rough_floor(monkeypatch):
    from alpaca.trading.enums import AssetClass

    adapter = AlpacaPaperAdapter(api_key="k", secret_key="s")
    pos = SimpleNamespace(
        asset_class=AssetClass.US_OPTION, qty="2", multiplier=100, market_value="0.0"
    )
    trading = _FakeTrading(positions=[pos])
    adapter._trading = trading
    snap = adapter.account_snapshot()
    # market_value 0 -> falls back to qty * mult * 10.0 rough floor.
    assert snap.open_option_notional == 2 * 100 * 10.0


def test_alpaca_bars_rejects_invalid_interval():
    adapter = AlpacaPaperAdapter(api_key="k", secret_key="s")
    with pytest.raises(ValueError, match="end"):
        adapter.get_option_bars(["AAPL"], ts(3), ts(2))


def test_alpaca_submit_paper_passes_kwargs_and_tif(monkeypatch):
    adapter = AlpacaPaperAdapter(api_key="k", secret_key="s")
    trading = _FakeTrading()
    adapter._trading = trading
    intent = order(quantity=3)
    req = adapter.submit_paper(intent)
    assert req is not None
    # MarketOrderRequest for limit-free intents; symbol roundtrips.
    assert req.symbol == "AAPL250221C00200000" and req.qty == 3
    assert req.side == "buy" and req.time_in_force == "day"


def test_alpaca_submit_paper_rejects_live_run_mode():
    adapter = AlpacaPaperAdapter(api_key="k", secret_key="s")
    from options_agent.contracts import RunMode

    live_intent = order()
    live_intent.mode = RunMode.BACKTEST  # must be force-rejected outside PAPER
    with pytest.raises(ValueError, match="paper"):
        adapter.submit_paper(live_intent)