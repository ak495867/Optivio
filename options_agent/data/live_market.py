from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class MarketEvent:
    kind: str
    symbol: str
    event_time: datetime
    available_at: datetime
    sequence: int
    payload: Mapping[str, Any]

    @property
    def key(self) -> tuple[str, str, int]:
        return self.kind, self.symbol, self.sequence


class BoundedEventBus:
    """Bounded fan-out bus with backpressure and sequence/deduplication guards."""
    def __init__(self, maxsize: int = 10000):
        if maxsize <= 0:
            raise ValueError("maxsize must be positive")
        self.queue: asyncio.Queue[MarketEvent] = asyncio.Queue(maxsize=maxsize)
        self._seen: set[tuple[str, str, int]] = set()
        self._last_sequence: dict[tuple[str, str], int] = {}
        self.dropped = 0
        self.rejected = 0

    def publish_nowait(self, event: MarketEvent) -> bool:
        if event.available_at < event.event_time:
            self.rejected += 1
            return False
        stream = (event.kind, event.symbol)
        if event.key in self._seen or event.sequence <= self._last_sequence.get(stream, -1):
            self.rejected += 1
            return False
        if self.queue.full():
            self.dropped += 1
            return False
        self._seen.add(event.key)
        self._last_sequence[stream] = event.sequence
        self.queue.put_nowait(event)
        return True

    async def publish(self, event: MarketEvent, timeout: float = 0.0) -> bool:
        if timeout <= 0:
            return self.publish_nowait(event)
        if event.available_at < event.event_time:
            self.rejected += 1
            return False
        stream = (event.kind, event.symbol)
        if event.key in self._seen or event.sequence <= self._last_sequence.get(stream, -1):
            self.rejected += 1
            return False
        try:
            await asyncio.wait_for(self.queue.put(event), timeout=timeout)
        except TimeoutError:
            self.dropped += 1
            return False
        self._seen.add(event.key)
        self._last_sequence[stream] = event.sequence
        return True

    async def consume(self, handler: Callable[[MarketEvent], Awaitable[None]]) -> None:
        while True:
            event = await self.queue.get()
            try:
                await handler(event)
            finally:
                self.queue.task_done()


@dataclass(frozen=True, slots=True)
class OptionContractRecord:
    symbol: str
    underlying_symbol: str
    expiration_date: date
    strike_price: float
    right: str
    multiplier: int
    size: int
    status: str
    tradable: bool
    style: str
    open_interest: float | None = None
    open_interest_date: date | None = None
    source_id: str = "alpaca"

    @classmethod
    def from_alpaca(cls, item: Mapping[str, Any]) -> OptionContractRecord:
        return cls(
            symbol=str(item["symbol"]), underlying_symbol=str(item.get("underlying_symbol", item.get("root_symbol", ""))),
            expiration_date=date.fromisoformat(str(item["expiration_date"])), strike_price=float(item["strike_price"]),
            right=str(item["type"]), multiplier=int(float(item["multiplier"])), size=int(float(item["size"])),
            status=str(item["status"]), tradable=bool(item["tradable"]), style=str(item["style"]),
            open_interest=float(item["open_interest"]) if item.get("open_interest") is not None else None,
            open_interest_date=date.fromisoformat(str(item["open_interest_date"])) if item.get("open_interest_date") else None,
        )


class ContractMaster:
    """In-memory validated contract master; refresh is injected for testability."""
    def __init__(self):
        self._contracts: dict[str, OptionContractRecord] = {}

    def upsert(self, record: OptionContractRecord) -> None:
        if record.strike_price <= 0 or record.multiplier <= 0 or record.size <= 0:
            raise ValueError("invalid contract economics")
        if record.right not in {"call", "put"} or record.status not in {"active", "inactive"}:
            raise ValueError("invalid contract classification")
        self._contracts[record.symbol] = record

    def upsert_many(self, records: list[OptionContractRecord]) -> int:
        for record in records:
            self.upsert(record)
        return len(records)

    def get(self, symbol: str) -> OptionContractRecord:
        return self._contracts[symbol]

    def active_for(self, underlying: str, asof: date) -> list[OptionContractRecord]:
        return sorted((r for r in self._contracts.values() if r.underlying_symbol == underlying and r.status == "active" and r.tradable and r.expiration_date >= asof), key=lambda r: (r.expiration_date, r.strike_price, r.right))

    def __len__(self) -> int:
        return len(self._contracts)


async def refresh_contract_master(fetch_page: Callable[[str | None], Awaitable[tuple[list[Mapping[str, Any]], str | None]]], master: ContractMaster) -> int:
    token: str | None = None
    total = 0
    while True:
        rows, token = await fetch_page(token)
        total += master.upsert_many([OptionContractRecord.from_alpaca(row) for row in rows])
        if token is None:
            return total


class AlpacaOptionStreamAdapter:
    """Lazy adapter for Alpaca's msgpack option stream; emits validated MarketEvent objects."""
    def __init__(self, api_key: str, secret_key: str, feed: str = "indicative"):
        if feed not in {"indicative", "opra"}:
            raise ValueError("feed must be indicative or opra")
        self.api_key, self.secret_key, self.feed = api_key, secret_key, feed
        self._stream: Any = None

    def connect(self) -> None:
        from alpaca.data.enums import OptionsFeed
        from alpaca.data.live.option import OptionDataStream
        selected = OptionsFeed.OPRA if self.feed == "opra" else OptionsFeed.INDICATIVE
        self._stream = OptionDataStream(self.api_key, self.secret_key, feed=selected)

    def subscribe_quotes(self, symbols: list[str], handler: Callable[[MarketEvent], Awaitable[None]]) -> None:
        if self._stream is None:
            raise RuntimeError("stream must be connected")

        async def on_quote(message: Any) -> None:
            timestamp = message.timestamp
            sequence = int(timestamp.timestamp() * 1_000_000_000)
            event = MarketEvent("quote", str(message.symbol), timestamp, timestamp, sequence, {"bid": float(message.bid_price), "ask": float(message.ask_price), "bid_size": int(message.bid_size), "ask_size": int(message.ask_size)})
            await handler(event)

        self._stream.subscribe_quotes(on_quote, *symbols)

    def run(self) -> None:
        if self._stream is None:
            raise RuntimeError("stream must be connected")
        self._stream.run()
