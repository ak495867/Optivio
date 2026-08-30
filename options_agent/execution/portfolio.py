from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class PortfolioLimits:
    max_single_weight: float = 0.20
    max_gross_weight: float = 1.0
    target_annual_vol: float = 0.15
    min_cash_weight: float = 0.10


class PortfolioManager:
    def __init__(self, limits: PortfolioLimits | None = None):
        self.limits = limits or PortfolioLimits()

    def target_weights(self, scores: np.ndarray, vol: np.ndarray, regime_scale: float = 1.0) -> np.ndarray:
        scores, vol = np.asarray(scores, dtype=float), np.maximum(np.asarray(vol, dtype=float), 1e-6)
        if scores.shape != vol.shape:
            raise ValueError("scores and vol must have equal shape")
        raw = scores / vol
        raw[np.abs(raw) < 1e-12] = 0.0
        gross = np.abs(raw).sum()
        w = raw / gross if gross else np.zeros_like(raw)
        w *= min(1.0, self.limits.target_annual_vol / max(float(np.mean(vol) * np.sqrt(252)), 1e-9))
        w *= max(0.0, min(1.0, regime_scale))
        w = np.clip(w, -self.limits.max_single_weight, self.limits.max_single_weight)
        if np.abs(w).sum() > self.limits.max_gross_weight:
            w *= self.limits.max_gross_weight / np.abs(w).sum()
        return w

    def cash_weight(self, weights: np.ndarray) -> float:
        return max(self.limits.min_cash_weight, 1.0 - float(np.abs(weights).sum()))
