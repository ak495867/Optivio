from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

REQUIRED_TIME_COLUMNS = {"asof", "available_at"}


def validate_point_in_time(df: pd.DataFrame) -> None:
    missing = REQUIRED_TIME_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"missing point-in-time columns: {sorted(missing)}")
    asof = pd.to_datetime(df["asof"], utc=True)
    available = pd.to_datetime(df["available_at"], utc=True)
    if (available > asof).any():
        bad = df.loc[available > asof].head(1).to_dict("records")
        raise ValueError(f"future availability detected: {bad}")
    if not asof.is_monotonic_increasing:
        raise ValueError("rows must be sorted by asof")


def assert_no_future_rows(df: pd.DataFrame, cutoff: datetime) -> None:
    cutoff = pd.Timestamp(cutoff, tz="UTC") if pd.Timestamp(cutoff).tz is None else pd.Timestamp(cutoff)
    asof = pd.to_datetime(df["asof"], utc=True)
    available = pd.to_datetime(df["available_at"], utc=True)
    if ((asof > cutoff) | (available > cutoff)).any():
        raise ValueError("dataset contains rows unavailable at the requested cutoff")


class ExpandingStandardizer:
    """A leakage-safe scaler: fit is called only on the current training fold."""

    def __init__(self, columns: list[str]) -> None:
        self.columns = columns
        self.mean_: pd.Series | None = None
        self.scale_: pd.Series | None = None

    def fit(self, train: pd.DataFrame) -> ExpandingStandardizer:
        self.mean_ = train[self.columns].mean()
        scale = train[self.columns].std(ddof=0).replace(0, 1.0)
        self.scale_ = scale.fillna(1.0)
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        if self.mean_ is None or self.scale_ is None:
            raise RuntimeError("standardizer must be fit on a training fold first")
        out = data.copy()
        out[self.columns] = (out[self.columns] - self.mean_) / self.scale_
        return out


@dataclass(frozen=True)
class Fold:
    fold: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    embargo_end: int


def purged_walk_forward(n: int, train_size: int, test_size: int, purge: int = 1, embargo: int = 1, step: int | None = None):
    if min(n, train_size, test_size) <= 0 or min(purge, embargo) < 0:
        raise ValueError("invalid walk-forward sizes")
    step = step or test_size
    start = 0
    fold = 0
    while start + train_size + purge + test_size <= n:
        train_end = start + train_size
        test_start = train_end + purge
        test_end = test_start + test_size
        yield Fold(fold, start, train_end, test_start, test_end, min(n, test_end + embargo))
        fold += 1
        start += step


def lagged_return(close: pd.Series, horizon: int = 1) -> pd.Series:
    if horizon <= 0:
        raise ValueError("horizon must be positive")
                                                                                                  
    return close.shift(-horizon) / close - 1.0
