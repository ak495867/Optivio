from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np


@dataclass(frozen=True, slots=True)
class SentimentObservation:
    source_id: str
    asset: str
    event_time: datetime
    available_at: datetime
    score: float
    confidence: float
    text_hash: str

    def usable_at(self, cutoff: datetime) -> bool:
        return self.available_at <= cutoff


class CausalSentimentAggregator:
    def __init__(self, minimum_confidence: float = .55):
        self.minimum_confidence = minimum_confidence

    def aggregate(self, observations: list[SentimentObservation], asset: str, cutoff: datetime) -> tuple[float, float]:
        usable = [o for o in observations if o.asset == asset and o.usable_at(cutoff) and o.confidence >= self.minimum_confidence]
        if not usable:
            return 0.0, 0.0
        weights = np.array([o.confidence for o in usable])
        scores = np.array([np.clip(o.score, -1, 1) for o in usable])
        return float(np.average(scores, weights=weights)), float(np.mean(weights))


@dataclass(frozen=True)
class RLAction:
    exposure_scale: float
    entropy: float
    reason: str


class ConstrainedPortfolioRL:
    """Contextual policy placeholder with hard safety bounds.

    A trained RL policy may propose a scale, but this layer clips it and applies
    regime/sentiment uncertainty penalties. It never changes Greeks or account limits.
    """
    def __init__(self, min_scale: float = 0.0, max_scale: float = 1.0):
        self.min_scale, self.max_scale = min_scale, max_scale

    def act(self, regime_scale: float, sentiment_score: float, sentiment_confidence: float, entropy: float = 0.0) -> RLAction:
        uncertainty_penalty = max(0.0, 1.0 - np.clip(sentiment_confidence, 0, 1))
        proposed = regime_scale * (1.0 + .15 * np.clip(sentiment_score, -1, 1)) * (1.0 - .5 * uncertainty_penalty)
        scale = float(np.clip(proposed, self.min_scale, self.max_scale))
        return RLAction(scale, float(max(0.0, entropy)), "bounded regime/sentiment policy")
