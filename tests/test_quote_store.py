"""Tests for the latest-quote cache and mappers (no network, no API keys)."""

import types
from datetime import UTC, date, datetime

import pytest

from options_agent.contracts import OptionContract, OptionRight
from options_agent.data.live_market import ContractMaster, OptionContractRecord
from options_agent.data.quote_store import (
    QuoteStore,
    build_quote_from_snapshot,
    build_quote_from_stream_event,
    parse_occ_symbol,
    record_to_contract,
    stream_handler,
)


def contract(symbol: str = "AAPL260131C00300000") -> OptionContract:
    return OptionContract(
        symbol=symbol,
        underlying="AAPL",
        expiration=datetime(2026, 1, 31, tzinfo=UTC),
        strike=300.0,
        right=OptionRight.CALL,
    )


def test_parse_occ_symbol():
    root, expiry, right, strike = parse_occ_symbol("AAPL260131C00300000")
    assert root == "AAPL"
    assert expiry.date() == date(2026, 1, 31)
    assert right == OptionRight.CALL
    assert strike == 300.0
    # A put parses and the right is PUT.
    root, _d, right_put, _s = parse_occ_symbol("SPX260131P00500000")
    assert root == "SPX" and right_put == OptionRight.PUT and _s == 500.0
    with pytest.raises(ValueError):
        parse_occ_symbol("nonsense")


def test_build_quote_from_snapshot_skips_invalid_sides():
    ct = contract()
    ts = datetime(2026, 8, 30, tzinfo=UTC)
    # zero bid
    assert (
        build_quote_from_snapshot(
            ct,
            types.SimpleNamespace(
                bid_price=0.0, ask_price=2.0, bid_size=1, ask_size=1, timestamp=ts
            ),
        )
        is None
    )
    # zero ask
    assert (
        build_quote_from_snapshot(
            ct,
            types.SimpleNamespace(
                bid_price=1.0, ask_price=0.0, bid_size=1, ask_size=1, timestamp=ts
            ),
        )
        is None
    )
    # crossed
    assert (
        build_quote_from_snapshot(
            ct,
            types.SimpleNamespace(
                bid_price=2.1, ask_price=2.0, bid_size=1, ask_size=1, timestamp=ts
            ),
        )
        is None
    )
    # zero sizes
    assert (
        build_quote_from_snapshot(
            ct,
            types.SimpleNamespace(
                bid_price=1.0, ask_price=2.0, bid_size=0, ask_size=1, timestamp=ts
            ),
        )
        is None
    )
    # None quote -> None
    assert build_quote_from_snapshot(ct, None, ts) is None


def test_build_quote_from_snapshot_produces_valid_quote():
    ct = contract()
    ts = datetime(2026, 8, 30, tzinfo=UTC)
    lq = types.SimpleNamespace(
        bid_price=2.0, ask_price=2.1, bid_size=5, ask_size=9, timestamp=ts
    )
    q = build_quote_from_snapshot(ct, lq)
    assert q is not None
    assert q.bid == 2.0 and q.ask == 2.1 and q.bid_size == 5 and q.ask_size == 9
    assert q.asof == ts


def test_build_quote_from_stream_event_requires_event_time():
    ct = contract()
    payload = {"bid": 1.0, "ask": 1.1, "bid_size": 2, "ask_size": 3}
    evt_ts = datetime(2026, 8, 30, 12, tzinfo=UTC)
    q = build_quote_from_stream_event(ct, payload, event_time=evt_ts)
    assert q is not None and q.asof == evt_ts and q.available_at == evt_ts
    assert build_quote_from_stream_event(ct, payload, event_time=None) is None
    # crossed payload skipped
    assert (
        build_quote_from_stream_event(
            ct,
            {"bid": 2.0, "ask": 1.0, "bid_size": 1, "ask_size": 1},
            event_time=evt_ts,
        )
        is None
    )


def test_store_record_get_and_recency():
    store = QuoteStore(max_age_seconds=60)
    q = contract()
    store.attach_clock(lambda: 0.0)
    store.record(
        build_quote_from_snapshot(
            q,
            types.SimpleNamespace(
                bid_price=1.0,
                ask_price=1.1,
                bid_size=1,
                ask_size=1,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            ),
        )
    )
    # Fresh (clock 0, stored quote timestamp far past but the injected clock
    # measures wall time, not the quote timestamp).
    assert store.get_fresh("AAPL260131C00300000") is not None
    assert len(store) == 1 and store.symbols() == {"AAPL260131C00300000"}
    unknown = store.get("nope")
    assert unknown is None


def test_record_to_contract_from_contract_master():
    master = ContractMaster()
    master.upsert(
        OptionContractRecord(
            "A1",
            "A",
            date(2026, 2, 1),
            100,
            "call",
            100,
            100,
            "active",
            True,
            "american",
        )
    )
    ct = record_to_contract(master.get("A1"))
    assert (
        ct.underlying == "A" and ct.right == OptionRight.CALL and ct.multiplier == 100
    )


def test_stream_handler_records_into_store():
    from options_agent.data.live_market import MarketEvent

    master = ContractMaster()
    master.upsert(
        OptionContractRecord(
            "AAPL260131C00300000",
            "AAPL",
            date(2026, 1, 31),
            300.0,
            "call",
            100,
            100,
            "active",
            True,
            "american",
        )
    )
    store = QuoteStore()
    handler = stream_handler(store, master)
    evt_ts = datetime(2026, 8, 30, 12, tzinfo=UTC)
    event = MarketEvent(
        "quote",
        "AAPL260131C00300000",
        evt_ts,
        evt_ts,
        1,
        {"bid": 2.0, "ask": 2.1, "bid_size": 5, "ask_size": 9},
    )
    handler(event)
    assert len(store) == 1
    q = store.get("AAPL260131C00300000")
    assert q is not None and q.bid == 2.0 and q.asof == evt_ts
    # Unknown symbol: handler must not raise.
    handler(
        MarketEvent(
            "quote",
            "UNKNOWN",
            evt_ts,
            evt_ts,
            2,
            {"bid": 2.0, "ask": 2.1, "bid_size": 5, "ask_size": 9},
        )
    )
    assert len(store) == 1
