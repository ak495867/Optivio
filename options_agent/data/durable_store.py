from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class StoredEvent:
    sequence: int
    event_type: str
    event_time: str
    available_at: str
    payload: dict[str, Any]
    previous_hash: str
    record_hash: str


class DurableEventStore:
    """Append-only SQLite journal with deterministic replay and tamper evidence."""

    def __init__(self, path: Path, schema_version: int = 1):
        self.path = path
        self.schema_version = schema_version
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, event_type TEXT NOT NULL, event_time TEXT NOT NULL, available_at TEXT NOT NULL, payload TEXT NOT NULL, previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL, schema_version INTEGER NOT NULL)"
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        # A nonzero busy_timeout makes a concurrent writer wait for the lock
        # instead of raising "database is locked" immediately (default is 0).
        connection = sqlite3.connect(self.path, timeout=5.0)
        return connection

    def append(
        self,
        event_type: str,
        event_time: str,
        available_at: str,
        payload: dict[str, Any],
    ) -> StoredEvent:
        # The append is a read-modify-write (peek the last record's hash, then
        # chain onto it). Without holding the write lock while reading, two
        # concurrent appends can both read the same tail and interleave -- one
        # fails, or the hash chain corrupts. BEGIN IMMEDIATE acquires the write
        # lock up front, so concurrent appends serialize: each sees the tail
        # the previous writer committed. With the busy timeout set, the
        # second writer waits instead of erroring.
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT sequence, record_hash FROM events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            sequence, previous = (
                (int(row[0]) + 1, str(row[1])) if row else (1, "0" * 64)
            )
            body = {
                "sequence": sequence,
                "event_type": event_type,
                "event_time": event_time,
                "available_at": available_at,
                "payload": payload,
                "previous_hash": previous,
                "schema_version": self.schema_version,
            }
            record_hash = hashlib.sha256(
                json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sequence,
                    event_type,
                    event_time,
                    available_at,
                    json.dumps(payload, sort_keys=True),
                    previous,
                    record_hash,
                    self.schema_version,
                ),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        return StoredEvent(
            sequence,
            event_type,
            event_time,
            available_at,
            payload,
            previous,
            record_hash,
        )

    def replay(self, after_sequence: int = 0) -> Iterable[StoredEvent]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT sequence, event_type, event_time, available_at, payload, previous_hash, record_hash FROM events WHERE sequence > ? ORDER BY sequence",
                (after_sequence,),
            ).fetchall()
        for row in rows:
            yield StoredEvent(
                int(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3]),
                json.loads(row[4]),
                str(row[5]),
                str(row[6]),
            )

    def verify(self) -> bool:
        previous = "0" * 64
        for event in self.replay():
            if event.previous_hash != previous:
                return False
            body = {
                "sequence": event.sequence,
                "event_type": event.event_type,
                "event_time": event.event_time,
                "available_at": event.available_at,
                "payload": event.payload,
                "previous_hash": event.previous_hash,
                "schema_version": self.schema_version,
            }
            if (
                hashlib.sha256(
                    json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                != event.record_hash
            ):
                return False
            previous = event.record_hash
        return True
