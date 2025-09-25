from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Dict, Iterable, Optional


DEFAULT_DB = Path(os.getenv("AGENT_QUEUE_DB", Path(__file__).parent / "agent_queue.db"))


class PayloadQueue:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self._lock = threading.Lock()
        self._ensure_tables()

    def _ensure_tables(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queue (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  payload TEXT NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  attempts INTEGER DEFAULT 0
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        return conn

    def enqueue(self, payload: Dict):
        body = json.dumps(payload)
        with self._lock, self._connect() as conn:
            conn.execute("INSERT INTO queue (payload) VALUES (?)", (body,))
            conn.commit()

    def dequeue_batch(self, limit: int = 25) -> Iterable[tuple[int, Dict]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT id, payload, attempts FROM queue ORDER BY id ASC LIMIT ?", (limit,)).fetchall()
            for row in rows:
                pid, payload_str, _ = row
                try:
                    payload = json.loads(payload_str)
                except Exception:
                    payload = {"_corrupt": payload_str}
                yield pid, payload

    def mark_success(self, pid: int):
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM queue WHERE id = ?", (pid,))
            conn.commit()

    def mark_failure(self, pid: int):
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE queue SET attempts = attempts + 1 WHERE id = ?", (pid,))
            conn.commit()


