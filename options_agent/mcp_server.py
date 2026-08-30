"""Model Context Protocol (MCP) server exposing Optivio's paper-only trading agents.

This is the hackathon-required integration surface for the Alpaca stack. It reuses the
existing `AlpacaPaperAdapter` and `RiskGate` so the LLM operates the same paper-only,
risk-gated execution path the library already guarantees — it never introduces a live
endpoint and never bypasses `RiskLimits`.

The server is import-safe without the optional `mcp` package: importing this module
does not raise. Tool calls that need the SDK raise a clear ``ImportError`` directing the
operator to install ``optivio[mcp]`` / ``mcp``.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from options_agent.contracts import OrderIntent, Side
from options_agent.execution.risk_gate import RiskGate, RiskLimits
from options_agent.data.quote_store import QuoteStore

_tools_registered: bool = False
# One adapter (one paper TradingClient + one data client) + one quote cache per
# process, shared by the MCP tools and the CLI.
_adapter_instance: Any = None
_quote_store: QuoteStore | None = None


def _paper_env_guard() -> None:
    if os.environ.get("ALPACA_PAPER", "1") != "1":
        raise RuntimeError("Refusing to operate: ALPACA_PAPER must be 1 (paper-only)")


def _get_quote_store() -> QuoteStore:
    global _quote_store
    if _quote_store is None:
        _quote_store = QuoteStore()
    return _quote_store


def _adapter() -> Any:
    global _adapter_instance
    _paper_env_guard()
    if _adapter_instance is None:
        from options_agent.execution.alpaca_adapter import AlpacaPaperAdapter

        _adapter_instance = AlpacaPaperAdapter()
        _adapter_instance.attach_quote_store(_get_quote_store())
    return _adapter_instance


def _risk_gate() -> RiskGate:
    # Load limits from the environment so the same knobs the shell sets drive the MCP path.
    return RiskGate(RiskLimits.from_env())


# ---------------------------------------------------------------------------
# Tool implementations (pure functions; safe to call directly, no SDK required).
# ---------------------------------------------------------------------------


def mcp_get_account() -> dict[str, Any]:
    """Return the paper account equity, buying power, and open-options notional."""
    snap = _adapter().account_snapshot()
    return {
        "equity": snap.equity,
        "buying_power": snap.buying_power,
        "open_option_notional": snap.open_option_notional,
        "daily_loss": snap.daily_loss,
        "paper": True,
    }


def mcp_get_quote(symbol: str) -> dict[str, Any]:
    """Return the latest two-sided option quote (bid/ask/sizes) for a contract symbol."""
    _paper_env_guard()
    if not symbol:
        raise ValueError("symbol is required")
    store = _get_quote_store()
    cached = store.get_fresh(symbol)
    src = "stream"
    if cached is not None:
        return _quote_payload(cached, source=src)
    adapter = _adapter()
    latest: Any = adapter.get_latest_quote(symbol)
    if latest is None:
        return {
            "symbol": symbol,
            "available": False,
            "source": "api",
            "reason": "no two-sided quote available (missing/invalid side)",
        }
    return _quote_payload(latest, source="api")


def _quote_payload(quote: Any, source: str) -> dict[str, Any]:
    return {
        "symbol": quote.contract.symbol,
        "underlying": quote.contract.underlying,
        "expiration": quote.contract.expiration.isoformat()[:10],
        "strike": quote.contract.strike,
        "right": quote.contract.right.value,
        "bid": quote.bid,
        "ask": quote.ask,
        "bid_size": quote.bid_size,
        "ask_size": quote.ask_size,
        "asof": quote.asof.isoformat(),
        "available": True,
        "source": source,
    }


def mcp_submit_order(
    contract_symbol: str,
    side: str,
    quantity: int,
    limit_price: float,
    models_from_followups: bool = True,
) -> dict[str, Any]:
    """Place a risk-gated paper order using a real, authoritative contract.

    Args:
        contract_symbol: Alpaca options OCC contract symbol.
        side: "buy" or "sell".
        quantity: whole-number contract count.
        limit_price: limit price for the order.
    """
    _paper_env_guard()
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")
    if quantity <= 0:
        raise ValueError("quantity must be a positive integer")
    if limit_price <= 0:
        raise ValueError("limit_price must be positive")
    adapter = _adapter()

    # Resolve the real contract (underlying, expiration, strike, right) from the
    # paper trading client's authoritative option-contracts endpoint. A stub is
    # never used: if the symbol is unknown/untradable the adapter raises.

    contract = adapter.get_option_contract(contract_symbol)
    now = datetime.now(timezone.utc)
    intent = OrderIntent(
        client_order_id=f"mcp-{int(now.timestamp())}",
        contract=contract,
        side=Side(side),
        quantity=int(quantity),
        limit_price=float(limit_price),
        rationale="MCP paper order",
        model_version="mcp-v1",
        signal_asof=now,
        created_at=now,
    )

    # The notional RiskGate is the correct single-order boundary: limit_price *
    # quantity * multiplier must be <= max_order_notional (default 2500), plus the
    # open-notional and daily-loss caps. Never let an LLM call bypass it.
    snap = adapter.account_snapshot()
    ok, reason = _risk_gate().approve(intent, snap)
    if not ok:
        raise RuntimeError(f"risk gate rejected order: {reason}")

    submitted = adapter.submit_paper(intent)
    return {"submitted": True, "order": submitted, "paper": True}


def mcp_list_all_tools() -> list[dict[str, Any]]:
    """Return the tool definitions for this server (3 real tools; discovery helper)."""
    return [
        {
            "name": "get_account",
            "description": "Return paper account equity, buying power, and open-notional.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_quote",
            "description": "Return the latest two-sided quote for an options contract symbol.",
            "inputSchema": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
        {
            "name": "submit_order",
            "description": "Place a risk-gated paper options order.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "contract_symbol": {"type": "string"},
                    "side": {"type": "string", "enum": ["buy", "sell"]},
                    "quantity": {"type": "integer"},
                    "limit_price": {"type": "number"},
                },
                "required": ["contract_symbol", "side", "quantity", "limit_price"],
            },
        },
    ]


def _register_with_mcp(mcp: Any) -> None:
    """Register the three real tools on an `mcp.server.FastMCP`/`Server` instance.

    `mcp_list_all_tools` is intentionally NOT registered as an MCP tool — it is a
    plain discovery function callable directly by clients or the CLI.
    """
    global _tools_registered
    mcp.tool()(mcp_get_account)
    mcp.tool()(mcp_get_quote)
    mcp.tool()(mcp_submit_order)
    _tools_registered = True


def serve(mcp_app: Any | None = None) -> Any:
    """Return a configured MCP server, or create one from the `mcp` package.

    Args:
        mcp_app: optional, a compatible MCP app object (e.g. FastMCP). If None, the
            `mcp` SDK is imported and a FastMCP server named "optivio" is created.

    Supports both mcp 1.x (`mcp.server.fastmcp.FastMCP`) and mcp 2.x
    (`mcp.server.mcpserver.MCPServer`). The latter is preferred when available.
    """
    if mcp_app is not None:
        _register_with_mcp(mcp_app)
        return mcp_app
    try:
        try:
            from mcp.server.mcpserver import MCPServer as _MCPApp
        except ImportError:
            from mcp.server.fastmcp import FastMCP as _MCPApp
    except ImportError as exc:  # pragma: no cover - exercised only when SDK absent
        raise ImportError(
            "Install the optional MCP dependency to run the Optivio MCP server: "
            "`pip install 'optivio[mcp]'` (or `mcp`)."
        ) from exc
    app = _MCPApp("optivio")
    _register_with_mcp(app)
    return app


def main() -> None:
    """Entry point: `python -m options_agent.mcp_server` runs the MCP stdio server."""
    try:
        app = serve()
    except ImportError as exc:
        raise SystemExit(str(exc)) from exc
    app.run()


if __name__ == "__main__":
    main()
