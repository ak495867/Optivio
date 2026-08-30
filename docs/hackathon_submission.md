# Optivio — lablab.ai × Alpaca AI Trading Agents Hackathon submission

**One-liner:** Optivio is a leakage-safe options research lab with an Alpaca
paper-trading cockpit, exposed to an AI agent through a 3-tool MCP server and a
matching CLI.

## Problem

Options research is easy to fake. Most backtests leak: a label built from tomorrow
feeds today's feature, or a "decision" silently uses information only available in
replay. The hackathon judges a working agent over a real (paper) Alpaca account, so
the submission must both *reason about options* and *act on Alpaca paper orders*
without shortcuts.

## Stack

- **Python core** (`options_agent/`): point-in-time data contracts, purged
  walk-forward validation, leak-free feature construction, options-aware backtest,
  hybrid Hive–Kronos model, portfolio sizing, risk gates.
- **Native research kernels**: Rust (risk/greeks), C++ (backtest), OCaml (order
  policy) — each CI-tested in the same pipeline.
- **Alpaca integration**: paper `TradingClient` + `OptionHistoricalDataClient`
  (real contract resolution, real latest quotes, option-chain snapshot).
- **Agent surface**: MCP server (`optivio-mcp`, stdio) + CLI (`optivio`) on the
  same risk-gated paper path.

## Three runnable surfaces

1. **MCP tools** — `get_account`, `get_quote`, `submit_order`. The LLM gets the
   paper account, real two-sided quotes for a contract symbol, and a risk-gated
   paper order — never a live endpoint, never a stub contract.
2. **CLI** — `optivio env-check / quote / submit / smoke / run`.
3. **Library** — backtest + walk-forward + model research on timestamped data.

## Safety posture

- **Paper-only, triple-guarded**: `ALPACA_PAPER=1` process guard → `RunMode.PAPER`
  intent default → adapter refuses live intents and constructs `paper=True`
  clients only.
- **Risk-gated orders**: `RiskGate` caps order notional, open notional, and daily
  loss before any submit call; limits come from the same `OPTIVIO_*` knobs an
  operator sets in `.env`.
- **No credential leakage**: keys come from the environment only; `.env` is
  git-ignored; gitleaks runs in CI.
- **No leakage in research**: every observation carries `asof`/`available_at`;
  wall-clock calls are banned from feature-construction modules in CI.

## 3-command demo

```bash
export ALPACA_PAPER=1 ALPACA_API_KEY=... ALPACA_SECRET_KEY=...
optivio env-check                       # paper-only, keys present -> exit 0
optivio quote AAPL260131C00300000       # {bid, ask, sizes, ...} or "available": false
optivio submit AAPL260131C00300000 buy 1 1.25   # risk-gated paper order receipt
```

## Repo layout

```
options_agent/          Python core (data, models, strategies, validation,
                        orchestration, execution)
  execution/            alpaca_adapter, risk_gate, smart_router, live_ops
  mcp_server.py         MCP tools (get_account / get_quote / submit_order)
  cli.py                optivio console entrypoint
cpp/  rust/  ocaml/     Native research kernels (CI-tested)
tests/                  pytest suite (112 passing)
.github/workflows/ci.yml  Python + native + reproducibility + gitleaks
docs/                   Architecture, readiness audit, model docs
```

## Notes

- Historical options data from Alpaca begins February 2024; long-horizon claims
  require a separately licensed, timestamped dataset or they are refused in the
  report.
- Educational and experimental software — not investment advice.