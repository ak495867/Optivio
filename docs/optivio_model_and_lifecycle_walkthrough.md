# Optivio model walkthrough and production roadmap

> **Quick take:** This is the moving-parts tour: models on one side, multi-leg order state on the other, and risk controls in the middle. The casual rule is simple—if a leg gets lost, the package stops.

> *“A spread is one idea with several things that can go wrong.”*

## 1. Custom Hive-Kronos hybrid

The current custom model is intentionally an auditable research implementation rather than a claim that the original pretrained Kronos model has been retrained for options. It accepts tensors shaped as `[samples, assets, lookback, features]`. The feature set may contain OHLCV, realized volatility, returns, spreads, volume imbalance, implied-volatility observations, and surface features, provided each feature has an `asof` and `available_at` timestamp.

The first stage is `KronosStyleTokenizer`. It estimates coarse and fine quantization bounds only on the training fold, using robust percentiles, then maps each continuous feature to hierarchical integer levels. This mirrors Kronos’s coarse/fine token idea while avoiding any future-data access. In the current reference model, token statistics are concatenated to the original feature channels. A production PyTorch version should load a vetted Kronos tokenizer/model checkpoint, record its hash, and expose the hidden representation without allowing the checkpoint to update during zero-shot evaluation.

The second stage is `HiveStyleRingEncoder`. At every lookback step, each asset has a recurrent hidden state. Neighboring asset states are rolled around a fixed ring and averaged, creating a bounded cross-asset message. The input projection, recurrent projection, message projection, and a leaky update produce the next hidden state. This retains Hive’s central idea—local recurrent coupling and shared market dynamics—while making the asset graph explicit and replaceable by a sector/index/correlation graph in production.

The final stage is multi-head regression. The heads estimate directional score, expected move, volatility, and liquidity. The outputs are not orders. `OptivioSignalPipeline` aggregates the heads, classifies the current regime, scales exposure, and passes target weights to deterministic portfolio and risk controls. For options, the preferred production extension is to add heads for implied-volatility level, skew slope, term-structure slope, surface residual, expected spread cost, and probability of fill.

The model does not directly model a complete implied-volatility surface yet. The production surface representation should use a fixed moneyness/tenor grid and separate observed values from missing values. Features should include ATM IV, 25-delta risk reversal, butterfly, term slope, local surface curvature, realized-versus-implied spread, and quote quality. A surface encoder should be trained only on surfaces observable at the decision timestamp. The prediction target should be forward change in IV, forward change in skew, or option-level risk-adjusted return after costs—not the contemporaneous surface itself.

## 2. Arbitrage model

`SurfaceArbitrageModel` currently provides deterministic parity and vertical monotonicity checks. A production arbitrage engine should add put-call parity with dividends, box spreads, vertical spread bounds, calendar monotonicity, butterfly convexity, conversion/reversal relationships, and cross-venue discrepancies. Each candidate must pass quote freshness, contract identity, leg availability, borrow/funding assumptions, and executable-size checks. Apparent arbitrage is often stale data, wide spreads, fees, early exercise risk, or assignment risk; the engine must therefore report executable net edge after all costs and reject uncertain opportunities.

## 3. Hidden-Markov model

`GaussianHMM` is a compact diagonal Gaussian HMM over a scalar regime observation such as realized volatility, volatility-of-volatility, return trend, or surface displacement. It is fit on a training fold, then performs filtered—not smoothed—state inference at decision time. This distinction prevents future observations from changing past regime labels. Production versions should use multivariate emissions, calibrated transition persistence, missing-data handling, state-label stability, and a regime map based on out-of-sample risk rather than naming states from in-sample means.

## 4. Pairs trading model

`PairsTradingModel` fits a hedge ratio on the training fold, computes the residual spread and its training statistics, and emits entry/exit states from the current z-score. For options, pairs can be underlying pairs, ETF-versus-constituent relationships, volatility-index-versus-realized-volatility relationships, or same-underlying option surface points. The production version needs cointegration stability tests, borrow and financing costs, delta/vega neutralization, leg synchronization, and a timeout when the spread fails to mean-revert.

## 5. Parallel model execution

`ParallelSignalEngine` creates a persistent executor once, submits model inference concurrently, isolates individual model failures, and aggregates valid signals by confidence. It is designed so Groq, network calls, training, and disk I/O remain outside the hot path. Parallelism is not free: thread scheduling, cache contention, Python’s GIL, serialization, and queueing can make a single optimized model faster. Optivio should benchmark serial, persistent-thread, process, Rust, and C++ variants on the target machine. The correct design is the one with the lowest p99 end-to-end decision latency while maintaining determinism and risk correctness—not the one with the most concurrent models.

## 6. Multi-leg lifecycle code structure

A robust implementation should add the following modules:

| Module | Responsibility |
|---|---|
| `execution/multileg.py` | Leg and strategy state machines, legal transitions, partial fills, cancel/replace, expiration, and unknown-state blocking |
| `execution/order_intent.py` | Versioned intent schema, idempotency key, strategy ID, model version, risk snapshot ID, quote timestamp, and leg prices |
| `execution/alpaca_stream.py` | Broker order-update stream, reconnect/backoff, sequence handling, duplicate suppression, and message authentication |
| `execution/reconciler.py` | Compare local orders/fills/positions/cash/ buying power with Alpaca; block new orders on material drift |
| `execution/assignment.py` | Exercise, assignment, expiration, OCC event, and resulting underlying-position handling |
| `risk/greeks.py` | Black-Scholes/american approximation, implied-volatility solver, Greeks, stale/missing-IV policy, and scenario shocks |
| `risk/limits.py` | Portfolio and strategy Greeks limits, concentration, liquidity, margin, loss, and stress limits |
| `risk/pretrade.py` | Atomic validation of the complete multi-leg package before any leg is submitted |
| `execution/recovery.py` | Recovery after disconnect, uncertain acknowledgement, partial package fill, and process restart |
| `audit/event_log.py` | Append-only event journal linking market input, signal, risk decision, intent, broker response, and reconciliation |

The strategy state machine should distinguish `PLANNED`, `SUBMITTING`, `WORKING`, `PARTIALLY_FILLED`, `FILLED`, `CANCEL_PENDING`, `CANCELLED`, `REJECTED`, `EXPIRED`, and `UNKNOWN`. Any `UNKNOWN` state must block additional exposure until broker reconciliation resolves it. A multi-leg strategy is not considered complete merely because one leg filled; the package manager must track residual delta, vega, margin, and liquidation risk after every leg event.

## 7. Greeks risk limits

For each candidate package, calculate current portfolio Greeks plus proposed change. At minimum, enforce absolute and signed limits for delta, gamma, theta, vega, and rho; net and gross exposures by underlying; exposure by expiry and tenor; skew and surface-node concentration; scenario P&L under underlying shocks, volatility shocks, time decay, and correlation shocks; buying power and margin; and liquidity-adjusted liquidation cost.

Limits should be hierarchical. The global account limit is stricter than the strategy limit, which is stricter than the individual-underlying limit. A risk breach should reject the complete package atomically, not submit the safest legs and leave an unintended partial hedge. Limits must be versioned, signed, and changed through an approval workflow. Models and Groq must not modify them.

## 8. Production sequence

The practical build order is: canonical live data and contract master; complete options surface and Greeks engine; durable multi-leg state machine; broker stream and reconciliation; pre-trade risk; audit and recovery; model registry and frozen checkpoints; parallel benchmark harness; shadow mode; signal-only paper mode; constrained autonomous paper mode; and only then a formal review of whether the system is suitable for any broader use. Return optimization comes after costs, liquidity, latency, and risk controls are validated.
