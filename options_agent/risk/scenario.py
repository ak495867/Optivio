from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from options_agent.execution.multileg import Greeks


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


def evaluate_scenarios(greeks: Greeks, scenarios: list[Scenario], max_loss: float) -> Mapping[str, ScenarioResult]:
    results: dict[str, ScenarioResult] = {}
    for scenario in scenarios:
        pnl = greeks.delta * scenario.delta_shock + .5 * greeks.gamma * scenario.delta_shock**2 + greeks.vega * scenario.vega_shock + greeks.theta * scenario.theta_shock + greeks.rho * scenario.rho_shock + greeks.gamma * scenario.gamma_shock
        adjusted_loss = max(0.0, -pnl) * max(1.0, scenario.liquidity_multiplier)
        results[scenario.name] = ScenarioResult(scenario.name, pnl, adjusted_loss, adjusted_loss > max_loss)
    return results
