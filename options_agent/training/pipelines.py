from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from options_agent.data.point_in_time import validate_point_in_time
from options_agent.models.alternative_strategies import GaussianHMM
from options_agent.validation.offline_rl import LoggedTransition


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    source: str
    row_count: int
    feature_columns: tuple[str, ...]
    cutoff_ns: int
    content_hash: str


@dataclass(frozen=True, slots=True)
class HMMTrainingResult:
    manifest: DatasetManifest
    model: GaussianHMM
    train_rows: int
    validation_rows: int


@dataclass(frozen=True, slots=True)
class OfflineRLTrainingResult:
    manifest: DatasetManifest
    transitions: tuple[LoggedTransition, ...]
    train_rows: int
    validation_rows: int


def _manifest(
    source: str,
    rows: Sequence[dict[str, Any]],
    features: tuple[str, ...],
    cutoff_ns: int,
) -> DatasetManifest:
    encoded = json.dumps(list(rows), sort_keys=True, default=str).encode()
    return DatasetManifest(
        source, len(rows), features, cutoff_ns, hashlib.sha256(encoded).hexdigest()
    )


def _split(
    rows: Sequence[dict[str, Any]], cutoff_ns: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train = [row for row in rows if int(row["available_at_ns"]) <= cutoff_ns]
    validation = [row for row in rows if int(row["available_at_ns"]) > cutoff_ns]
    if not train or not validation:
        raise ValueError(
            "training pipeline requires non-empty train and validation windows"
        )
    return train, validation


def _validate(rows: Sequence[dict[str, Any]]) -> None:
    frame = pd.DataFrame(rows)
    frame["asof"] = pd.to_datetime(frame["asof_ns"], unit="ns", utc=True)
    frame["available_at"] = pd.to_datetime(
        frame["available_at_ns"], unit="ns", utc=True
    )
    validate_point_in_time(frame)


def train_hmm(
    rows: Sequence[dict[str, Any]], feature: str, source: str, cutoff_ns: int
) -> HMMTrainingResult:
    _validate(rows)
    train, validation = _split(rows, cutoff_ns)
    values = np.asarray([float(row[feature]) for row in train], dtype=float)
    model = GaussianHMM(states=2, iterations=20).fit(values)
    return HMMTrainingResult(
        _manifest(source, rows, (feature,), cutoff_ns),
        model,
        len(train),
        len(validation),
    )


def build_offline_rl_dataset(
    rows: Sequence[dict[str, Any]],
    source: str,
    cutoff_ns: int,
    feature_columns: tuple[str, ...],
    policy: Callable[[dict[str, Any]], int],
    reward_horizon: int = 1,
) -> OfflineRLTrainingResult:
    """Build offline-RL transitions from point-in-time rows.

    Each transition is ``(state, action, reward, next_state, done)``. The reward is
    realized over the *next* ``reward_horizon`` bars, so ``next_state`` is the state
    observed after that horizon elapses — never the immediately-next row. The final
    ``reward_horizon`` rows have no observable outcome and are emitted as done
    transitions (self-loop) only so the episode boundary is explicit; offline-RL
    evaluators must drop them (see ``OfflineRLEvaluator``).
    """
    _validate(rows)
    if reward_horizon <= 0:
        raise ValueError("reward_horizon must be positive")
    train, validation = _split(rows, cutoff_ns)
    transitions: list[LoggedTransition] = []
    for index, row in enumerate(train):
        state = np.asarray(
            [float(row[column]) for column in feature_columns], dtype=float
        )
        outcome_index = index + reward_horizon
        if outcome_index < len(train):
            outcome = train[outcome_index]
            next_state = np.asarray(
                [float(outcome[column]) for column in feature_columns], dtype=float
            )
            done = False
        else:
            # No observable outcome within the window: self-loop, terminal.
            next_state = state
            done = True
        transitions.append(
            LoggedTransition(
                state,
                int(row["action"]),
                float(row["reward"]),
                next_state,
                done,
                float(row["behavior_probability"]),
                int(row["available_at_ns"]),
            )
        )
    return OfflineRLTrainingResult(
        _manifest(source, rows, feature_columns, cutoff_ns),
        tuple(transitions),
        len(train),
        len(validation),
    )


def save_manifest(manifest: DatasetManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "source": manifest.source,
                "row_count": manifest.row_count,
                "feature_columns": manifest.feature_columns,
                "cutoff_ns": manifest.cutoff_ns,
                "content_hash": manifest.content_hash,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
