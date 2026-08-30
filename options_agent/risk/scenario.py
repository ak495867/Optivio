from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from options_agent.execution.multileg import Greeks


# Black-Scholes theta is annualized (tau in years). A scenario's theta_shock is
# expressed in days of time decay, so the annualized theta must be converted to
# per-day before the shock is applied.
TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    delta_shock: float = 0.0
    gamma_shock: float = 0.0
    vega_shock: float = 0.0
    theta_shock: float = 0.0
    rho_shock: float = 0.0
    liquidity_multiplier: float = 1.0


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    name: str
    pnl_change: float
    liquidity_adjusted_loss: float
    breached: bool


def evaluate_scenarios(
    greeks: Greeks, scenarios: list[Scenario], max_loss: float
) -> Mapping[str, ScenarioResult]:
    # Convert annualized theta to per-day so a theta_shock (in days of decay) is not
    # overstated 252x (365 with calendar days). The other greeks (delta/gamma/vega/rho)
    # are per-point/per-unit shocks and need no rescaling.
    theta_per_day = greeks.theta / TRADING_DAYS_PER_YEAR
    results: dict[str, ScenarioResult] = {}
    for scenario in scenarios:
        pnl = (
            greeks.delta * scenario.delta_shock
            + 0.5 * greeks.gamma * scenario.delta_shock**2
            + greeks.vega * scenario.vega_shock
            + theta_per_day * scenario.theta_shock
            + greeks.rho * scenario.rho_shock
            + greeks.gamma * scenario.gamma_shock
        )
        adjusted_loss = max(0.0, -pnl) * max(1.0, scenario.liquidity_multiplier)
        results[scenario.name] = ScenarioResult(
            scenario.name, pnl, adjusted_loss, adjusted_loss > max_loss
        )
    return results
