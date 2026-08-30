from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from options_agent.execution.portfolio import PortfolioManager
from options_agent.models.optivio_hybrid import HybridOutput, OptivioHybridModel
from options_agent.models.regime_factor import ActiveRegimeClassifier


@dataclass(frozen=True)
class OptivioDecision:
    scores: np.ndarray
    expected_move: np.ndarray
    volatility: np.ndarray
    liquidity: np.ndarray
    regime: str
    exposure_scale: float
    target_weights: np.ndarray


class OptivioSignalPipeline:
    def __init__(self, model: OptivioHybridModel, regime_classifier: ActiveRegimeClassifier | None = None, portfolio: PortfolioManager | None = None):
        self.model = model
        self.regime_classifier = regime_classifier or ActiveRegimeClassifier()
        self.portfolio = portfolio or PortfolioManager()

    def decide(self, x: np.ndarray, trend: float, realized_volatility: float) -> OptivioDecision:
        output: HybridOutput = self.model.predict(x)
                                                                                               
        scores = output.direction.mean(axis=0) * output.liquidity.mean(axis=0)
        expected = output.expected_move.mean(axis=0)
        volatility = output.volatility.mean(axis=0)
        liquidity = output.liquidity.mean(axis=0)
        regime = self.regime_classifier.classify(trend, realized_volatility)
        scale = self.regime_classifier.exposure_scale(regime)
        weights = self.portfolio.target_weights(scores, volatility, scale)
        return OptivioDecision(scores, expected, volatility, liquidity, regime, scale, weights)
