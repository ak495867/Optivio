# Optivio CI/CD and validation design

> **Quick take:** This is the practical release checklist. The goal is to make broken builds, secret leaks, data leakage, and optimistic backtests difficult to sneak into paper trading.

> *“Ship the evidence, not just the executable.”*

## Continuous integration

Every pull request should run deterministic Python compilation, unit tests, Ruff, mypy, Bandit, dependency auditing, secret scanning, Rust formatting/tests/Clippy/audit, C++ warnings-as-errors plus AddressSanitizer/UndefinedBehaviorSanitizer tests, OCaml policy tests, and bridge schema-vector tests. The existing `.github/workflows/ci.yml` contains these gates. The pipeline also verifies that paper mode remains enforced and that no production feature path introduces implicit wall-clock calls or credential literals.

## Research validation job

A separate scheduled or manually approved research workflow should retrieve a versioned immutable dataset, verify its manifest hash, and run:

| Stage | What should happen |
|---|---|
| Data audit | Validate schema, timezone, contract identity, `asof`, `available_at`, revisions, missingness, and quote chronology |
| Feature audit | Fit scalers, tokenizers, HMMs, hedge ratios, and surface transforms on the training block only |
| Backtest | Use bid/ask sides, latency, slippage, fees, partial fills, assignment, expiration, and buying-power constraints |
| Walk-forward | Purge overlapping labels and apply embargo; fit a new model only inside each training window |
| Decay | Measure performance as the model ages and require stability across sequential windows |
| Zero-shot | Freeze the entire model, strategy, optimizer, tokenizer, and feedback cutoff; evaluate once on untouched data |
| Stress | Shock volatility, spreads, liquidity, gaps, correlation, fills, and broker outages |
| Promotion | Require reproducible manifests, signed artifacts, risk limits, model card, and human approval |

The final zero-shot block must never be used to tune hyperparameters, genetic genomes, HMM state counts, thresholds, feature definitions, or risk limits. Results should be written as immutable artifacts containing code revision, data manifest, dependency lock, configuration hash, model hash, and metrics.

## Execution/PnL feedback

`ExecutionStateStore` writes append-only JSONL events with a SHA-256 hash chain. It records order/fill events, event time, availability time, strategy ID, model version, fees, and realized PnL. `feedback()` and `feedback_features()` return only outcomes whose `available_at` is no later than the requested decision cutoff. This makes feedback usable for delayed calibration, drift monitoring, and Bayesian decay without leaking future outcomes into historical decisions.

Realized PnL must not be fed directly into a live model update on every fill. The production design should batch feedback, apply minimum sample counts, use a delayed calibration window, maintain champion/challenger models, and require statistical and risk gates before promotion. Execution records should also be joined with quote snapshots, decision IDs, route choice, fill probability, and expected-versus-realized shortfall.

## Continuous delivery

Only signed, reproducible images or binaries should be promoted from CI to a paper environment. Deployment should use separate credentials and namespaces for research, shadow, signal-only, and autonomous paper stages. Runtime configuration must be immutable after startup except for a separately authenticated kill switch. Rollbacks must restore code, model, configuration, and schema versions together.
