# Optivio production-readiness specification

> **Quick take:** Use this as the go/no-go list for autonomous paper operation. Optivio earns more autonomy one tested stage at a time; it does not jump from a notebook straight to an always-on process.

> *“Production is a behavior under failure, not a folder with more files.”*

Optivio should be treated as a **distributed quantitative research and execution system**, not as a single trading script. It can operate autonomously in the Alpaca paper market only after every safety gate is deterministic, observable, replayable, and independently tested. Autonomous paper trading is the first operational target; real-money trading is outside the current scope and must never be enabled by configuration alone.

## Required production components

| Domain | Required capability | Completion gate |
|---|---|---|
| Market data | Live quote/bar ingestion, reconnects, sequence checks, stale-data detection, market calendar, contract lifecycle and corporate-action handling | Replayed outages and malformed events produce safe rejects and no unbounded queue growth |
| Canonical data | Immutable raw-event store, schema versions, source IDs, hashes, `asof`, `available_at`, revision history | A dataset can be reconstructed exactly from its manifest |
| Research | Contract-level options history, realistic spread/fill/latency/assignment models, purged walk-forward, zero-shot, decay and stress suites | No result is published without provenance and a passing leakage audit |
| Models | Frozen model registry, feature manifests, model cards, regime and calibration monitoring, challenger/shadow models | Promotion requires reproducible metrics, stability, and approval evidence |
| Portfolio | Positions, Greeks, scenario exposures, buying power, concentration, liquidity, margin, assignment and expiration controls | Every order is explainable and traceable to a portfolio/risk snapshot |
| Execution | Smart routing, idempotent intents, quote freshness, limit-price bands, partial-fill handling, cancel/replace policy, rate limits | Deterministic state machine handles rejects, disconnects, duplicates, and uncertain order status |
| Safety | Kill switch, circuit breakers, daily loss limits, max notional, max order rate, human approval for policy changes | Safety controls remain active if Groq, models, data, or broker connectivity fail |
| Reconciliation | Broker account, orders, fills, positions, cash, buying power, open interest and corporate actions | Reconciliation is continuous and blocks new orders on material divergence |
| Operations | Metrics, structured logs, traces, alerts, dashboards, incident runbooks, backups, restore drills | An operator can explain every order and recover from a failed process |
| Security | Secret manager, least privilege, dependency/SBOM scanning, signed artifacts, network egress policy, tamper-evident audit log | CI blocks leaked secrets, vulnerable dependencies, unsigned release artifacts, and unsafe code |

## Autonomous paper-trading stages

Optivio should progress through shadow mode, then signal-only mode, then paper execution with orders disabled by default, then constrained autonomous paper trading with tiny notional and strict circuit breakers. Each stage must run for a pre-declared observation window and meet thresholds for data completeness, stale-event rate, reconciliation drift, order rejects, latency, drawdown, and incident count. A stage cannot advance based on returns alone.

The Groq supervisor remains asynchronous. It may classify supplied alternative data, summarize regime evidence, and recommend experiments. It may not change limits, promote models, select a live endpoint, or submit/cancel orders. Rust/C++/OCaml services enforce the deterministic contract at the boundary.

## Cross-language allocation

Rust owns the policy and risk-gate library because it provides strong memory safety and explicit error handling. C++ owns the bounded hot-path quote normalization and route scoring where profiling demonstrates that Python is insufficient. OCaml owns a small declarative policy-validation layer for configuration and promotion rules. Python remains the research/orchestration layer. These components communicate through versioned JSON/MessagePack or a local IPC protocol; no language may silently reinterpret a risk field.

## Performance requirements

Performance must be benchmarked on the actual deployment host. Report p50/p95/p99 local decision latency, route-selection latency, serialization latency, event throughput, queue depth, allocation count, stale-event rejects, and broker round-trip latency separately. “Blazing fast” is not a fixed number until the user specifies the host, frequency, and acceptable risk. The hot path must be bounded, preallocated where practical, free of LLM/network calls, and protected against backpressure.

## Items still needed for a full production-grade system

The current repository is a strong safety-oriented foundation, not yet a full production system. It still needs live streaming ingestion, durable storage, options Greeks and scenario engine, multi-leg order state machines, assignment/exercise/expiration processing, broker reconciliation, corporate actions, market calendars, model registry and promotion workflow, secrets management, deployment manifests, observability, alerting, disaster recovery, load testing, chaos testing, security review, licensing review, and a staged operational runbook. Most importantly, it needs a real timestamped options dataset and live paper-market soak test before any performance conclusion is trusted.
