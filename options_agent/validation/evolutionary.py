from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Genome:
    values: np.ndarray
    fitness: float = float("-inf")
    train_fitness: float = float("-inf")
    test_fitness: float | None = None


@dataclass(frozen=True)
class EvolutionConfig:
    population: int = 32
    generations: int = 20
    elite: int = 4
    tournament: int = 3
    mutation_rate: float = 0.12
    mutation_scale: float = 0.08
    seed: int = 7


class OptivioEvolutionaryOptimizer:
    """GA plus evolutionary-selection optimizer.

    The objective must be evaluated only on a training fold. Test-fold data is
    intentionally absent from `fit`; callers may evaluate the selected genome
    once on an untouched test or zero-shot block.
    """
    def __init__(self, lower: np.ndarray, upper: np.ndarray, config: EvolutionConfig | None = None):
        self.lower, self.upper = np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)
        self.config = config or EvolutionConfig()
        if self.lower.shape != self.upper.shape or np.any(self.lower >= self.upper):
            raise ValueError("invalid genome bounds")
        if self.config.elite >= self.config.population:
            raise ValueError("elite count must be below population")
        self.best: Genome | None = None
        self.history: list[float] = []

    def _initial(self, rng: np.random.Generator) -> list[Genome]:
        return [Genome(rng.uniform(self.lower, self.upper)) for _ in range(self.config.population)]

    def _select(self, pop: list[Genome], rng: np.random.Generator) -> Genome:
        indices = rng.choice(len(pop), size=self.config.tournament, replace=False)
        candidates = [pop[int(index)] for index in indices]
        return max(candidates, key=lambda g: g.fitness)

    def _child(self, a: Genome, b: Genome, rng: np.random.Generator) -> Genome:
        mask = rng.random(a.values.size) < 0.5
        values = np.where(mask, a.values, b.values).astype(float)
        mutate = rng.random(values.size) < self.config.mutation_rate
        values[mutate] += rng.normal(0, self.config.mutation_scale, mutate.sum()) * (self.upper - self.lower)[mutate]
        return Genome(np.clip(values, self.lower, self.upper))

    def fit(self, objective) -> Genome:
        rng = np.random.default_rng(self.config.seed)
        pop = self._initial(rng)
        for _ in range(self.config.generations):
            scored = [Genome(g.values, float(objective(g.values)), float(objective(g.values))) for g in pop]
            scored.sort(key=lambda g: g.fitness, reverse=True)
            self.history.append(scored[0].fitness)
            if self.best is None or scored[0].fitness > self.best.fitness:
                self.best = scored[0]
            next_pop = scored[: self.config.elite]
            while len(next_pop) < self.config.population:
                next_pop.append(self._child(self._select(scored, rng), self._select(scored, rng), rng))
            pop = next_pop
        if self.best is None:
            raise RuntimeError("evolution did not produce a genome")
        return self.best


def risk_adjusted_objective(returns: np.ndarray, turnover: np.ndarray, drawdown_penalty: float = 1.0, turnover_penalty: float = 0.1) -> float:
    r, t = np.asarray(returns, dtype=float), np.asarray(turnover, dtype=float)
    if r.size == 0 or r.shape != t.shape:
        raise ValueError("returns and turnover must be non-empty and aligned")
    curve = np.cumprod(1 + r)
    dd = float(np.min(curve / np.maximum.accumulate(curve) - 1))
    sharpe = float(np.sqrt(252) * r.mean() / r.std()) if r.std() > 0 else 0.0
    return sharpe + drawdown_penalty * dd - turnover_penalty * float(t.mean())
