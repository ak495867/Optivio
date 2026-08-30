# Optivio

> **Quick take:** Think of Optivio as a careful research lab with a paper-trading cockpit attached. It helps you move from raw market data to tested ideas, but it refuses to act like yesterday’s information was available tomorrow.

> *“If the data cannot be replayed, the decision cannot be trusted.”*

Optivio is a **research-first options system**. It combines point-in-time data contracts, options-aware backtesting, purged walk-forward validation, strategy-decay tests, graph message passing, a DeepGBM component, a custom Hive-Kronos hybrid model, genetic/evolutionary optimization, Kalman filtering, Bayesian decay, mathematical factors, active regime classification, portfolio sizing, smart routing, optional native Hive/Kronos adapters, and a Groq manager for structured alternative-data assessment. The execution boundary is intentionally limited to Alpaca paper trading.

> The LLM can interpret supplied alternative data and coordinate research tasks, but it cannot submit orders, alter provenance, disable risk checks, or select a live endpoint.

## Architecture

| Layer | Responsibility | Safety boundary |
|---|---|---|
| Data contracts | Timestamped bars, quotes, features, contracts, and signals | Every observation has `asof` and `available_at`; future availability is rejected |
| Feature pipeline | Point-in-time indicators and fold-local transforms | Scalers are fit only on the training fold |
| Models | Graph network, DeepGBM, optional Hive and Kronos adapters | Models receive already-frozen fold data; no network fetching |
| Strategies | PCR/VIX-inspired signal construction and liquid-contract selection | Liquidity, DTE, spread, confidence, and notional gates |
| Validation | Backtest, purged walk-forward, decay, shortfall-ready fills | Bid/ask, slippage, commissions, rejected orders, and audit records |
| Orchestration | Groq structured JSON assessment of supplied alt data | Provenance IDs are immutable; abstention is supported |
| Execution | Smart router, risk gate, Alpaca paper adapter | `paper=True`; only `OrderIntent(mode=paper)` is accepted; no LLM on hot path |
| Portfolio | Volatility targeting, concentration/cash limits, regime scaling | Hard caps override model outputs |

## Repository reuse

The specified repositories are treated as references rather than blindly copied into production. The custom hybrid model is documented in `docs/optivio_hybrid_model.md`, and evolutionary search is restricted to training-fold objectives. Quantfx contributes the concepts of deterministic replay, shortfall accounting, durable state, kill switches, and purged walk-forward tests. Ito contributes order-intent, risk-gate, journaling, reconciliation, and failover concepts. Hive contributes the small recurrent ring-coupled portfolio model and cost-aware post-processing ideas. Kronos is isolated behind a lazy adapter for OHLCV forecasting. StockSharp is an architectural reference for connectors and market-data storage. The sentiment and educational options repositories are baseline references only; any feature derived from them must carry point-in-time provenance.

## Leakage policy

A row is usable at decision time `t` only if both `asof <= t` and `available_at <= t`. Labels are created separately and are never passed into feature construction. Every training fold gets its own scaler and model. Purge intervals remove overlapping label horizons between training and test windows, and embargo intervals prevent immediate post-test contamination. Alternative data must carry stable source IDs and an event/availability time; unclear or revised information causes abstention. No code in the execution path calls `datetime.now()` to create a market feature.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[all]'
pytest -q
```

Environment variables for paper trading are read only at runtime. Start from the included `.env.example`, copy it to `.env`, and populate secrets through the shell or a secret manager:

```bash
cp .env.example .env
export ALPACA_API_KEY='...'
export ALPACA_SECRET_KEY='...'
export GROQ_API_KEY='...'
export GROQ_MODEL='llama-3.3-70b-versatile'
```

The real `.env` file is excluded by `.gitignore`; only `.env.example` is intended to be committed.

No credentials are stored in source files, configuration files, logs, or model prompts. Use a secret manager in any persistent deployment. The current adapter should remain paper-only until reconciliation, corporate-action handling, options assignment handling, and operational controls are independently certified.

## Model readiness

For a component-by-component status report, read `docs/model_readiness_audit.md`. It separates implemented, unit-tested, orchestrated, live-data-capable, and production-ready claims so a passing fixture test is not mistaken for a live trading certification.

## Data limitations

Alpaca documentation currently describes historical options data beginning in February 2024. Therefore, a long-horizon options backtest must either use a separately licensed historical options source with an explicit source record or refuse to produce a long-history result. Underlying OHLCV data alone is insufficient to claim realistic options performance.

## Recommended workflow

First ingest immutable raw data and provenance metadata. Next freeze a decision cutoff, validate timestamps, and build features only from rows available by that cutoff. Run fold-local training and inference. Convert model outputs into deterministic signals and pass them through liquidity, risk, and buying-power checks. Backtest with quote-side execution and conservative costs. Run purged walk-forward, decay, stress, and implementation-shortfall tests. Only after the complete research report is reviewed should a user connect Alpaca paper credentials and run reconciliation-aware paper orders.

Zero-shot and latency benchmarks are intentionally data-dependent. Optivio does not manufacture historical returns or claim performance without a user-supplied, timestamped contract-level dataset. The benchmark reports p50/p95/p99 local decision latency separately from broker network latency.

This repository is educational and experimental software, not investment advice or a guarantee of performance. Options involve substantial risk, including total loss and assignment risk.

## References

[1]: https://github.com/ak495867/Quantfx "Quantfx repository"
[2]: https://github.com/ak495867/Hive "Hive repository"
[3]: https://github.com/shiyu-coder/Kronos "Kronos repository"
[4]: https://github.com/StockSharp/StockSharp "StockSharp repository"
[5]: https://github.com/ak495867/Ito "Ito repository"
[6]: https://github.com/abdulfatir/twitter-sentiment-analysis "Twitter sentiment analysis repository"
[7]: https://github.com/PyPatel/Options-Trading-Strategies-in-Python "Options strategies repository"
[8]: https://docs.alpaca.markets/us/docs/options-trading "Alpaca options trading documentation"
[9]: https://docs.alpaca.markets/us/docs/historical-option-data "Alpaca historical options data documentation"
