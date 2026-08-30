# Repository integration and safety audit

> **Quick take:** These notes explain what Optivio learned from the referenced projects and where it drew the line. Reuse is useful; copying assumptions without their context is not.

> *“Borrow patterns, not blind spots.”*

The implementation deliberately uses **adapter boundaries** instead of copying external repositories into the execution path. This is important because several upstream examples are research demonstrations rather than production trading systems.

| Source | Adopted concept | Excluded from execution path | Reason |
|---|---|---|---|
| Quantfx | Deterministic replay, purged walk-forward, shortfall accounting, durable audit and kill-switch concepts | NASM engine and FX-specific wire formats | Options require contract/quote/assignment semantics and a Python-first research surface |
| Hive | Small ring-coupled recurrent portfolio architecture, turnover/cost-aware post-processing | Direct yfinance downloads and fold-agnostic normalization | External fetching and global/rolling normalization can create reproducibility or leakage problems |
| Kronos | OHLCV foundation-model adapter and explicit context boundary | Example scripts that fetch data dynamically or generate fallback random data | Features must come from an immutable, timestamped data manifest |
| StockSharp | Connector, market-data storage, and strategy-platform architecture | Entire C# platform | Too broad for the first implementation; the Alpaca adapter is explicit and testable |
| Ito | Risk gate, order-intent schema, reconciliation, journaling, failover concepts | Hardware/RTL/OCaml/Rust production stack | Useful safety patterns, but not required to validate the Python paper system |
| Twitter sentiment | Baseline sentiment-model idea | Legacy training/data pipeline | Alternative-data ingestion must preserve publication time, source IDs, and revision history |
| Options strategies | PCR, TRIN, Turtle, VIX strategy ideas | Unmodified educational scripts | They require options-aware execution, costs, liquidity, and point-in-time feature construction |

## Leakage audit

The new production package contains no wall-clock calls for feature or order timestamps, no credential literals, and no unbounded external data fetches. `FeatureRow`, `Quote`, and the cutoff utilities require `asof` and `available_at`. Walk-forward evaluation fits a new standardizer inside every training fold and inserts purge and embargo intervals. The LLM schema preserves source IDs and supports abstention. The paper adapter hard-codes `paper=True` and accepts only `OrderIntent` objects whose mode is paper.

The audit does **not** prove that upstream model weights or third-party data are free of hidden leakage. Any downloaded checkpoint, dataset, sentiment corpus, or historical option source must be versioned with a manifest containing acquisition time, data availability time, revisions, license, and hash. Do not use Alpaca underlying bars as a substitute for historical option quotes. Alpaca’s documented historical options coverage begins in February 2024, so earlier options results require an explicitly disclosed second source.

## Operational gaps before wider paper deployment

The next engineering increment should add durable order and position reconciliation, option assignment/exercise event processing, corporate-action normalization, market-calendar handling, rate-limit/backoff controls, persistent structured audit logs, idempotent client-order IDs, a kill-switch service, and a separate approval process for model/checkpoint promotion. A production run should first be shadow-only, then paper-only with no automatic order submission, then paper with deterministic risk-gated submission and daily reconciliation.

No performance claim is made by this repository. Backtest output is only meaningful after the user supplies a properly timestamped contract-level dataset and documents its historical coverage and execution assumptions.
