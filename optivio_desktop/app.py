from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from options_agent.orchestration.runtime import (
    OptivioOrchestrator,
    RuntimeCredentials,
    RuntimeMode,
    RuntimeState,
)


class OptivioConsole(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Optivio · Paper Trading Control Console")
        self.geometry("1280x820")
        self.minsize(1060, 700)
        self.configure(bg="#0b1220")
        self.orchestrator = OptivioOrchestrator(Path(".optivio/operator_audit.tsv"))
        self.events: queue.Queue[str] = queue.Queue()
        self.mode = tk.StringVar(value=RuntimeMode.SIGNAL_ONLY.value)
        self.state_var = tk.StringVar(value=RuntimeState.STOPPED.value.upper())
        self.status = tk.StringVar(value="Ready for a paper-only preflight")
        self.alpaca_key = tk.StringVar()
        self.alpaca_secret = tk.StringVar()
        self.groq_key = tk.StringVar()
        self._build_styles()
        self._build_ui()
        self.after(750, self._refresh)

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#0b1220")
        style.configure("Panel.TFrame", background="#111b2e")
        style.configure("TLabel", background="#0b1220", foreground="#c9d5e8", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#0b1220", foreground="#f4f7fb", font=("Segoe UI", 22, "bold"))
        style.configure("Muted.TLabel", background="#0b1220", foreground="#8190a8", font=("Segoe UI", 9))
        style.configure("PanelTitle.TLabel", background="#111b2e", foreground="#f4f7fb", font=("Segoe UI", 11, "bold"))
        style.configure("TButton", padding=(12, 8), background="#20304b", foreground="#f4f7fb", borderwidth=0)
        style.map("TButton", background=[("active", "#2f476a")])
        style.configure("Accent.TButton", background="#2d7ff9", foreground="white", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#4a95ff")])
        style.configure("Danger.TButton", background="#7e2943", foreground="white")
        style.configure("TEntry", fieldbackground="#17243a", foreground="#f4f7fb", insertcolor="white", borderwidth=0, padding=8)
        style.configure("TCombobox", fieldbackground="#17243a", foreground="#f4f7fb")
        style.configure("Treeview", background="#0f1929", fieldbackground="#0f1929", foreground="#c9d5e8", rowheight=26, borderwidth=0)
        style.configure("Treeview.Heading", background="#1c2a42", foreground="#f4f7fb", relief="flat")

    def _panel(self, parent: ttk.Frame, title: str, row: int, column: int) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        frame.grid(row=row, column=column, sticky="nsew", padx=6, pady=6)
        ttk.Label(frame, text=title, style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 12))
        return frame

    def _build_ui(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", padx=24, pady=(20, 12))
        ttk.Label(header, text="OPTIVIO", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="local paper-trading control console", style="Muted.TLabel").pack(side="left", padx=14, pady=(8, 0))
        ttk.Label(header, textvariable=self.state_var, foreground="#7ee2b8", background="#0b1220", font=("Segoe UI", 12, "bold")).pack(side="right", pady=(8, 0))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(1, weight=1)

        setup = self._panel(body, "Runtime setup", 0, 0)
        ttk.Label(setup, text="Alpaca paper key").pack(anchor="w")
        ttk.Entry(setup, textvariable=self.alpaca_key, show="•").pack(fill="x", pady=(4, 10))
        ttk.Label(setup, text="Alpaca paper secret").pack(anchor="w")
        ttk.Entry(setup, textvariable=self.alpaca_secret, show="•").pack(fill="x", pady=(4, 10))
        ttk.Label(setup, text="Groq key (optional, kept advisory)").pack(anchor="w")
        ttk.Entry(setup, textvariable=self.groq_key, show="•").pack(fill="x", pady=(4, 10))
        ttk.Label(setup, text="Execution mode").pack(anchor="w")
        ttk.Combobox(setup, textvariable=self.mode, values=[m.value for m in RuntimeMode], state="readonly").pack(fill="x", pady=(4, 12))
        controls = ttk.Frame(setup, style="Panel.TFrame")
        controls.pack(fill="x")
        ttk.Button(controls, text="Start / Run", style="Accent.TButton", command=self._start).pack(fill="x", pady=3)
        ttk.Button(controls, text="Pause exposure", command=self._pause).pack(fill="x", pady=3)
        ttk.Button(controls, text="Recover / Reconnect", command=self._recover).pack(fill="x", pady=3)
        ttk.Button(controls, text="Stop", style="Danger.TButton", command=self._stop).pack(fill="x", pady=3)
        ttk.Label(setup, text="Secrets are validated in memory and never written to the audit timeline.", style="Muted.TLabel", wraplength=260).pack(anchor="w", pady=(14, 0))

        status = self._panel(body, "System health", 0, 1)
        status_body = ttk.Frame(status, style="Panel.TFrame")
        status_body.pack(fill="both", expand=True)
        status_body.columnconfigure(0, weight=1)
        status_body.columnconfigure(1, weight=1)
        status_body.columnconfigure(2, weight=1)
        self.health_labels: dict[str, ttk.Label] = {}
        health_keys = (("Market data", "market_data"), ("Contract master", "contract_master"), ("Models / strategies", "models"), ("Risk / Greeks", "risk_greeks"), ("Broker reconciliation", "broker_reconciliation"), ("Latency", "latency"), ("Orders", "orders"), ("Fills", "fills"), ("PnL", "pnl"))
        for idx, (label, key) in enumerate(health_keys):
            box = ttk.Frame(status_body, style="Panel.TFrame", padding=10)
            box.grid(row=1 + idx // 3, column=idx % 3, sticky="ew", padx=4, pady=4)
            ttk.Label(box, text=label, style="Muted.TLabel").pack(anchor="w")
            value_label = ttk.Label(box, text="STANDBY", foreground="#f2bd68", background="#111b2e", font=("Segoe UI", 11, "bold"))
            value_label.pack(anchor="w", pady=(5, 0))
            self.health_labels[key] = value_label

        lower = ttk.Frame(body)
        lower.grid(row=1, column=0, columnspan=2, sticky="nsew")
        lower.columnconfigure(0, weight=1)
        lower.columnconfigure(1, weight=1)
        lower.rowconfigure(0, weight=1)
        components = self._panel(lower, "Invoke components", 0, 0)
        self.component_tree = ttk.Treeview(components, columns=("group", "status"), show="headings", height=13)
        self.component_tree.heading("group", text="Group")
        self.component_tree.heading("status", text="Status")
        self.component_tree.column("group", width=120)
        self.component_tree.column("status", width=130)
        self.component_tree.pack(fill="both", expand=True)
        for component in self.orchestrator.components():
            self.component_tree.insert("", "end", iid=component.name, values=(component.group, "standby"))
        ttk.Button(components, text="Invoke selected", command=self._invoke).pack(anchor="e", pady=(10, 0))

        timeline = self._panel(lower, "Operator timeline", 0, 1)
        self.log = tk.Text(timeline, height=13, bg="#0f1929", fg="#c9d5e8", insertbackground="white", relief="flat", padx=10, pady=8, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)
        ttk.Label(self, textvariable=self.status, style="Muted.TLabel").pack(fill="x", padx=28, pady=(0, 12))

    def _write(self, text: str) -> None:
        self.events.put(text)

    def _start(self) -> None:
        credentials = RuntimeCredentials(self.alpaca_key.get(), self.alpaca_secret.get(), self.groq_key.get())
        mode = RuntimeMode(self.mode.get())
        self._write("Start requested: running preflight; secrets omitted")
        threading.Thread(target=self._start_worker, args=(credentials, mode), daemon=True).start()

    def _start_worker(self, credentials: RuntimeCredentials, mode: RuntimeMode) -> None:
        ok, detail = self.orchestrator.start(credentials, mode)
        self._write(detail)
        if ok and mode == RuntimeMode.CONSTRAINED_PAPER:
            self._write("Constrained paper mode is blocked until verified broker synchronization")

    def _invoke(self) -> None:
        selected = self.component_tree.selection()
        if not selected:
            return
        name = selected[0]
        try:
            detail = self.orchestrator.invoke(name)
            self.component_tree.set(name, "status", "ready")
            self._write(f"component {name}: {detail}")
        except (KeyError, RuntimeError) as error:
            self._write(f"component {name}: blocked — {error}")

    def _pause(self) -> None:
        self.orchestrator.pause()
        self._write("New exposure paused")

    def _recover(self) -> None:
        self._write("Recovery requested; rebuilding data path in background")
        threading.Thread(target=self._reconnect_worker, daemon=True).start()

    def _reconnect_worker(self) -> None:
        ok, detail = self.orchestrator.reconnect()
        self._write(detail if ok else f"Reconnect halted: {detail}")

    def _stop(self) -> None:
        self.orchestrator.stop()
        self._write("Operator stop recorded")

    def _refresh(self) -> None:
        snapshot = self.orchestrator.tick()
        self.state_var.set(snapshot.state.value.upper())
        for key, label in self.health_labels.items():
            label.configure(text=snapshot.metrics.get(key, "standby").upper())
        self.status.set(f"{snapshot.state.value} · mode={snapshot.mode.value} · health checks={snapshot.counters.get('health_checks', 0)} · orders={snapshot.metrics.get('orders', 'standby')} · pnl={snapshot.metrics.get('pnl', 'standby')}")
        while not self.events.empty():
            try:
                message = self.events.get_nowait()
            except queue.Empty:
                break
            self.log.configure(state="normal")
            self.log.insert("end", f"• {message}\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.after(750, self._refresh)


def main() -> None:
    os.environ.setdefault("OPTIVIO_PAPER_ONLY", "1")
    OptivioConsole().mainloop()


if __name__ == "__main__":
    main()
