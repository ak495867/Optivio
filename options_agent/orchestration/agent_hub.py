from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from options_agent.contracts import Signal


@dataclass(frozen=True, slots=True)
class AgentResult:
    agent_id: str
    signal: Signal | None
    error: str | None = None


class IndependentAgentHub:
    """Runs independent signal agents in parallel; execution remains centrally gated."""

    def __init__(
        self,
        agents: Mapping[str, Callable[[object], Signal]],
        workers: int | None = None,
    ):
        if not agents:
            raise ValueError("at least one agent is required")
        self._agents = dict(agents)
        self._pool = ThreadPoolExecutor(
            max_workers=workers or len(agents), thread_name_prefix="optivio-agent"
        )

    def infer(self, observation: object) -> tuple[AgentResult, ...]:
        futures = {
            self._pool.submit(agent, observation): agent_id
            for agent_id, agent in self._agents.items()
        }
        results: list[AgentResult] = []
        for future in as_completed(futures):
            agent_id = futures[future]
            try:
                results.append(AgentResult(agent_id, future.result()))
            except Exception as error:
                results.append(AgentResult(agent_id, None, type(error).__name__))
        return tuple(sorted(results, key=lambda result: result.agent_id))

    def close(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=True)
