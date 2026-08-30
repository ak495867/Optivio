from __future__ import annotations

import numpy as np


def smooth_iv_surface(log_moneyness: np.ndarray, maturities: np.ndarray, iv: np.ndarray, bandwidth_moneyness: float = .15, bandwidth_maturity: float = .20, min_observations: int = 3) -> np.ndarray:
    """Smooth one timestamp’s IV surface; no temporal fill or future data is used."""
    k, t, values = np.asarray(log_moneyness, dtype=float), np.asarray(maturities, dtype=float), np.asarray(iv, dtype=float)
    if k.shape != t.shape or k.shape != values.shape or k.ndim != 1:
        raise ValueError("surface vectors must be aligned and one-dimensional")
    valid = np.isfinite(k) & np.isfinite(t) & np.isfinite(values) & (values > 0) & (t > 0)
    if valid.sum() < min_observations:
        return np.full_like(values, np.nan)
    result = np.full_like(values, np.nan)
    for i in range(len(values)):
        if not valid[i]:
            continue
        weights = np.exp(-.5 * ((k[valid] - k[i]) / max(bandwidth_moneyness, 1e-8)) ** 2 - .5 * ((np.sqrt(t[valid]) - np.sqrt(t[i])) / max(bandwidth_maturity, 1e-8)) ** 2)
        if np.sum(weights) <= 0:
            continue
        result[i] = float(np.clip(np.sum(weights * values[valid]) / np.sum(weights), 1e-6, 8.0))
    return result
