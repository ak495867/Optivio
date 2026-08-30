from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StreamHealth:
    state: str = "disconnected"
    reconnects: int = 0
    auth_failures: int = 0
    last_error: str | None = None
    messages: int = 0


@dataclass
class AlpacaStreamSupervisor:
    """Supervise the SDK stream; the factory must construct a fresh authenticated stream."""

    stream_factory: Callable[[str, str], Any]
    subscribe: Callable[[Any, list[str]], Awaitable[None]]
    symbols: list[str]
    credential_provider: Callable[[], tuple[str, str]]
    max_retries: int = 10
    base_delay: float = 0.5
    max_delay: float = 30.0
    health: StreamHealth = field(default_factory=StreamHealth)
    _stop: asyncio.Event = field(default_factory=asyncio.Event)

    async def run(self) -> None:
        attempt = 0
        while not self._stop.is_set() and attempt <= self.max_retries:
            try:
                self.health.state = "authenticating"
                api_key, secret_key = self.credential_provider()
                if not api_key or not secret_key:
                    raise PermissionError("missing Alpaca credentials")
                stream = self.stream_factory(api_key, secret_key)
                await self.subscribe(stream, list(self.symbols))
                self.health.state = "connected"
                attempt = 0
                await self._serve(stream)
            except (PermissionError, ConnectionError, TimeoutError, OSError) as exc:
                self.health.last_error = type(exc).__name__
                self.health.auth_failures += int(isinstance(exc, PermissionError))
                self.health.reconnects += 1
                self.health.state = "backoff"
                if attempt >= self.max_retries:
                    self.health.state = "halted"
                    return
                delay = min(self.max_delay, self.base_delay * (2**attempt))
                attempt += 1
                if not self._stop.is_set():
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=delay)
                    except TimeoutError:
                        pass
            except asyncio.CancelledError:
                self.health.state = "stopped"
                raise

    async def _serve(self, stream: Any) -> None:

        runner = getattr(stream, "run_async", None)
        if runner is not None:
            await runner()
            return
        await asyncio.to_thread(stream.run)

    def stop(self) -> None:
        self._stop.set()
