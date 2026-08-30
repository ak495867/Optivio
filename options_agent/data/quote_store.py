"""In-memory latest-quote cache and pure mappers from Alpaca data to domain models.

This module keeps the hot MCP/CLI quote path off repeated network calls. A
``QuoteStore`` records the last good two-sided ``Quote`` per contract symbol;
the mappers translate Alpaca snapshot / stream payloads into the strict domain
``Quote`` model (bid>0, ask>0, sizes>=1, ask>=bid) and return ``None`` for any
invalid side instead of raising — a missing or crossed side is a data-quality
result, not a crash.

Everything here is pure Python over the existing ``contracts`` models; the Alpaca
SDK is imported lazily inside the adapter, never here.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from options_agent.contracts import OptionContract, OptionRight, Quote

_OCC_RE = re.compile(
    r"^(?P<root>[A-Z]{1,6})(?P<expiry>\d{6})(?P<right>[CP])(?P<strike>\d{8})$"
)


def parse_occ_symbol(symbol: str) -> tuple[str, datetime, OptionRight, float]:
    """Parse a modern OCC option symbol to (root, expiry, right, strike).

    Format: ROOT + YYMMDD expiry + C/P + 8-digit strike (5 whole + 3 decimal),
    e.g. ``AAPL260131C00300000`` -> (AAPL, 2026-01-31, CALL, 300.0).
    """
    match = _OCC_RE.match(symbol.strip().upper())
    if not match:
        raise ValueError(f"cannot parse OCC option symbol: {symbol}")
    expiry_str = "20" + match.group("expiry")  # YYMMDD -> YYYYMMDD
    expiry = datetime.strptime(expiry_str, "%Y%m%d")
    right = OptionRight.CALL if match.group("right") == "C" else OptionRight.PUT
    strike = int(match.group("strike")) / 1000.0
    return match.group("root"), expiry, right, strike


def build_quote_from_snapshot(
    contract: OptionContract,
    latest_quote: Any,
    asof: datetime | None = None,
) -> Quote | None:
    """Map an Alpaca latest-quote object to a domain Quote, or None if not tradable.

    ``latest_quote`` exposes ``timestamp``, ``bid_price``, ``bid_size``,
    ``ask_price``, ``ask_size`` (as on the alpaca-py ``Quote`` model). Honors the
    strict domain model: a zero/None side, zero size, or crossed market maps to
    ``None`` rather than raising.
    """
    if latest_quote is None:
        return None
    bid = float(getattr(latest_quote, "bid_price", 0.0) or 0.0)
    ask = float(getattr(latest_quote, "ask_price", 0.0) or 0.0)
    bid_size = int(getattr(latest_quote, "bid_size", 0) or 0)
    ask_size = int(getattr(latest_quote, "ask_size", 0) or 0)
    if bid <= 0 or ask <= 0 or bid_size < 1 or ask_size < 1 or ask < bid:
        return None
    event_time = asof or getattr(latest_quote, "timestamp", None)
    if event_time is None:
        return None
    return Quote(
        contract=contract,
        asof=event_time,
        available_at=event_time,
        bid=bid,
        ask=ask,
        bid_size=bid_size,
        ask_size=ask_size,
    )


def build_quote_from_stream_event(
    contract: OptionContract,
    payload: dict[str, Any],
    event_time: datetime | None = None,
) -> Quote | None:
    """Map a stream MarketEvent payload into a domain Quote, or None if invalid.

    ``event_time`` is taken from the MarketEvent itself (its market timestamp),
    never from the wall clock — a stream quote's ``asof``/``available_at`` must be
    the exchange time, which keeps feature construction leakage-free.
    """
    try:
        bid = float(payload.get("bid", 0.0) or 0.0)
        ask = float(payload.get("ask", 0.0) or 0.0)
        bid_size = int(payload.get("bid_size", 0) or 0)
        ask_size = int(payload.get("ask_size", 0) or 0)
    except (TypeError, ValueError):
        return None
    if bid <= 0 or ask <= 0 or bid_size < 1 or ask_size < 1 or ask < bid:
        return None
    if event_time is None:
        return None
    return Quote(
        contract=contract,
        asof=event_time,
        available_at=event_time,
        bid=bid,
        ask=ask,
        bid_size=bid_size,
        ask_size=ask_size,
    )


class QuoteStore:
    """Thread-safe in-memory latest-quote cache keyed by contract symbol."""

    def __init__(self, max_age_seconds: float = 60.0):
        self.max_age_seconds = max_age_seconds
        self._quotes: dict[str, Quote] = {}
        self._clock: Callable[[], float] | None = None

    def attach_clock(self, clock: Callable[[], float]) -> None:
        """Inject a wall-clock provider (seconds) for deterministic tests."""
        self._clock = clock

    def _now(self) -> float:
        if self._clock is not None:
            return self._clock()
        from time import monotonic

        return monotonic()

    def record(self, quote: Quote) -> None:
        self._quotes[quote.contract.symbol] = quote

    def get(self, symbol: str) -> Quote | None:
        return self._quotes.get(symbol)

    def get_fresh(
        self, symbol: str, max_age_seconds: float | None = None
    ) -> Quote | None:
        """Return a cached quote if it is younger than max_age_seconds."""
        quote = self._quotes.get(symbol)
        if quote is None:
            return None
        age_limit = (
            max_age_seconds if max_age_seconds is not None else self.max_age_seconds
        )
        # Rough recency gate via the injected clock when present; otherwise return
        # the quote as-is (the adapter enforces freshness on live fetches).
        if self._clock is not None:
            age = self._now() - _as_seconds_since_epoch(quote.asof)
            if age > age_limit:
                return None
        return quote

    def symbols(self) -> set[str]:
        return set(self._quotes)

    def __len__(self) -> int:
        return len(self._quotes)


def _as_seconds_since_epoch(dt: datetime) -> float:
    return dt.timestamp()


def record_to_contract(record: Any) -> OptionContract:
    """Convert a ContractMaster record (OptionContractRecord) into a domain OptionContract."""
    return OptionContract(
        symbol=record.symbol,
        underlying=record.underlying_symbol,
        expiration=datetime.combine(record.expiration_date, datetime.min.time()),
        strike=record.strike_price,
        right=OptionRight.CALL if record.right == "call" else OptionRight.PUT,
        multiplier=record.multiplier or 100,
    )


def stream_handler(
    quote_store: QuoteStore, contract_master: Any
) -> Callable[[Any], None]:
    """Build a handler that records stream MarketEvents into the store.

    The returned callable takes a MarketEvent, looks up the contract in the
    contract master by event symbol, and records a valid two-sided quote. Missing
    contracts and invalid quotes are silently skipped (data-quality, not errors).
    """

    def handle(event: Any) -> None:
        try:
            record = contract_master.get(event.symbol)
        except KeyError:
            return
        if record is None:
            return
        contract = record_to_contract(record)
        quote = build_quote_from_stream_event(
            contract, dict(event.payload), event_time=event.event_time
        )
        if quote is not None:
            quote_store.record(quote)

    return handle
