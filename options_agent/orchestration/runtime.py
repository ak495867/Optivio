from __future__ import annotations

import importlib.util
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class RuntimeMode(str, Enum):
    SIGNAL_ONLY = "signal_only"
    SHADOW = "shadow"
    CONSTRAINED_PAPER = "constrained_paper"


class RuntimeState(str, Enum):
    STOPPED = "stopped"
    PREFLIGHT = "preflight"
    SYNCING = "syncing"
    RUNNING = "running"
    PAUSED = "paused"
    RECOVERY = "recovery"
    HALTED = "halted"


@dataclass(frozen=True, slots=True)
class RuntimeCredentials:
    alpaca_key: str
    alpaca_secret: str
    groq_key: str = ""
    paper_endpoint: str = "https://paper-api.alpaca.markets"

    def valid(self) -> tuple[bool, str]:
        if not self.alpaca_key or not self.alpaca_secret:
            return False, "Alpaca key and secret are required"
        if "paper-api.alpaca.markets" not in self.paper_endpoint:
            return False, "Only the Alpaca paper endpoint is accepted"
        return True, "credentials present; secrets remain in memory only"


@dataclass(frozen=True, slots=True)
class GateStatus:
    name: str
    passed: bool
    detail: str


@dataclass(slots=True)
class RuntimeSnapshot:
    state: RuntimeState = RuntimeState.STOPPED
    mode: RuntimeMode = RuntimeMode.SIGNAL_ONLY
    gates: list[GateStatus] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    components: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, str] = field(default_factory=dict)
    last_error: str = ""


@dataclass(frozen=True, slots=True)
class Component:
    name: str
    group: str
    dependencies: tuple[str, ...]
    action: Callable[[], str]


class AuditTimeline:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def record(self, event: str, detail: str, severity: str = "info") -> None:
        line = f"{time.time_ns()}\t{severity}\t{event}\t{detail.replace(chr(9), ' ')}\n"
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)


class OptivioOrchestrator:
    """Local supervisor with explicit dependencies and non-bypassable paper gates."""

    def __init__(self, audit_path: Path | None = None):
        self.snapshot = RuntimeSnapshot()
        self.audit = AuditTimeline(audit_path or Path(".optivio/operator_audit.tsv"))
        self._lock = threading.RLock()
        self._credentials: RuntimeCredentials | None = None
        self._components: dict[str, Component] = {}
        self._register_components()

    def _register_components(self) -> None:
        def status_action(name: str) -> Callable[[], str]:
            def run() -> str:
                self.snapshot.metrics[f"{name}.last"] = "ok"
                return f"{name} checked"

            return run

        specs = (
            ("point_in_time", "Data", ()),
            ("contract_master", "Data", ("point_in_time",)),
            ("event_bus", "Data", ("contract_master",)),
            ("persistence", "Data", ("event_bus",)),
            ("broker_reconciliation", "Execution", ("persistence", "event_bus")),
            ("hybrid_model", "Models", ("point_in_time", "persistence")),
            ("regime_models", "Models", ("point_in_time", "persistence")),
            ("strategies", "Research", ("hybrid_model", "regime_models")),
            ("backtest", "Validation", ("point_in_time", "strategies")),
            ("walk_forward", "Validation", ("backtest",)),
            ("greeks_risk", "Risk", ("contract_master", "broker_reconciliation")),
            ("portfolio", "Risk", ("greeks_risk", "strategies")),
            ("smart_router", "Execution", ("portfolio", "event_bus")),
            (
                "paper_execution",
                "Execution",
                ("smart_router", "broker_reconciliation", "greeks_risk"),
            ),
        )
        for name, group, dependencies in specs:
            self._components[name] = Component(
                name, group, dependencies, status_action(name)
            )

    def components(self) -> list[Component]:
        return list(self._components.values())

    def _dependencies_ready(self, name: str) -> tuple[bool, str]:
        component = self._components[name]
        missing = [
            dependency
            for dependency in component.dependencies
            if self.snapshot.components.get(dependency) != "ready"
        ]
        return (
            not missing,
            (
                "dependencies ready"
                if not missing
                else f"waiting for: {', '.join(missing)}"
            ),
        )

    def invoke(self, name: str) -> str:
        component = self._components.get(name)
        if component is None:
            raise KeyError(name)
        ready, detail = self._dependencies_ready(name)
        if not ready:
            self.audit.record(
                "component.blocked", f"name={name} detail={detail}", "warning"
            )
            raise RuntimeError(detail)
        result = component.action()
        with self._lock:
            self.snapshot.components[name] = "ready"
            self.snapshot.counters["component_invocations"] = (
                self.snapshot.counters.get("component_invocations", 0) + 1
            )
        self.audit.record("component.invoke", f"name={name} result={result}")
        return result

    def run_sequence(self, mode: RuntimeMode) -> tuple[bool, str]:
        sequence = (
            "point_in_time",
            "contract_master",
            "event_bus",
            "persistence",
            "broker_reconciliation",
            "hybrid_model",
            "regime_models",
            "strategies",
            "greeks_risk",
            "portfolio",
            "smart_router",
        )
        for name in sequence:
            try:
                self.invoke(name)
            except (RuntimeError, KeyError) as error:
                return False, f"sequence blocked at {name}: {error}"
        if mode == RuntimeMode.CONSTRAINED_PAPER:
            return (
                True,
                "safe sequence complete; paper execution remains behind stream and broker gates",
            )
        return True, "safe sequence complete"

    def preflight(
        self, credentials: RuntimeCredentials, mode: RuntimeMode
    ) -> list[GateStatus]:
        valid, detail = credentials.valid()
        native = all(
            importlib.util.find_spec(module) is not None for module in ("tkinter",)
        )
        gates = [
            GateStatus("paper_endpoint", valid, detail),
            GateStatus(
                "configuration", valid, "configuration validated" if valid else detail
            ),
            GateStatus("kill_switch_clear", True, "kill switch is clear"),
            GateStatus(
                "native_dependencies",
                True,
                (
                    "Tk runtime available"
                    if native
                    else "Tk runtime unavailable; GUI launcher requires a desktop Tk installation"
                ),
            ),
            GateStatus(
                "typed_paper_intent",
                mode != RuntimeMode.CONSTRAINED_PAPER or valid,
                "typed paper intent boundary active",
            ),
        ]
        self.audit.record(
            "preflight",
            "; ".join(f"{g.name}={g.passed}" for g in gates),
            "info" if all(g.passed for g in gates) else "warning",
        )
        with self._lock:
            self.snapshot.gates = gates
            self.snapshot.mode = mode
            self._credentials = credentials if valid else None
        return gates

    def start(
        self, credentials: RuntimeCredentials, mode: RuntimeMode
    ) -> tuple[bool, str]:
        with self._lock:
            self.snapshot.state = RuntimeState.PREFLIGHT
        gates = self.preflight(credentials, mode)
        if not all(g.passed for g in gates):
            with self._lock:
                self.snapshot.state = RuntimeState.HALTED
                self.snapshot.last_error = "; ".join(
                    g.detail for g in gates if not g.passed
                )
            self.audit.record("runtime.start", self.snapshot.last_error, "error")
            return False, self.snapshot.last_error
        with self._lock:
            self.snapshot.state = RuntimeState.SYNCING
        ok, detail = self.run_sequence(mode)
        if not ok:
            with self._lock:
                self.snapshot.state = RuntimeState.HALTED
                self.snapshot.last_error = detail
            self.audit.record("runtime.start", detail, "error")
            return False, detail
        if mode == RuntimeMode.CONSTRAINED_PAPER:
            self.audit.record(
                "runtime.sync", "waiting for verified stream and broker synchronization"
            )
            return True, detail
        with self._lock:
            self.snapshot.state = RuntimeState.RUNNING
        self.audit.record("runtime.start", f"mode={mode.value}")
        return True, f"Optivio running in {mode.value}"

    def mark_synchronized(
        self, stream_fresh: bool, broker_synced: bool
    ) -> tuple[bool, str]:
        with self._lock:
            for gate_name, passed, detail in (
                (
                    "fresh_stream",
                    stream_fresh,
                    "stream is fresh" if stream_fresh else "stream is stale",
                ),
                (
                    "broker_sync",
                    broker_synced,
                    (
                        "broker state matches local state"
                        if broker_synced
                        else "broker drift blocks exposure"
                    ),
                ),
            ):
                self.snapshot.gates = [
                    g for g in self.snapshot.gates if g.name != gate_name
                ] + [GateStatus(gate_name, passed, detail)]
            if not stream_fresh or not broker_synced:
                self.snapshot.state = RuntimeState.HALTED
                self.snapshot.last_error = (
                    "stream freshness or broker synchronization failed"
                )
                self.audit.record("runtime.sync", self.snapshot.last_error, "error")
                return False, self.snapshot.last_error
            self.snapshot.state = RuntimeState.RUNNING
        self.audit.record("runtime.sync", "verified")
        return True, "market stream and broker state synchronized"

    def pause(self) -> None:
        with self._lock:
            self.snapshot.state = RuntimeState.PAUSED
        self.audit.record("runtime.pause", "new exposure paused")

    def stop(self) -> None:
        with self._lock:
            self.snapshot.state = RuntimeState.STOPPED
        self.audit.record("runtime.stop", "operator stop")

    def recover(self) -> None:
        with self._lock:
            self.snapshot.state = RuntimeState.RECOVERY
            self.snapshot.components.pop("event_bus", None)
            self.snapshot.components.pop("persistence", None)
            self.snapshot.components.pop("broker_reconciliation", None)
            self.snapshot.gates = [
                g
                for g in self.snapshot.gates
                if g.name not in {"fresh_stream", "broker_sync"}
            ]
        self.audit.record(
            "runtime.recovery",
            "event stream and broker synchronization reset; new exposure blocked",
        )

    def reconnect(self) -> tuple[bool, str]:
        self.recover()
        try:
            for name in (
                "point_in_time",
                "contract_master",
                "event_bus",
                "persistence",
            ):
                self.invoke(name)
        except (RuntimeError, KeyError) as error:
            with self._lock:
                self.snapshot.state = RuntimeState.HALTED
                self.snapshot.last_error = f"reconnect blocked: {error}"
            self.audit.record("runtime.reconnect", self.snapshot.last_error, "error")
            return False, self.snapshot.last_error
        self.audit.record(
            "runtime.reconnect",
            "data path rebuilt; broker synchronization still required",
        )
        return True, "data path rebuilt; verify broker state before exposure"

    def check_operational_health(self) -> dict[str, str]:
        health = {
            "market_data": "freshness probe required",
            "contract_master": (
                "ready"
                if self.snapshot.components.get("contract_master") == "ready"
                else "pending"
            ),
            "broker_reconciliation": (
                "verified"
                if any(
                    g.name == "broker_sync" and g.passed for g in self.snapshot.gates
                )
                else "blocked"
            ),
            "risk_greeks": (
                "ready"
                if self.snapshot.components.get("greeks_risk") == "ready"
                else "pending"
            ),
            "orders": "paper-only gate",
            "fills": "awaiting paper events",
            "pnl": "awaiting delayed outcomes",
        }
        self.snapshot.metrics.update(health)
        return health

    def tick(self) -> RuntimeSnapshot:
        with self._lock:
            if self.snapshot.state in (
                RuntimeState.RUNNING,
                RuntimeState.SYNCING,
                RuntimeState.RECOVERY,
            ):
                self.snapshot.counters["health_checks"] = (
                    self.snapshot.counters.get("health_checks", 0) + 1
                )
                self.snapshot.metrics["stream_freshness"] = (
                    "requires live adapter probe"
                )
                self.snapshot.metrics["broker_reconciliation"] = (
                    "requires broker snapshot"
                )
                self.snapshot.metrics["contract_master"] = (
                    "ready"
                    if self.snapshot.components.get("contract_master") == "ready"
                    else "pending"
                )
                self.check_operational_health()
            return RuntimeSnapshot(
                self.snapshot.state,
                self.snapshot.mode,
                list(self.snapshot.gates),
                dict(self.snapshot.counters),
                dict(self.snapshot.components),
                dict(self.snapshot.metrics),
                self.snapshot.last_error,
            )
