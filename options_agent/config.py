"""Central environment-backed configuration for Optivio.

This module is the single source of truth for the ``OPTIVIO_*`` / ``ALPACA_*`` /
``GROQ_*`` knobs documented in ``.env.example``. Consumers import ``settings`` (a
module-level singleton) or call ``load_settings()`` for a fresh copy. Alias pairs
are canonicalized here so a renamed variable (e.g. ``ALPACA_DATA_FEED`` vs the once
used ``ALPACA_OPTIONS_FEED``) stays transparent to the rest of the codebase.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


def _load_dotenv(path: Path | str = ".env") -> dict[str, str]:
    """Load ``KEY=VALUE`` lines from a local dotfile without adding a dependency.

    Only loads variables that are NOT already set in the environment (so a real
    exported value always wins). Ignores blank lines, whole-line comments, and any
    line that is not a simple assignment. Returns the values loaded.
    """
    dotenv_path = Path(path)
    loaded: dict[str, str] = {}
    if not dotenv_path.exists():
        return loaded
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip("'").strip('"')
        if key in os.environ:
            continue
        os.environ[key] = value
        loaded[key] = value
    return loaded


def _num(
    source: Mapping[str, str], key: str, default: float, lo: float | None = None
) -> float:
    raw = source.get(key, "")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if lo is not None and value < lo:
        return default
    return value


def _int(source: Mapping[str, str], key: str, default: int, lo: int | None = None) -> int:
    raw = source.get(key, "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if lo is not None and value < lo:
        return default
    return value


def _str(source: Mapping[str, str], key: str, default: str) -> str:
    raw = source.get(key, "")
    return raw.strip() if raw else default


def _bool(source: Mapping[str, str], key: str, default: bool) -> bool:
    raw = source.get(key, "")
    if raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    mode: str = "paper"
    paper_endpoint: str = "https://paper-api.alpaca.markets"

    alpaca_key: str = ""
    alpaca_secret: str = ""
    alpaca_paper: bool = True
    data_feed: str = "indicative"

    groq_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_temperature: float = 0.0

    model_version: str = "optivio-hive-kronos-v0.1.0"

    # Risk limits (mirror OPTIVIO_MAX_* in .env.example)
    max_order_notional: float = 2500.0
    max_open_notional: float = 10000.0
    max_daily_loss_fraction: float = 0.02
    max_abs_delta: float = 1000.0
    max_abs_gamma: float = 500.0
    max_abs_theta: float = 5000.0
    max_abs_vega: float = 5000.0
    max_abs_rho: float = 5000.0

    # Walk-forward controls (OPTIVIO_PURGE_BARS / OPTIVIO_EMBARGO_BARS)
    purge_bars: int = 1
    embargo_bars: int = 1

    kill_switch: bool = False

    # Live-paper operation
    test_symbols: tuple[str, ...] = ()
    stream_seconds: float = 5.0


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build a Settings from an env mapping (defaults to ``os.environ``).

    Pass ``env`` explicitly in tests to avoid mutating the process environment.
    """
    if env is None:
        # Load a local .env if present so the documented template is operational.
        _load_dotenv()
    source = os.environ if env is None else env
    return Settings(
        mode=_str(source, "OPTIVIO_MODE", "paper"),
        alpaca_key=_str(source, "ALPACA_API_KEY", ""),
        alpaca_secret=_str(source, "ALPACA_SECRET_KEY", ""),
        alpaca_paper=_bool(source, "ALPACA_PAPER", True)
        or _bool(source, "OPTIVIO_PAPER_ONLY", False),
        data_feed=_str(source, "ALPACA_DATA_FEED", "indicative")
        if source.get("ALPACA_DATA_FEED")
        else _str(source, "ALPACA_OPTIONS_FEED", "indicative"),
        groq_key=_str(source, "GROQ_API_KEY", ""),
        groq_model=_str(source, "GROQ_MODEL", "llama-3.3-70b-versatile"),
        groq_temperature=_num(source, "GROQ_TEMPERATURE", 0.0),
        model_version=_str(
            source, "OPTIVIO_MODEL_VERSION", "optivio-hive-kronos-v0.1.0"
        ),
        max_order_notional=_num(
            source, "OPTIVIO_MAX_ORDER_NOTIONAL", 2500.0, lo=0.0
        ),
        max_open_notional=_num(source, "OPTIVIO_MAX_OPEN_NOTIONAL", 10000.0, lo=0.0),
        max_daily_loss_fraction=_num(
            source, "OPTIVIO_MAX_DAILY_LOSS_FRACTION", 0.02, lo=0.0
        ),
        max_abs_delta=_num(source, "OPTIVIO_MAX_ABS_DELTA", 1000.0, lo=0.0),
        max_abs_gamma=_num(source, "OPTIVIO_MAX_ABS_GAMMA", 500.0, lo=0.0),
        max_abs_theta=_num(source, "OPTIVIO_MAX_ABS_THETA", 5000.0, lo=0.0),
        max_abs_vega=_num(source, "OPTIVIO_MAX_ABS_VEGA", 5000.0, lo=0.0),
        max_abs_rho=_num(source, "OPTIVIO_MAX_ABS_RHO", 5000.0, lo=0.0),
        purge_bars=_int(source, "OPTIVIO_PURGE_BARS", 1, lo=0),
        embargo_bars=_int(source, "OPTIVIO_EMBARGO_BARS", 1, lo=0),
        kill_switch=_bool(source, "OPTIVIO_KILL_SWITCH", False),
        test_symbols=tuple(
            part.strip()
            for part in source.get("OPTIVIO_TEST_SYMBOLS", "").split(",")
            if part.strip()
        ),
        stream_seconds=_num(source, "OPTIVIO_STREAM_SECONDS", 5.0, lo=0.1),
    )


# Module-level singleton so consumers get one consistent view.
settings = load_settings()