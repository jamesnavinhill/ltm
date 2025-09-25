from __future__ import annotations

import json
from pathlib import Path

from plans.agent_prototype.queue import PayloadQueue


def test_queue_enqueue_dequeue_mark_success(tmp_path: Path):
    db_path = tmp_path / "queue.db"
    q = PayloadQueue(db_path=db_path)
    payload = {"hello": "world"}
    q.enqueue(payload)
    items = list(q.dequeue_batch(limit=10))
    assert len(items) == 1
    pid, pl = items[0]
    assert pl == payload

    # mark failure should keep item
    q.mark_failure(pid)
    items2 = list(q.dequeue_batch(limit=10))
    assert len(items2) == 1

    # mark success should remove
    q.mark_success(pid)
    items3 = list(q.dequeue_batch(limit=10))
    assert len(items3) == 0


