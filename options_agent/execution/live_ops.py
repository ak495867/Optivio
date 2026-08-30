from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from alpaca.data.enums import OptionsFeed
from options_agent.data.alpaca_resilient import AlpacaStreamSupervisor
from options_agent.execution.lifecycle_engine import BrokerSnapshot, MultiLegPackage
from options_agent.execution.reconciliation import BrokerReconciler


@dataclass(frozen=True, slots=True)
class LiveCheck:
    name: str
    ok: bool
    detail: str


class ContinuousReconciliation:
    """Runs broker reconciliation on a cadence; any exception blocks exposure."""

    def __init__(
        self,
        reconciler: BrokerReconciler,
        snapshot_provider: Callable[
            [], tuple[dict[str, MultiLegPackage], BrokerSnapshot]
        ],
        interval_seconds: float = 5.0,
    ):
        if interval_seconds < 1.0:
            raise ValueError("reconciliation interval must be at least one second")
        self.reconciler = reconciler
        self.snapshot_provider = snapshot_provider
        self.interval_seconds = interval_seconds
        self.exposure_blocked = True
        self.last_check: LiveCheck | None = None

    def check_once(self) -> LiveCheck:
        try:
            packages, broker = self.snapshot_provider()
            result = self.reconciler.reconcile(packages, broker)
            ok = result.ok
            detail = (
                "broker state synchronized"
                if ok
                else "material broker drift; exposure blocked"
            )
        except Exception as error:

            ok, detail = False, f"broker check failed: {type(error).__name__}"
        self.exposure_blocked = not ok
        self.last_check = LiveCheck("broker_reconciliation", ok, detail)
        return self.last_check

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            self.check_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                continue


def alpaca_paper_stream_smoke_test(
    symbols: list[str], seconds: float = 5.0
) -> dict[str, object]:
    """Connect briefly to Alpaca options data; never prints credentials or submits orders."""
    key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not secret:
        return {"ok": False, "reason": "missing ALPACA_API_KEY or ALPACA_SECRET_KEY"}
    if os.environ.get("ALPACA_PAPER", "1") != "1":
        return {"ok": False, "reason": "ALPACA_PAPER must equal 1"}
    if not symbols or seconds <= 0 or seconds > 60:
        return {
            "ok": False,
            "reason": "symbols required and seconds must be between 0 and 60",
        }
    try:
        from alpaca.data.live.option import (
            OptionDataStream,
        )
    except ImportError:
        return {"ok": False, "reason": "alpaca-py is not installed"}

    received = 0

    async def on_quote(_: Any) -> None:
        nonlocal received
        received += 1

    def factory(api_key: str, secret_key: str) -> Any:
        feed = os.environ.get("ALPACA_OPTIONS_FEED", "indicative")
        return OptionDataStream(api_key, secret_key, feed=OptionsFeed(feed))

    async def subscribe(stream: Any, requested: list[str]) -> None:
        stream.subscribe_quotes(on_quote, *requested)

    supervisor = AlpacaStreamSupervisor(
        factory, subscribe, symbols, lambda: (key, secret), max_retries=2
    )

    async def bounded_run() -> None:
        task = asyncio.create_task(supervisor.run())
        await asyncio.sleep(seconds)
        supervisor.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    try:
        asyncio.run(bounded_run())
    except Exception as error:
        return {"ok": False, "reason": type(error).__name__, "received": received}
    return {
        "ok": supervisor.health.state == "connected" or received > 0,
        "received": received,
        "paper": True,
        "stream_state": supervisor.health.state,
    }
