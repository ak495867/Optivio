# Optivio recovery, Greeks, and offline RL safeguards

> **Quick take:** This note covers what happens when the connection drops, the quote looks impossible, or an RL challenger becomes risky. In all three cases, Optivio should prefer a clear stop over a clever guess.

> *“When the state is uncertain, reduce exposure before reducing standards.”*

## Alpaca stream recovery

`AlpacaStreamSupervisor` constructs a fresh stream through an injected factory, reloads credentials through an injected provider, replays subscriptions, and applies exponential backoff after permission, connection, timeout, or operating-system failures. It tracks authentication failures, reconnect count, last error, message count, and terminal halted state. The design follows Alpaca’s documented option-stream SDK boundary, where the option stream exposes quote/trade subscriptions and handles MsgPack internally [1] [2].

The adapter must be extended in deployment with credential rotation, server error classification, subscription snapshots, sequence-gap recovery, persisted last-event state, jittered backoff, health probes, and an operator kill switch. A reconnect is not a reconciliation: after every reconnect, Optivio must compare local orders and positions with the broker before permitting new exposure.

## Greeks engine

`risk/greeks_engine.py` implements European Black-Scholes pricing, a bracketed bisection implied-volatility solver, no-arbitrage price bounds, finite-input checks, maximum-volatility bounds, iteration limits, and quote failure states. It returns scaled Greeks for the contract multiplier. The solver returns `None` rather than inventing volatility when an option price is impossible, a quote is invalid, or a root cannot be bracketed.

Production expansion should add dividend curves, American early-exercise handling, discrete dividends, robust hybrid Newton/bisection solving, stale-quote and crossed-market rejection, surface smoothing with no-arbitrage constraints, and scenario Greeks. Greeks should be recomputed on every material quote update and aggregated by account, strategy, underlying, expiry, tenor, and surface node.

## Offline RL champion-challenger

`validation/rl_champion.py` evaluates a champion and challenger using the logged-transition evaluator, action-support checks, capped importance sampling, weighted importance sampling, realized return, maximum drawdown, worst subperiod return, and turnover. The challenger is promoted only when support is sufficient, drawdown and tail-loss limits pass, turnover remains bounded, and the return advantage exceeds the configured margin.

The policy should be trained offline only. The live system should use a frozen champion, a shadow challenger, deterministic action clipping, a fallback policy, and a kill switch. Promotion evidence should include confidence intervals, behavior-policy coverage, sensitivity to reward definitions, regime-by-regime results, stress scenarios, and a new untouched zero-shot evaluation. Realized PnL is delayed feedback and must not be used to tune the same historical window on which a policy is judged.

## References

[1]: https://docs.alpaca.markets/us/docs/real-time-option-data "Alpaca Real-Time Option Data"
[2]: https://alpaca.markets/sdks/python/api_reference/data/option/live.html "Alpaca-py OptionDataStream"
