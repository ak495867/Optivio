from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    event_id: str
    event_type: str
    order_id: str
    symbol: str
    event_time: datetime
    available_at: datetime
    quantity: int
    price: float
    fee: float = 0.0
    realized_pnl: float | None = None
    strategy_id: str = ""
    model_version: str = ""
    source_id: str = ""


class ExecutionStateStore:
    """Append-only JSONL state with hash chaining and delayed model feedback."""
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_hash = self._read_last_hash()

    def _read_last_hash(self) -> str:
        if not self.path.exists():
            return "0" * 64
        last = "0" * 64
        for line in self.path.read_text().splitlines():
            if line.strip():
                last = json.loads(line)["record_hash"]
        return last

    def append(self, event: ExecutionEvent) -> str:
        if event.available_at < event.event_time:
            raise ValueError("available_at cannot precede event_time")
        payload = asdict(event)
        payload["event_time"] = event.event_time.isoformat()
        payload["available_at"] = event.available_at.isoformat()
        payload["previous_hash"] = self._last_hash
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        record_hash = hashlib.sha256(encoded).hexdigest()
        record = {**payload, "record_hash": record_hash}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        self._last_hash = record_hash
        return record_hash

    def verify_chain(self) -> bool:
        previous = "0" * 64
        if not self.path.exists():
            return True
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("previous_hash") != previous:
                return False
            stored = record.pop("record_hash", None)
            encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            if stored != hashlib.sha256(encoded).hexdigest():
                return False
            previous = stored
        return True

    def feedback(self, decision_cutoff: datetime) -> list[dict]:
        """Return only realized outcomes whose availability is at or before cutoff."""
        rows: list[dict] = []
        if not self.path.exists():
            return rows
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            available = datetime.fromisoformat(row["available_at"])
            if row.get("realized_pnl") is not None and available <= decision_cutoff:
                rows.append(row)
        return rows

    def feedback_features(self, decision_cutoff: datetime) -> dict[str, float]:
        rows = self.feedback(decision_cutoff)
        pnl = [float(row["realized_pnl"]) for row in rows]
        return {
            "outcome_count": float(len(pnl)),
            "realized_pnl_sum": float(sum(pnl)),
            "realized_pnl_mean": float(sum(pnl) / len(pnl)) if pnl else 0.0,
            "win_rate": float(sum(value > 0 for value in pnl) / len(pnl)) if pnl else 0.0,
        }
