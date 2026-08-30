from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np


@dataclass(frozen=True, slots=True)
class OnlineOutcome:
    policy_version: str
    decision_time: datetime
    available_at: datetime
    reward: float
    action: float
    allowed: bool = True


@dataclass(frozen=True, slots=True)
class LiveGuardrails:
    max_drawdown: float = 0.05
    max_daily_loss: float = 0.02
    max_action_abs: float = 1.0
    min_observations: int = 100
    min_advantage: float = 0.005


@dataclass
class PolicyRuntime:
    version: str
    action_fn: Callable[[np.ndarray], float]
    shadow: bool = True
    active: bool = False
    outcomes: list[OnlineOutcome] = field(default_factory=list)

    def record(self, outcome: OnlineOutcome) -> None:
        if outcome.policy_version != self.version:
            raise ValueError("outcome version mismatch")
        self.outcomes.append(outcome)


@dataclass(frozen=True, slots=True)
class OnlinePromotionDecision:
    approved: bool
    reason: str
    active_version: str
    candidate_version: str
    candidate_return: float
    active_return: float
    candidate_drawdown: float


class OnlineChampionChallenger:
    """Shadow-first online promotion with hard live safety gates and rollback."""

    def __init__(
        self, champion: PolicyRuntime, guardrails: LiveGuardrails | None = None
    ):
        champion.active, champion.shadow = True, False
        self.champion = champion
        self.challenger: PolicyRuntime | None = None
        self.guardrails = guardrails or LiveGuardrails()
        self.halted = False

    def load_challenger(self, candidate: PolicyRuntime) -> None:
        if candidate.version == self.champion.version:
            raise ValueError("challenger must have a new version")
        candidate.shadow, candidate.active = True, False
        self.challenger = candidate

    def propose_action(self, state: np.ndarray, policy: PolicyRuntime) -> float:
        if self.halted:
            return 0.0
        action = float(policy.action_fn(state))
        return float(
            np.clip(
                action, -self.guardrails.max_action_abs, self.guardrails.max_action_abs
            )
        )

    @staticmethod
    def _metrics(outcomes: list[OnlineOutcome]) -> tuple[float, float]:
        rewards = np.asarray([o.reward for o in outcomes], dtype=float)
        if rewards.size == 0:
            return 0.0, -1.0
        curve = np.cumprod(1 + rewards)
        return float(curve[-1] - 1), float(
            np.min(curve / np.maximum.accumulate(curve) - 1)
        )

    def record_outcome(self, outcome: OnlineOutcome) -> None:
        if outcome.available_at < outcome.decision_time:
            raise ValueError("outcome cannot be available before decision")
        target = (
            self.champion
            if outcome.policy_version == self.champion.version
            else self.challenger
        )
        if target is None:
            raise ValueError("unknown policy version")
        target.record(outcome)
        _, drawdown = self._metrics(target.outcomes)
        if abs(drawdown) > self.guardrails.max_drawdown:
            if target is self.challenger:
                self.challenger = None
            else:
                self.halted = True

    def evaluate_and_promote(self) -> OnlinePromotionDecision:
        if self.challenger is None:
            raise RuntimeError("no challenger loaded")
        if len(self.challenger.outcomes) < self.guardrails.min_observations:
            return OnlinePromotionDecision(
                False,
                "insufficient challenger observations",
                self.champion.version,
                self.challenger.version,
                0,
                0,
                -1,
            )
        candidate_return, candidate_dd = self._metrics(self.challenger.outcomes)
        active_return, _ = self._metrics(self.champion.outcomes)
        safe = (
            abs(candidate_dd) <= self.guardrails.max_drawdown
            and candidate_return - active_return >= self.guardrails.min_advantage
        )
        if safe:
            old = self.champion
            self.champion = self.challenger
            self.champion.active, self.champion.shadow = True, False
            self.challenger = old
            self.challenger.active, self.challenger.shadow = False, True
        return OnlinePromotionDecision(
            safe,
            "promoted" if safe else "failed live gates",
            self.champion.version,
            self.challenger.version,
            candidate_return,
            active_return,
            candidate_dd,
        )

    def rollback(self) -> None:
        if self.challenger is None:
            return
        self.champion.active, self.champion.shadow = False, True
        self.challenger.active, self.challenger.shadow = True, False
        self.champion, self.challenger = self.challenger, self.champion
