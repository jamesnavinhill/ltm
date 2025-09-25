from __future__ import annotations

import types

import pytest

from plans.agent_prototype.capture import submit_to_openmemory, AgentConfig


class _Resp:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _DummyAsyncClient:
    def __init__(self, *args, **kwargs):
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json):
        # record and echo
        self.requests.append((url, json))
        return _Resp(200, {"ok": True, "echo": json})


def test_submit_to_openmemory_mocks_httpx(monkeypatch):
    import httpx

    dummy = _DummyAsyncClient()
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: dummy)

    cfg = AgentConfig(openmemory_url="http://dummy")
    payload = {
        "user_id": "alice",
        "app": "work",
        "metadata": {"source": "screen-ocr", "window_title": "X", "process": "Y", "capture_mode": "manual", "ocr_hash": "h"},
        "infer": True,
        "text": "hello world",
    }

    res = submit_to_openmemory(payload, cfg)
    assert res.get("ok") is True
    assert res.get("echo") == payload


