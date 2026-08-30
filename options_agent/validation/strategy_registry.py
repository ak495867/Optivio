from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True)
class StrategyCandidate:
    strategy_id: str
    parameters: dict[str, float]
    code_version: str
    created_at: datetime

    @property
    def manifest_hash(self) -> str:
        payload = json.dumps(
            {
                "strategy_id": self.strategy_id,
                "parameters": self.parameters,
                "code_version": self.code_version,
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class PromotionReport:
    candidate_hash: str
    train_score: float
    validation_score: float
    zero_shot_score: float | None
    approved: bool
    reason: str


class StrategyRegistry:
    def __init__(self):
        self._candidates: dict[str, StrategyCandidate] = {}
        self._promoted: dict[str, PromotionReport] = {}

    def register(self, candidate: StrategyCandidate) -> str:
        self._candidates[candidate.manifest_hash] = candidate
        return candidate.manifest_hash

    def promote(
        self,
        candidate_hash: str,
        evaluator: Callable[[StrategyCandidate, str], float],
        minimum_score: float,
        validation_score: float,
        zero_shot_score: float | None = None,
    ) -> PromotionReport:
        candidate = self._candidates[candidate_hash]
        train_score = float(evaluator(candidate, "train"))

        approved = (
            train_score >= minimum_score
            and validation_score >= minimum_score
            and (zero_shot_score is None or zero_shot_score >= minimum_score)
        )
        report = PromotionReport(
            candidate_hash,
            train_score,
            validation_score,
            zero_shot_score,
            approved,
            "passed gates" if approved else "failed score gate",
        )
        if approved:
            self._promoted[candidate_hash] = report
        return report

    def is_promoted(self, candidate_hash: str) -> bool:
        return candidate_hash in self._promoted

    def manifest(self, candidate_hash: str) -> dict:
        return asdict(self._candidates[candidate_hash])
