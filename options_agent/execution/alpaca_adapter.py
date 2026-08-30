from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from options_agent.contracts import OrderIntent, RiskSnapshot, RunMode


class AlpacaPaperAdapter:
    def __init__(self, api_key: str | None = None, secret_key: str | None = None):
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")
        if not self.api_key or not self.secret_key:
            raise RuntimeError("ALPACA_API_KEY and ALPACA_SECRET_KEY are required")
        self._trading: Any = None
        self._data: Any = None

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
        return RiskSnapshot(
            equity=float(account.equity),
            buying_power=float(account.buying_power),
            open_option_notional=0.0,
            daily_loss=0.0,
        )

    def get_option_bars(self, symbols: list[str], start: datetime, end: datetime):
        """Fetch historical bars inside an explicit closed interval; caller persists provenance."""
        if end < start:
            raise ValueError("end must be >= start")
        if self._data is None:
            self.connect()
        try:
            from alpaca.data.requests import OptionBarsRequest
        except ImportError as exc:
            raise ImportError("install the optional alpaca dependency") from exc
        request = OptionBarsRequest(symbol_or_symbols=symbols, start=start, end=end)
        return self._data.get_option_bars(request)

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
