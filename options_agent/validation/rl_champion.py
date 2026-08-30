from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from options_agent.validation.offline_rl import LoggedTransition, OfflineRLEvaluator


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    name: str
    report: object
    cumulative_return: float
    max_drawdown: float
    worst_period_return: float
    turnover: float


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    approved: bool
    reason: str
    champion: str
    challenger: str
    challenger_advantage: float


class ConservativeChampionChallenger:
    def __init__(self, min_support: float = .95, max_drawdown: float = .10, max_worst_period_loss: float = .05, max_turnover: float = 2.0, min_advantage: float = .01):
        self.min_support = min_support
        self.max_drawdown = max_drawdown
        self.max_worst_period_loss = max_worst_period_loss
        self.max_turnover = max_turnover
        self.min_advantage = min_advantage

    @staticmethod
    def _metrics(rewards: np.ndarray, actions: np.ndarray) -> tuple[float, float, float, float]:
        curve = np.cumprod(1 + rewards)
        drawdown = float(np.min(curve / np.maximum.accumulate(curve) - 1))
        periods = np.array_split(rewards, max(1, min(20, len(rewards))))
        worst = float(min((np.prod(1 + p) - 1 for p in periods), default=0.0))
        turnover = float(np.abs(np.diff(actions)).mean()) if len(actions) > 1 else 0.0
        return float(curve[-1] - 1), drawdown, worst, turnover

    def evaluate(self, name: str, transitions: Sequence[LoggedTransition], policy: Callable[[np.ndarray], int], cutoff: int | None = None) -> PolicyEvaluation:
        evaluator = OfflineRLEvaluator(min_support_rate=self.min_support)
        report = evaluator.evaluate(transitions, policy, cutoff)
        usable = [t for t in transitions if cutoff is None or t.available_at <= cutoff]
        rewards, actions = [], []
        for transition in usable:
            if int(policy(transition.state)) == transition.action:
                rewards.append(float(transition.reward)); actions.append(int(transition.action))
        ret, dd, worst, turnover = self._metrics(np.asarray(rewards, dtype=float), np.asarray(actions, dtype=float)) if rewards else (0.0, -1.0, -1.0, float("inf"))
        return PolicyEvaluation(name, report, ret, dd, worst, turnover)

    def decide(self, champion: PolicyEvaluation, challenger: PolicyEvaluation) -> PromotionDecision:
        c, n = champion, challenger
        advantage = n.cumulative_return - c.cumulative_return
        safe = bool(getattr(n.report, "safe", False)) and abs(n.max_drawdown) <= self.max_drawdown and n.worst_period_return >= -self.max_worst_period_loss and n.turnover <= self.max_turnover
        approved = safe and advantage >= self.min_advantage
        reason = "challenger passed support, risk, turnover, and advantage gates" if approved else "challenger failed conservative promotion gates"
        return PromotionDecision(approved, reason, c.name, n.name, float(advantage))
