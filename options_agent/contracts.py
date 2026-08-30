from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunMode(str, Enum):
    BACKTEST = "backtest"
    PAPER = "paper"


class OptionRight(str, Enum):
    CALL = "call"
    PUT = "put"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class FeatureRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str
    asof: datetime
    available_at: datetime
    values: dict[str, float]
    source_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def availability_is_not_future(self) -> FeatureRow:
        if self.available_at > self.asof:
            raise ValueError("available_at cannot be later than asof")
        return self


class OptionContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str
    underlying: str
    expiration: datetime
    strike: float = Field(gt=0)
    right: OptionRight
    multiplier: int = Field(default=100, gt=0)


class Quote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract: OptionContract
    asof: datetime
    available_at: datetime
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    bid_size: int = Field(ge=1)
    ask_size: int = Field(ge=1)

    @model_validator(mode="after")
    def quote_is_valid(self) -> Quote:
        if self.available_at > self.asof:
            raise ValueError("quote available_at cannot be later than asof")
        if self.ask < self.bid:
            raise ValueError("ask cannot be below bid")
        return self


class OrderIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal[RunMode.PAPER] = RunMode.PAPER
    client_order_id: str
    contract: OptionContract
    side: Side
    quantity: int = Field(gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    time_in_force: Literal["day", "gtc"] = "day"
    rationale: str
    model_version: str
    signal_asof: datetime
    created_at: datetime


class RiskSnapshot(BaseModel):
    equity: float = Field(ge=0)
    buying_power: float = Field(ge=0)
    open_option_notional: float = Field(ge=0)
    daily_loss: float = Field(ge=0)
    kill_switch: bool = False


class Signal(BaseModel):
    symbol: str
    asof: datetime
    score: float
    confidence: float = Field(ge=0, le=1)
    expected_move: float
    rationale: str
    features: dict[str, float] = Field(default_factory=dict)
