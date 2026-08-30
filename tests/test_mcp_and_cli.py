"""MCP server and CLI tests (no network, no API keys, fakes/monkeypatch).

The MCP server is import-safe without the optional ``mcp`` SDK. Tool calls that
need the SDK raise a clear ``ImportError`` directing the operator to install it.
"""
import json
from datetime import UTC, datetime

import pytest

import options_agent.mcp_server as mcp_server
from options_agent.contracts import OptionRight, Quote
from options_agent.data.quote_store import QuoteStore
from tests.test_quote_store import contract


def _reset_server_state(monkeypatch):
    """Clear the module-level adapter/store singletons between tests."""
    monkeypatch.setattr(mcp_server, "_adapter_instance", None)
    monkeypatch.setattr(mcp_server, "_quote_store", None)


def _fake_adapter(quote=None, contract_=None):
    class _FakeAdapter:
        def __init__(self):
            self.submitted = []
            self.calls = []

        def account_snapshot(self):
            from options_agent.contracts import RiskSnapshot

            return RiskSnapshot(
                equity=1000.0,
                buying_power=500.0,
                open_option_notional=0.0,
                daily_loss=0.0,
                kill_switch=False,
            )

        def get_latest_quote(self, symbol):
            self.calls.append(("get_latest_quote", symbol))
            return quote

        def get_option_contract(self, symbol):
            self.calls.append(("get_option_contract", symbol))
            if contract_ is not None:
                return contract_
            raise ValueError(f"unknown contract {symbol}")

        def submit_paper(self, intent):
            self.submitted.append(intent)
            return {"id": "fake-order-1", "symbol": intent.contract.symbol}

    return _FakeAdapter()


def test_mcp_module_import_safe():
    # Importing must not require the optional `mcp` package.
    assert hasattr(mcp_server, "mcp_get_quote")


def test_serve_requires_mcp_sdk(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def deny(name, *args, **kwargs):
        if name == "mcp.server.fastmcp":
            raise ImportError("mcp is not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny)
    with pytest.raises(ImportError, match="optivio\\[mcp\\]"):
        mcp_server.serve(None)


def test_serve_registers_exactly_three_tools_on_custom_app():
    registered = {}

    class _FakeApp:
        def tool(self):
            def deco(fn):
                registered[fn.__name__] = fn
                return fn

            return deco

    app = mcp_server.serve(_FakeApp())
    assert app is not None
    assert set(registered) == {"mcp_get_account", "mcp_get_quote", "mcp_submit_order"}


def test_mcp_list_all_tools_exact_three():
    names = [t["name"] for t in mcp_server.mcp_list_all_tools()]
    assert names == ["get_account", "get_quote", "submit_order"]


def test_mcp_get_quote_two_sided(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER", "1")
    _reset_server_state(monkeypatch)
    q = Quote(
        contract=contract(),
        asof=datetime(2026, 8, 30, 12, tzinfo=UTC),
        available_at=datetime(2026, 8, 30, 12, tzinfo=UTC),
        bid=2.0,
        ask=2.1,
        bid_size=5,
        ask_size=9,
    )
    adapter = _fake_adapter(quote=q)
    monkeypatch.setattr(mcp_server, "_adapter", lambda: adapter)
    out = mcp_server.mcp_get_quote("AAPL260131C00300000")
    assert out["available"] is True
    assert out["symbol"] == "AAPL260131C00300000"
    assert out["underlying"] == "AAPL"
    assert out["strike"] == 300.0
    assert out["right"] == OptionRight.CALL.value
    assert out["bid"] == 2.0 and out["ask"] == 2.1
    assert out["source"] in ("stream", "api")


def test_mcp_get_quote_unavailable_when_one_sided(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER", "1")
    _reset_server_state(monkeypatch)
    adapter = _fake_adapter(quote=None)
    monkeypatch.setattr(mcp_server, "_adapter", lambda: adapter)
    out = mcp_server.mcp_get_quote("AAPL260131C00300000")
    assert out["available"] is False
    assert out["symbol"] == "AAPL260131C00300000"
    assert out["reason"]


def test_mcp_get_quote_uses_cache_on_second_call(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER", "1")
    _reset_server_state(monkeypatch)
    q = Quote(
        contract=contract(),
        asof=datetime(2026, 8, 30, 12, tzinfo=UTC),
        available_at=datetime(2026, 8, 30, 12, tzinfo=UTC),
        bid=1.0,
        ask=1.1,
        bid_size=1,
        ask_size=1,
    )
    adapter = _fake_adapter(quote=q)
    store = QuoteStore()
    store.record(q)
    monkeypatch.setattr(mcp_server, "_adapter", lambda: adapter)
    monkeypatch.setattr(mcp_server, "_quote_store", store)
    out = mcp_server.mcp_get_quote("AAPL260131C00300000")
    assert out["available"] is True and out["source"] == "stream"
    # Second call must not touch the adapter (cache hit).
    adapter.calls.clear()
    mcp_server.mcp_get_quote("AAPL260131C00300000")
    assert adapter.calls == []


def test_mcp_submit_order_builds_real_contract_and_passes_risk_gate(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER", "1")
    _reset_server_state(monkeypatch)
    ct = contract("AAPL260131C00300000")
    adapter = _fake_adapter(contract_=ct)
    monkeypatch.setattr(mcp_server, "_adapter", lambda: adapter)
    result = mcp_server.mcp_submit_order(
        contract_symbol="AAPL260131C00300000",
        side="buy",
        quantity=1,
        limit_price=1.25,
    )
    assert result["submitted"] is True
    assert result["order"]["symbol"] == "AAPL260131C00300000"
    assert result["paper"] is True
    assert len(adapter.submitted) == 1
    intent = adapter.submitted[0]
    assert intent.contract.underlying == "AAPL"
    assert intent.contract.strike == 300.0


def test_mcp_submit_order_risk_gate_rejects_large_notional(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER", "1")
    _reset_server_state(monkeypatch)
    ct = contract("AAPL260131C00300000")
    monkeypatch.setattr(mcp_server, "_adapter", lambda: _fake_adapter(contract_=ct))
    # 1.25 * 40 * 100 = 5000 > default 2500 max order notional.
    with pytest.raises(RuntimeError, match="risk gate"):
        mcp_server.mcp_submit_order(
            contract_symbol="AAPL260131C00300000",
            side="buy",
            quantity=40,
            limit_price=1.25,
        )


def test_mcp_submit_order_rejects_unknown_contract(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER", "1")
    _reset_server_state(monkeypatch)
    adapter = _fake_adapter(contract_=None)
    monkeypatch.setattr(mcp_server, "_adapter", lambda: adapter)
    with pytest.raises(ValueError, match="unknown contract"):
        mcp_server.mcp_submit_order(
            contract_symbol="BOGUS", side="buy", quantity=1, limit_price=1.0
        )


def test_mcp_get_quote_paper_guard(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER", "0")
    with pytest.raises(RuntimeError, match="ALPACA_PAPER"):
        mcp_server.mcp_get_quote("AAPL260131C00300000")


def test_mcp_submit_order_paper_guard(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER", "0")
    with pytest.raises(RuntimeError, match="ALPACA_PAPER"):
        mcp_server.mcp_submit_order(
            contract_symbol="AAPL260131C00300000",
            side="buy",
            quantity=1,
            limit_price=1.0,
        )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_cli_env_check_exit_codes(monkeypatch, capsys):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    from options_agent import cli

    assert cli.main(["env-check"]) == 1
    captured = capsys.readouterr()
    assert "alpaca_keys_present" in captured.out


def test_cli_quote_returns_json(monkeypatch, capsys):
    monkeypatch.setenv("ALPACA_PAPER", "1")
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    _reset_server_state(monkeypatch)
    q = Quote(
        contract=contract(),
        asof=datetime(2026, 8, 30, 12, tzinfo=UTC),
        available_at=datetime(2026, 8, 30, 12, tzinfo=UTC),
        bid=2.0,
        ask=2.1,
        bid_size=5,
        ask_size=9,
    )
    monkeypatch.setattr(mcp_server, "_adapter", lambda: _fake_adapter(quote=q))
    from options_agent import cli

    assert cli.main(["quote", "AAPL260131C00300000"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["available"] is True and payload["bid"] == 2.0


def test_cli_quote_unavailable_exit_2(monkeypatch, capsys):
    monkeypatch.setenv("ALPACA_PAPER", "1")
    _reset_server_state(monkeypatch)
    monkeypatch.setattr(mcp_server, "_adapter", lambda: _fake_adapter(quote=None))
    from options_agent import cli

    assert cli.main(["quote", "AAPL260131C00300000"]) == 2
    assert "available" in capsys.readouterr().out


def test_cli_submit_paper_order(monkeypatch, capsys):
    monkeypatch.setenv("ALPACA_PAPER", "1")
    _reset_server_state(monkeypatch)
    ct = contract("AAPL260131C00300000")
    adapter = _fake_adapter(contract_=ct)
    monkeypatch.setattr(mcp_server, "_adapter", lambda: adapter)
    from options_agent import cli

    assert cli.main(["submit", "AAPL260131C00300000", "buy", "1", "1.25"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["submitted"] is True
    assert len(adapter.submitted) == 1
    assert adapter.submitted[0].contract.strike == 300.0


def test_cli_unknown_command_usage_exit():
    from options_agent import cli

    with pytest.raises(SystemExit):
        cli.main(["definitely-not-a-command"])


def test_cli_paper_guard_blocks_submit(monkeypatch, capsys):
    monkeypatch.setenv("ALPACA_PAPER", "0")
    from options_agent import cli

    assert cli.main(["submit", "AAPL260131C00300000", "buy", "1", "1.25"]) == 1
    assert "ALPACA_PAPER" in capsys.readouterr().err