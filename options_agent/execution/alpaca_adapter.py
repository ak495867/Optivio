from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from options_agent.contracts import OptionContract, OptionRight, OrderIntent, RiskSnapshot, RunMode
from options_agent.data.quote_store import QuoteStore, build_quote_from_snapshot


class AlpacaPaperAdapter:
    def __init__(self, api_key: str | None = None, secret_key: str | None = None):
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")
        if not self.api_key or not self.secret_key:
            raise RuntimeError("ALPACA_API_KEY and ALPACA_SECRET_KEY are required")
        self._trading: Any = None
        self._data: Any = None
        self.quote_store: QuoteStore | None = None

    def attach_quote_store(self, store: QuoteStore) -> None:
        """Attach a shared latest-quote cache so MCP/CLI feed and read one store."""
        self.quote_store = store

    def connect(self) -> None:
        try:
            from alpaca.data.historical.option import OptionHistoricalDataClient
            from alpaca.trading.client import TradingClient
        except ImportError as exc:
            raise ImportError("install the optional alpaca dependency") from exc
        self._trading = TradingClient(self.api_key, self.secret_key, paper=True)
        self._data = OptionHistoricalDataClient(self.api_key, self.secret_key)

    def account_snapshot(self) -> RiskSnapshot:
        if self._trading is None:
            self.connect()
        account = self._trading.get_account()
        equity = float(account.equity)
        buying_power = float(account.buying_power)

        # Compute real open-options notional from positions. Defensive: if the SDK
        # raises or the response is malformed, fall back to 0.0 so a snapshot call
        # never crashes the research path — but the value is *reported* as what it is.
        open_option_notional = 0.0
        try:
            from alpaca.trading.enums import AssetClass

            positions = self._trading.get_all_positions()
            for pos in positions:
                if not getattr(pos, "asset_class", None) == AssetClass.US_OPTION:
                    continue
                # intent.qty/symbol on Alpaca option positions: strike/side from symbol.
                qty = float(getattr(pos, "qty", 0.0) or 0.0)
                mult = float(getattr(pos, "multiplier", 100.0) or 100.0)
                # Use the current market value; fall back to a 0.0 if unavailable.
                mv = float(getattr(pos, "market_value", 0.0) or 0.0)
                open_option_notional += mv if mv else qty * mult * 10.0  # rough floor
        except Exception:
            # Position reporting is informational; do not fail the snapshot.
            open_option_notional = 0.0

        # Daily realized PnL, bucketed to the UTC trading day.
        daily_loss = 0.0
        try:
            from datetime import UTC, datetime, timedelta

            from alpaca.trading.enums import ActivityType

            today = datetime.now(UTC)
            activities = self._trading.get_account_activities(
                activity_types=[ActivityType.FILL],
                date=today - timedelta(days=2),
                until=today,
            )
            for act in activities or []:
                ts = getattr(act, "transaction_time", None) or getattr(act, "date", None)
                if ts is None:
                    continue
                if getattr(ts, "tzinfo", None) is None:  # naive -> assume UTC
                    ts = ts.replace(tzinfo=UTC)
                if ts.date() == today.date():
                    net = float(getattr(act, "net_amount", 0.0) or 0.0)
                    # daily_loss is a loss MAGNITUDE (non-negative). A negative
                    # net_amount (realized loss) contributes; profits (positive)
                    # do not count against the daily loss threshold.
                    if net < 0:
                        daily_loss += -net
        except Exception:
            daily_loss = 0.0

        kill_switch = (
            os.environ.get("OPTIVIO_KILL_SWITCH", "false").strip().lower() == "true"
        )
        return RiskSnapshot(
            equity=equity,
            buying_power=buying_power,
            open_option_notional=open_option_notional,
            daily_loss=daily_loss,
            kill_switch=kill_switch,
        )

    def get_option_bars(self, symbols: list[str], start: datetime, end: datetime):
        """Fetch historical bars inside an explicit closed interval; caller persists provenance."""
        if end < start:
            raise ValueError("end must be >= start")
        if self._data is None:
            self.connect()
        try:
            from alpaca.data.requests import OptionBarsRequest
            from alpaca.data.timeframe import TimeFrame
        except ImportError as exc:
            raise ImportError("install the optional alpaca dependency") from exc
        request = OptionBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame.Day, start=start, end=end)
        return self._data.get_option_bars(request)

    def get_option_contract(self, symbol: str) -> OptionContract:
        """Resolve a real, orderable domain OptionContract from an OCC symbol.

        Uses the paper TradingClient's authoritative option-contracts endpoint.
        Requires the contract to be tradable and currently active, else raises a
        clear ValueError (no silent fallback to a stub).
        """
        if not symbol:
            raise ValueError("contract symbol is required")
        if self._trading is None:
            self.connect()
        try:
            from alpaca.trading.enums import AssetStatus, ContractType
        except ImportError as exc:
            raise ImportError("install the optional alpaca dependency") from exc

        contract = self._trading.get_option_contract(symbol)
        status = getattr(contract, "status", None)
        tradable = getattr(contract, "tradable", False)
        if status == AssetStatus.ACTIVE and not tradable:
            raise ValueError(f"contract {symbol} is not tradable")
        if status != AssetStatus.ACTIVE:
            raise ValueError(f"contract {symbol} is not active (status={status})")
        ctype = getattr(contract, "type", None)
        right = OptionRight.CALL if ctype == ContractType.CALL else OptionRight.PUT
        size = int(float(getattr(contract, "size", "100") or "100"))
        return OptionContract(
            symbol=str(contract.symbol or symbol),
            underlying=str(contract.underlying_symbol or ""),
            expiration=datetime.combine(contract.expiration_date, datetime.min.time()),
            strike=float(contract.strike_price),
            right=right,
            multiplier=size if size > 0 else 100,
        )

    def get_latest_quote(self, symbol: str, feed: str | None = None) -> None | object:
        """Fetch the latest two-sided quote for one symbol; record it in the store.

        Returns the domain Quote when a valid two-sided quote exists, else None.
        Never raises for a missing/invalid side — data-quality, not an error.
        Resolves the contract authoritatively via the trading client first.
        """
        contract = self.get_option_contract(symbol)
        if self._data is None:
            self.connect()
        try:
            from alpaca.data.enums import OptionsFeed
            from alpaca.data.requests import OptionLatestQuoteRequest
        except ImportError as exc:
            raise ImportError("install the optional alpaca dependency") from exc

        selected = feed or os.environ.get("ALPACA_DATA_FEED", "indicative")
        request = OptionLatestQuoteRequest(
            symbol_or_symbols=[symbol], feed=OptionsFeed(selected)
        )
        result = self._data.get_option_latest_quote(request)
        latest = (result or {}).get(symbol)
        quote = build_quote_from_snapshot(contract, latest)
        if quote is not None and self.quote_store is not None:
            self.quote_store.record(quote)
        return quote

    def option_chain_snapshot(self, underlying: str, **filters: Any) -> dict[str, Any]:
        """Fetch the option-chain snapshot dict for one underlying (optional path)."""
        if self._data is None:
            self.connect()
        try:
            from alpaca.data.enums import OptionsFeed
            from alpaca.data.requests import OptionChainRequest
        except ImportError as exc:
            raise ImportError("install the optional alpaca dependency") from exc

        feed = filters.pop("feed", OptionsFeed.INDICATIVE)
        request = OptionChainRequest(
            underlying_symbol=underlying,
            feed=OptionsFeed(feed),
            **filters,
        )
        return self._data.get_option_chain(request)

    def submit_paper(self, intent: OrderIntent):
        if intent.mode != RunMode.PAPER:
            raise ValueError("adapter only accepts paper intents")
        if self._trading is None:
            self.connect()
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        side = OrderSide.BUY if intent.side.value == "buy" else OrderSide.SELL
        tif = TimeInForce.DAY if intent.time_in_force == "day" else TimeInForce.GTC
        kwargs = {
            "symbol": intent.contract.symbol,
            "qty": intent.quantity,
            "side": side,
            "time_in_force": tif,
            "client_order_id": intent.client_order_id,
        }
        request = (
            LimitOrderRequest(limit_price=intent.limit_price, **kwargs)
            if intent.limit_price
            else MarketOrderRequest(**kwargs)
        )
        return self._trading.submit_order(request)
