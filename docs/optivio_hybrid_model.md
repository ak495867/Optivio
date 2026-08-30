# Optivio hybrid model

> **Quick take:** This is the friendly tour of the custom Hive-Kronos model. We start with what the model is trying to hear in the market, then show how the tokenization, recurrence, and options heads turn those echoes into measurable outputs.

> *“Volatility has a shape, not just a number.”*

Optivio combines two complementary ideas from the studied repositories without copying their data pipelines. Kronos contributes hierarchical quantization of multi-dimensional OHLCV sequences and temporal representation learning. Hive contributes small recurrent state, local ring-coupled interactions, and cross-asset aggregation. The custom implementation is `options_agent/models/optivio_hybrid.py`.

## Model flow

| Stage | Optivio implementation | Options-specific purpose |
|---|---|---|
| Input | Causal windows of OHLCV, derived factors, and market microstructure features | Avoid future bars and preserve contract/quote timing |
| Tokenization | Frozen coarse/fine quantization bounds fitted on the training fold | Capture scale-robust price, volume, range, and volatility states |
| Temporal state | Recurrent hidden state across the lookback sequence | Summarize evolving market conditions without using future labels |
| Cross-asset state | Ring-coupled message passing between assets/underlyings | Model shared volatility, sector, index, and liquidity regimes |
| Heads | Direction, expected move, volatility, and liquidity | Support signal construction, sizing, contract selection, and risk controls |
| Execution interface | Signal is passed to deterministic portfolio/risk/router layers | The model cannot submit or modify orders |

The reference implementation is NumPy-based so it can run in the existing research environment without forcing heavyweight model dependencies. A production training variant may replace the encoder with a PyTorch implementation that directly loads a vetted Kronos checkpoint and a vetted Hive checkpoint, but it must preserve the same fold-local tokenizer, feature manifest, output schema, and audit metadata.

## Evolutionary optimization

`options_agent/validation/evolutionary.py` implements a bounded genetic/evolutionary optimizer. It uses seeded initialization, tournament selection, elitism, uniform crossover, bounded mutation, and a multi-objective risk-adjusted objective. Candidate genomes should encode strategy parameters such as DTE range, spread tolerance, volatility target, regime exposure scale, hedge ratio, and signal thresholds.

The optimizer accepts only a training-fold objective. It does not receive validation or zero-shot observations. After selection, the genome is frozen and evaluated exactly once on the untouched validation/zero-shot block. Fitness should penalize drawdown, turnover, illiquidity, rejected orders, latency, and unstable regime performance; maximizing return alone is prohibited.

## What “complete” still requires

This model is a complete research component, not proof that a profitable autonomous trader exists. A production Optivio deployment still requires contract-level historical options data, options Greeks and scenario calculations, multi-leg lifecycle handling, assignment/exercise/expiration processing, real-time data quality checks, broker reconciliation, persistent model registry, checkpoint signing, model drift monitoring, and a long live-paper soak test. No model should be promoted solely because an evolutionary search found a high backtest score.
