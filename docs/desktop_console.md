# Optivio desktop console

> **Quick take:** This is the local control room for Optivio. It gives one place to enter runtime credentials, run preflight, inspect services, invoke individual components, and control a paper-only session.

## What the console does

The Tkinter console is intentionally small and local. It does not replace the research modules; it coordinates them. The left panel handles runtime setup and lifecycle controls. The health cards show the state of the major service groups. The component table lets an operator invoke a single research, model, risk, validation, or execution boundary. The timeline records what happened without recording credentials.

## Start / Run sequence

When the operator clicks **Start / Run**, Optivio keeps the credential values in memory, checks that both Alpaca values exist, verifies that the endpoint contains the paper host, and builds a gate report. In signal-only and shadow modes, the runtime can move to running after preflight. In constrained-paper mode, it stays in synchronization until a verified stream and broker snapshot are available.

The desktop console does not silently turn on live trading. The only accepted endpoint is `https://paper-api.alpaca.markets`, the default mode is signal-only, and Groq remains advisory. A future broker adapter must still pass the existing typed intent, quote-quality, portfolio, Greeks, scenario, liquidity, and reconciliation checks before an order can be submitted.

## Lifecycle controls

**Pause exposure** records a pause and is intended to stop new exposure while allowing monitoring to continue. **Recover / Reconnect** moves the runtime into recovery and keeps new exposure blocked. **Stop** records an operator stop and returns the local state to stopped. Recovery should be followed by a new broker snapshot and a verified synchronization before constrained paper activity resumes.

## Audit timeline

The audit file is `.optivio/operator_audit.tsv`. It stores a nanosecond event marker, severity, event name, and sanitized detail. Secret values are never placed in the timeline. For a long-running installation, move this file to a durable append-only store such as the existing SQLite event store and retain correlation IDs for decisions, orders, fills, risk results, and reconciliation snapshots.

## Running it

From the Optivio repository root:

```bash
python -m optivio_desktop.app
```

Tkinter is part of most standard Python desktop installations. On Linux, the system package that provides Tk may need to be installed separately. The console is designed to run on the operator’s own machine, where credentials can be entered interactively and the machine can remain online for the duration of a paper session.

## Operational boundary

This is a local operator console, not an unattended production deployment. It currently provides the orchestration shell and safe state transitions; the full live-paper wiring still needs the concrete Alpaca stream, contract master, durable event replay, broker reconciliation, multi-leg lifecycle, and monitoring workers connected to the registered component actions. The safe default is to keep the GUI in signal-only or shadow mode until those dependencies report healthy and the operator has reviewed the audit timeline.
