from __future__ import annotations

import importlib.util
from typing import Any

import numpy as np
import pandas as pd


class HiveAdapter:
    """Adapter boundary for the Hive recurrent portfolio model; no data fetching occurs here."""

    def __init__(self, checkpoint: str | None = None):
        self.checkpoint = checkpoint
        self.model: Any = None

    def load(self, module_path: str):
        spec = importlib.util.spec_from_file_location("hive_external", module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load Hive module: {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.model = module
        return self

    def transform_features(self, bars: pd.DataFrame) -> np.ndarray:
        required = {"symbol", "asof", "open", "high", "low", "close"}
        if not required.issubset(bars.columns):
            raise ValueError(
                f"bars missing columns: {sorted(required - set(bars.columns))}"
            )

        out = bars.sort_values(["symbol", "asof"]).copy()
        out["log_return"] = out.groupby("symbol")["close"].transform(
            lambda s: np.log(s).diff()
        )
        out["rsi10"] = out.groupby("symbol")["log_return"].transform(
            lambda s: s.rolling(10, min_periods=10).mean()
        )
        return out[["log_return", "rsi10"]].fillna(0).to_numpy()


class KronosAdapter:
    """Lazy adapter boundary for Kronos OHLCV forecasting."""

    def __init__(self, model_name: str = "NeoQuasar/Kronos-small"):
        self.model_name = model_name
        self.predictor: Any = None

    def load(self):
        try:
            from Kronos.model import Kronos, KronosPredictor, KronosTokenizer
        except ImportError as exc:
            raise ImportError(
                "make the Kronos repository available or install its dependencies"
            ) from exc
        tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
        model = Kronos.from_pretrained(self.model_name)
        self.predictor = KronosPredictor(model, tokenizer, max_context=512)
        return self

    def forecast(self, bars: pd.DataFrame, future_timestamps: pd.Series, pred_len: int):
        if self.predictor is None:
            self.load()
        x = bars[["open", "high", "low", "close", "volume", "amount"]].copy()
        return self.predictor.predict(
            df=x,
            x_timestamp=bars["asof"],
            y_timestamp=future_timestamps,
            pred_len=pred_len,
            T=1.0,
            top_p=0.9,
            sample_count=1,
        )
