from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from options_agent.data.point_in_time import (
    ExpandingStandardizer,
    purged_walk_forward,
    validate_point_in_time,
)


@dataclass(frozen=True)
class FoldMetrics:
    fold: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    train_score: float
    test_score: float


@dataclass(frozen=True)
class DecayMetrics:
    window: int
    mean_return: float
    sharpe: float
    hit_rate: float


def _sharpe(r: np.ndarray) -> float:
    return (
        float(np.sqrt(252) * r.mean() / r.std()) if len(r) > 1 and r.std() > 0 else 0.0
    )


def walk_forward_scores(
    df: pd.DataFrame,
    feature_columns: list[str],
    label_column: str,
    model_factory,
    train_size: int,
    test_size: int,
    purge: int | None = None,
    embargo: int | None = None,
) -> list[FoldMetrics]:
    if purge is None or embargo is None:
        from options_agent.config import settings

        purge = settings.purge_bars if purge is None else purge
        embargo = settings.embargo_bars if embargo is None else embargo
    validate_point_in_time(df)
    out: list[FoldMetrics] = []
    for fold in purged_walk_forward(len(df), train_size, test_size, purge, embargo):
        train, test = (
            df.iloc[fold.train_start : fold.train_end],
            df.iloc[fold.test_start : fold.test_end],
        )
        scaler = ExpandingStandardizer(feature_columns).fit(train)
        x_train, x_test = (
            scaler.transform(train)[feature_columns].to_numpy(),
            scaler.transform(test)[feature_columns].to_numpy(),
        )
        y_train, y_test = train[label_column].to_numpy(), test[label_column].to_numpy()
        model = model_factory().fit(x_train, y_train)
        train_pred, test_pred = model.predict(x_train), model.predict(x_test)
        out.append(
            FoldMetrics(
                fold.fold,
                fold.train_start,
                fold.train_end,
                fold.test_start,
                fold.test_end,
                _sharpe(y_train * np.sign(train_pred)),
                _sharpe(y_test * np.sign(test_pred)),
            )
        )
    return out


def decay_test(
    returns: pd.Series, windows: tuple[int, ...] = (5, 10, 20, 40, 80)
) -> list[DecayMetrics]:
    r = pd.Series(returns).dropna().astype(float).to_numpy()
    result = []
    for w in windows:
        sample = r[-w:] if len(r) >= w else r
        result.append(
            DecayMetrics(
                w,
                float(sample.mean()) if len(sample) else 0.0,
                _sharpe(sample) if len(sample) else 0.0,
                float((sample > 0).mean()) if len(sample) else 0.0,
            )
        )
    return result


def metrics_json(metrics: list[FoldMetrics] | list[DecayMetrics]) -> list[dict]:
    return [asdict(x) for x in metrics]
