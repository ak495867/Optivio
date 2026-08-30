from __future__ import annotations

import math

from options_agent.contracts import OptionRight


def american_price_binomial(
    spot: float,
    strike: float,
    rate: float,
    carry: float,
    tau: float,
    vol: float,
    right: OptionRight,
    steps: int = 100,
) -> float | None:
    if (
        min(spot, strike, tau, vol) <= 0
        or steps < 2
        or steps > 2000
        or not all(math.isfinite(x) for x in (spot, strike, rate, carry, tau, vol))
    ):
        return None
    dt = tau / steps
    up = math.exp(vol * math.sqrt(dt))
    down = 1 / up
    disc = math.exp(-rate * dt)
    p = (math.exp((rate - carry) * dt) - down) / (up - down)
    if not 0 < p < 1:
        return None
    values = []
    for j in range(steps + 1):
        s = spot * up**j * down ** (steps - j)
        intrinsic = (
            max(s - strike, 0) if right == OptionRight.CALL else max(strike - s, 0)
        )
        values.append(intrinsic)
    for i in range(steps - 1, -1, -1):
        next_values = []
        for j in range(i + 1):
            s = spot * up**j * down ** (i - j)
            continuation = disc * (p * values[j + 1] + (1 - p) * values[j])
            intrinsic = (
                max(s - strike, 0) if right == OptionRight.CALL else max(strike - s, 0)
            )
            next_values.append(max(continuation, intrinsic))
        values = next_values
    return float(values[0])


def american_implied_volatility(
    price: float,
    spot: float,
    strike: float,
    rate: float,
    carry: float,
    tau: float,
    right: OptionRight,
    steps: int = 100,
    max_vol: float = 8.0,
) -> float | None:
    if price <= 0 or spot <= 0 or strike <= 0 or tau <= 0:
        return None
    lo, hi = 1e-6, max_vol
    flo = american_price_binomial(spot, strike, rate, carry, tau, lo, right, steps)
    fhi = american_price_binomial(spot, strike, rate, carry, tau, hi, right, steps)
    if flo is None or fhi is None or not (flo <= price <= fhi):
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        value = american_price_binomial(
            spot, strike, rate, carry, tau, mid, right, steps
        )
        if value is None:
            return None
        if abs(value - price) < 1e-8:
            return mid
        if value < price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
