from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from options_agent.contracts import OptionRight


@dataclass(frozen=True, slots=True)
class GreeksResult:
    implied_volatility: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    rho: float | None
    valid: bool
    reason: str
    asof: datetime


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _d1d2(
    spot: float, strike: float, rate: float, carry: float, tau: float, vol: float
) -> tuple[float, float]:
    d1 = (math.log(spot / strike) + (rate - carry + 0.5 * vol * vol) * tau) / (
        vol * math.sqrt(tau)
    )
    return d1, d1 - vol * math.sqrt(tau)


def theoretical_price(
    spot: float,
    strike: float,
    rate: float,
    carry: float,
    tau: float,
    vol: float,
    right: OptionRight,
) -> float:
    d1, d2 = _d1d2(spot, strike, rate, carry, tau, vol)
    sign = 1.0 if right == OptionRight.CALL else -1.0
    return sign * (
        spot * math.exp(-carry * tau) * _norm_cdf(sign * d1)
        - strike * math.exp(-rate * tau) * _norm_cdf(sign * d2)
    )


def implied_volatility(
    price: float,
    spot: float,
    strike: float,
    rate: float,
    carry: float,
    tau: float,
    right: OptionRight,
    min_vol: float = 1e-6,
    max_vol: float = 8.0,
    iterations: int = 100,
) -> float | None:
    if (
        not all(math.isfinite(x) for x in (price, spot, strike, rate, carry, tau))
        or price <= 0
        or spot <= 0
        or strike <= 0
        or tau <= 0
    ):
        return None
    discount_spot, discount_strike = spot * math.exp(-carry * tau), strike * math.exp(
        -rate * tau
    )
    sign = 1.0 if right == OptionRight.CALL else -1.0
    lower = max(0.0, sign * (discount_spot - discount_strike))
    upper = discount_spot if right == OptionRight.CALL else discount_strike
    if price < lower - 1e-8 or price > upper + 1e-8:
        return None
    lo, hi = min_vol, max_vol
    flo, fhi = (
        theoretical_price(spot, strike, rate, carry, tau, lo, right) - price,
        theoretical_price(spot, strike, rate, carry, tau, hi, right) - price,
    )
    if flo * fhi > 0:
        return None
    for _ in range(iterations):
        mid = (lo + hi) * 0.5
        fmid = theoretical_price(spot, strike, rate, carry, tau, mid, right) - price
        if abs(fmid) < 1e-8:
            return mid
        if flo * fmid <= 0:
            hi, fhi = mid, fmid
        else:
            lo, flo = mid, fmid
    return (lo + hi) * 0.5


def calculate_greeks(
    price: float,
    spot: float,
    strike: float,
    rate: float,
    carry: float,
    tau: float,
    right: OptionRight,
    asof: datetime,
    multiplier: int = 100,
) -> GreeksResult:
    vol = implied_volatility(price, spot, strike, rate, carry, tau, right)
    if vol is None:
        return GreeksResult(
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            "invalid quote or no-bracket implied volatility",
            asof,
        )
    d1, d2 = _d1d2(spot, strike, rate, carry, tau, vol)
    sign = 1.0 if right == OptionRight.CALL else -1.0
    discount_spot, discount_strike = math.exp(-carry * tau), math.exp(-rate * tau)
    delta = sign * discount_spot * _norm_cdf(sign * d1)
    gamma = discount_spot * _norm_pdf(d1) / (spot * vol * math.sqrt(tau))
    vega = spot * discount_spot * _norm_pdf(d1) * math.sqrt(tau)
    theta = -(
        spot * discount_spot * _norm_pdf(d1) * vol / (2 * math.sqrt(tau))
    ) - sign * (
        rate * strike * discount_strike * _norm_cdf(sign * d2)
        - carry * spot * discount_spot * _norm_cdf(sign * d1)
    )
    rho = sign * tau * strike * discount_strike * _norm_cdf(sign * d2)
    scale = float(multiplier)
    return GreeksResult(
        vol,
        delta * scale,
        gamma * scale,
        theta * scale,
        vega * scale,
        rho * scale,
        True,
        "ok",
        asof,
    )
