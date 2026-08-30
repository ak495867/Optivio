from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from typing import Any


def _paper_env_guard() -> None:
    if os.environ.get("ALPACA_PAPER", "1") != "1":
        raise RuntimeError("ALPACA_PAPER must be 1 (paper-only)")


def _adapter() -> Any:
    from options_agent.execution.alpaca_adapter import AlpacaPaperAdapter

    _paper_env_guard()
    return AlpacaPaperAdapter()


def cmd_env_check(_args: argparse.Namespace) -> int:
    """Report credential/paper/SDK readiness without any network calls."""
    from options_agent.config import settings

    checks = {
        "alpaca_keys_present": bool(
            os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY")
        ),
        "alpaca_sdk": importlib.util.find_spec("alpaca") is not None,
        "groq_key_present": bool(os.getenv("GROQ_API_KEY")),
        "mcp_sdk": importlib.util.find_spec("mcp") is not None,
        "execution_mode": "paper-only",
        "data_feed": settings.data_feed,
    }
    ok = checks["alpaca_keys_present"] and checks["alpaca_sdk"]
    print(json.dumps(checks, indent=2, sort_keys=True))
    return 0 if ok else 1


def cmd_quote(args: argparse.Namespace) -> int:
    """Resolve a contract and fetch the latest two-sided quote (JSON)."""
    from options_agent.mcp_server import mcp_get_quote

    _paper_env_guard()
    result = mcp_get_quote(args.symbol)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("available") else 2


def cmd_submit(args: argparse.Namespace) -> int:
    """Submit a risk-gated paper order. Same path as the MCP submit_order tool."""
    from options_agent.mcp_server import mcp_submit_order

    _paper_env_guard()
    side = "buy" if args.side == "buy" else "sell"
    result = mcp_submit_order(
        contract_symbol=args.symbol,
        side=side,
        quantity=args.quantity,
        limit_price=args.limit_price,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("submitted") else 1


def cmd_smoke(args: argparse.Namespace) -> int:
    """Brief live options-stream connectivity check; never submits orders."""
    from options_agent.execution.live_ops import alpaca_paper_stream_smoke_test

    symbols = args.symbols.split(",") if args.symbols else ["AAPL260131C00300000"]
    result = alpaca_paper_stream_smoke_test(symbols, seconds=args.seconds)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("ok") else 1


def cmd_run(args: argparse.Namespace) -> int:
    """Run the orchestrator component preflight + sequence (SIGNAL_ONLY, no network)."""
    from options_agent.orchestration.runtime import (
        OptivioOrchestrator,
        RuntimeCredentials,
        RuntimeMode,
    )

    runner = OptivioOrchestrator()
    credentials = RuntimeCredentials(
        alpaca_key=os.getenv("ALPACA_API_KEY", ""),
        alpaca_secret=os.getenv("ALPACA_SECRET_KEY", ""),
        paper_endpoint="https://paper-api.alpaca.markets",
    )
    ok, detail = runner.start(credentials, RuntimeMode.SIGNAL_ONLY)
    print(f"start: {'ok' if ok else 'blocked'} — {detail}")
    for gate in runner.snapshot.gates:
        print(f"  {gate.name}: {'pass' if gate.passed else 'FAIL'} — {gate.detail}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="optivio",
        description="Leakage-safe options research and Alpaca paper-trading agent.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("env-check", help="Report readiness (no network)")

    p_quote = sub.add_parser("quote", help="Latest two-sided quote for a symbol")
    p_quote.add_argument("symbol")

    p_submit = sub.add_parser("submit", help="Risk-gated paper order")
    p_submit.add_argument("symbol")
    p_submit.add_argument("side", choices=["buy", "sell"])
    p_submit.add_argument("quantity", type=int)
    p_submit.add_argument("limit_price", type=float)

    p_smoke = sub.add_parser("smoke", help="Brief options-stream connectivity test")
    p_smoke.add_argument("--symbols", default="")
    p_smoke.add_argument("--seconds", type=float, default=5.0)

    sub.add_parser("run", help="Orchestrator preflight + sequence (no network)")

    args = parser.parse_args(argv)
    handlers = {
        "env-check": cmd_env_check,
        "quote": cmd_quote,
        "submit": cmd_submit,
        "smoke": cmd_smoke,
        "run": cmd_run,
    }
    handler = handlers[args.command]
    try:
        return handler(args)
    except (RuntimeError, ValueError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())