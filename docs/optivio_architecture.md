# Optivio architecture

> **Quick take:** Here is how the pieces fit together, from market events to model output to a risk-approved paper order. The research side can be creative; the execution side should stay calm and deterministic.

> *“Keep the cleverness upstream of the safety boundary.”*

Optivio is a research-first options system with a fast deterministic execution core and a slower supervisory intelligence layer. The fast path must never wait for an LLM, perform network discovery, fit a model, or allocate unbounded objects. It consumes validated market events, maintains in-memory state, applies precomputed signals and risk limits, selects an order route, and emits an auditable paper order intent.

| Plane | Components | Performance objective | Safety rule |
|---|---|---:|---|
| Market-data plane | Alpaca option quotes/bars, normalized event bus, timestamp validator | O(1) state updates; bounded queues | Reject stale, crossed, or future-available events |
| Signal plane | Kalman state, factors, regime classifier, Hive/Kronos/GBM features | Batch or scheduled inference; never in order-submit path | Models use only frozen point-in-time features |
| Portfolio plane | Greeks/notional exposure, target weights, concentration and liquidity budgets | Deterministic vectorized rebalance | Hard limits override all model outputs |
| Execution plane | Smart order routing, spread/size checks, limit-price logic, risk gate | Microsecond-oriented in-process decision path; benchmark on target hardware | Paper-only adapter; idempotent client IDs |
| Supervisor plane | Groq structured decisions, alternative-data interpretation, experiment management | Asynchronous and rate-limited | Advisory only; cannot place orders or change risk limits |
| Research plane | Backtest, walk-forward, decay, zero-shot, stress, shortfall, latency benchmarks | Reproducible offline runs | Fold-local fitting and immutable manifests |

“Blazing fast” is treated as a measurable engineering requirement, not a claim. Optivio will report p50/p95/p99 decision latency, throughput, allocation counts, stale-event rejects, route-selection time, and risk-gate time on a named machine and dataset. Alpaca network round-trip time is reported separately from local decision latency because internet and broker latency cannot be controlled by Python code.

The initial implementation is Python-first for research and Alpaca integration. If benchmarks show the execution path misses its target, the hot loop can be moved behind a typed Rust/C++ service while preserving the same event and order-intent schemas. Quantfx and Ito provide useful reference patterns for this later boundary, but the first release must remain simple enough to audit.

Optivio’s zero-shot test means that a frozen model and frozen hyperparameters are applied to a later, unseen time block or unseen symbol set without re-fitting, tuning, scaler updates, or LLM access to future observations. The report must distinguish zero-shot cross-sectional generalization from ordinary out-of-sample temporal testing.
