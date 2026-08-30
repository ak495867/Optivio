from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class LoggedTransition:
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool
    behavior_probability: float
    available_at: int


@dataclass(frozen=True, slots=True)
class OfflineRLReport:
    observations: int
    support_rate: float
    importance_sampling: float
    weighted_importance_sampling: float
    reward_mean: float
    reward_std: float
    max_weight: float
    safe: bool
    reason: str


class OfflineRLEvaluator:
    """Offline policy evaluation with no environment interaction or future labels."""

    def __init__(
        self, max_importance_weight: float = 20.0, min_support_rate: float = 0.95
    ):
        self.max_importance_weight, self.min_support_rate = (
            max_importance_weight,
            min_support_rate,
        )

    def evaluate(
        self,
        transitions: Sequence[LoggedTransition],
        target_policy: Callable[[np.ndarray], int],
        decision_cutoff: int | None = None,
    ) -> OfflineRLReport:
        usable = [
            t
            for t in transitions
            if decision_cutoff is None or t.available_at <= decision_cutoff
        ]
        if not usable:
            raise ValueError("no transitions available before cutoff")
        weights: list[float] = []
        rewards: list[float] = []
        supported = 0
        for t in usable:
            action = int(target_policy(t.state))
            if action == t.action and t.behavior_probability > 0:
                supported += 1
                weights.append(
                    min(self.max_importance_weight, 1.0 / t.behavior_probability)
                )
                rewards.append(float(t.reward))
            else:
                weights.append(0.0)
                rewards.append(0.0)
        support_rate = supported / len(usable)
        w = np.asarray(weights, dtype=float)
        r = np.asarray(rewards, dtype=float)
        ips = float(np.mean(w * r))
        wis = float(np.sum(w * r) / np.sum(w)) if np.sum(w) > 0 else 0.0
        safe = support_rate >= self.min_support_rate and np.isfinite(wis)
        reason = (
            "support and weights acceptable"
            if safe
            else "insufficient logged-action support"
        )
        return OfflineRLReport(
            len(usable),
            float(support_rate),
            ips,
            wis,
            float(r.mean()),
            float(r.std()),
            float(w.max(initial=0.0)),
            safe,
            reason,
        )
