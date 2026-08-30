from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# External Hive model files must live in exactly this project-relative directory that
# the repository owns; an operator-supplied path outside it is never executed.
_HIVE_MODULE_DIR = Path(__file__).resolve().parent / "external" / "hive"

# Provenance marker: a file is only executed if it declares this opt-in header. This
# prevents an arbitrary .py dropped next to the model (or supplied via env/CLI) from
# being treated as trusted Hive code.
_PROVENANCE_MARKER = "# optivio-hive-model\n"


class HiveAdapter:
    """Adapter boundary for the Hive recurrent portfolio model; no data fetching occurs here."""

    def __init__(self, checkpoint: str | None = None):
        self.checkpoint = checkpoint
        self.model: Any = None

    def load(self, file_name: str):
        """Load a Hive model module from the trusted hive directory only.

        ``file_name`` is a bare filename resolved against the project-owned
        ``models/external/hive/`` directory. Absolute paths, path traversal, symlinks
        escaping the directory, and any file lacking the provenance marker are
        rejected before any code is executed — a module path from an unverified
        source is never imported (no arbitrary-code execution).
        """
        candidate = Path(file_name)
        if candidate.is_absolute() or candidate.name != file_name:
            raise ValueError(
                "Hive module path must be a bare filename within the trusted "
                f"external hive directory ({_HIVE_MODULE_DIR})"
            )
        # Resolve BEFORE the containment check so a symlink cannot point outside the
        # trusted directory. `_HIVE_MODULE_DIR` stays absolute; only the candidate is
        # resolved.
        trusted_root = _HIVE_MODULE_DIR.resolve()
        module_path = (trusted_root / candidate).resolve()
        if trusted_root not in module_path.parents and module_path != trusted_root:
            raise ValueError("Hive module path escapes the trusted hive directory")
        if module_path.suffix != ".py":
            raise ValueError("Hive module must be a .py file")
        if not module_path.exists():
            raise FileNotFoundError(f"no such Hive module: {module_path}")
        header = module_path.open("r", encoding="utf-8").readline()
        if header != _PROVENANCE_MARKER:
            raise ValueError(
                "Hive module missing opt-in provenance marker "
                f"({_PROVENANCE_MARKER.strip()})"
            )
        spec = importlib.util.spec_from_file_location("hive_external", str(module_path))
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
