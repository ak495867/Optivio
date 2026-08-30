# Optivio improvement roadmap

> **Quick take:** This roadmap is the honest upgrade list. It puts reliable data, realistic options mechanics, and recovery ahead of adding another shiny model.

> *“Before adding another signal, make the last signal measurable.”*

Optivio can become a stronger quantitative framework by treating research, execution, and operations as separate promotion domains. An autonomous alpha service should propose hypotheses from immutable market data, generate a complete feature/label/provenance manifest, search only within training folds, and submit candidates to a challenger registry. It should never deploy directly from a high backtest score.

| Priority | Capability | Required implementation | Promotion gate |
|---|---|---|---|
| P0 | Canonical market and options data | Contract master, quote/bar event store, revisions, corporate actions, calendars, surface snapshots, availability timestamps | Replay exactly reproduces every feature and decision |
| P0 | Multi-leg execution | Atomic intent, leg state machine, partial-fill hedging, cancel/replace, assignment/exercise/expiration, reconciliation | Unknown broker state blocks new exposure |
| P0 | Greeks and stress | IV solver, Greeks, scenario shocks, margin, liquidity-adjusted liquidation | Account, strategy, underlying, expiry, and surface-node limits pass |
| P0 | Live sentiment | Timestamped source ingestion, duplicate/event correction, text hash, entity mapping, availability lag, confidence calibration | Sentiment is used only after publication and source-quality checks |
| P1 | Alpha discovery | Research agents generate hypotheses, baselines, features, labels, backtests, and model cards | Purged walk-forward, zero-shot, decay, cost, stability, and falsification tests pass |
| P1 | Strategy deployment | Champion/challenger registry, signed artifacts, canary/shadow mode, rollback bundle, approval workflow | No direct autonomous promotion from research |
| P1 | RL portfolio supervision | Constrained contextual policy over exposure scale, with action clipping and hard deterministic risk boundary | Offline policy evaluation, drawdown, tail loss, turnover, regime stability, and safe fallback pass |
| P1 | Feedback learning | Hash-chained executions, delayed realized PnL, attribution by strategy/model/route, drift and calibration monitoring | Feedback cannot enter historical features and promotion requires a new frozen evaluation |
| P2 | Performance engineering | Profile p50/p95/p99; move only proven bottlenecks to C++/Rust; use persistent workers and zero-copy buffers | Lower p99 without changing decisions or risk outcomes |
| P2 | Hardware optimization | CPU affinity, NUMA awareness, preallocation, batching, kernel profiling, optional FPGA only after profiling | Reproducible benchmark on target hardware and safe degradation path |
| P2 | Additional languages | Shell for deployment/runbooks, Lisp for symbolic research DSL if justified, assembly only for measured kernels | Code review, portability, sanitizer/fuzzer coverage, and rollback path |

Live sentiment should be an input to a causal feature store, not an unrestricted portfolio controller. Groq can summarize or classify supplied evidence and an RL policy can propose a bounded exposure scale, but deterministic portfolio, Greeks, and account-risk controls must remain authoritative. Sentiment should also carry source-specific reliability, publication delay, contradiction handling, entity resolution, bot/spam filters, and an abstain state.

Low-level languages should be introduced selectively. C++ is suitable for quote normalization and route scoring after profiling. Rust is suitable for risk policy, state machines, and bridge validation. Shell is suitable for process supervision and deployment, not for tick-level decisions. Assembly should be limited to a benchmark-proven numerical kernel with a portable fallback. Lisp could provide a research experiment DSL, but adding it to the execution plane would increase operational complexity unless a clear symbolic-search requirement exists.

The long-term operating loop is: ingest immutable events; build point-in-time features; generate hypotheses; train and search only on training folds; validate sequentially; freeze artifacts; run shadow and canary paper stages; execute through deterministic risk and lifecycle controls; reconcile continuously; record execution/PnL outcomes; expose only delayed outcomes to monitoring and future model versions; and periodically re-run the entire promotion suite. This is how Optivio can improve without turning realized future performance into hidden leakage.
