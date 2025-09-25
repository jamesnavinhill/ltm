from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
import httpx

try:
    import pytesseract
except Exception as e:  # pragma: no cover
    pytesseract = None  # type: ignore

try:
    import mss
    import mss.tools
except Exception:  # pragma: no cover
    mss = None  # type: ignore

try:
    import win32gui  # type: ignore
    import win32process  # type: ignore
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    win32gui = None  # type: ignore
    win32process = None  # type: ignore
    psutil = None  # type: ignore

from .config import AgentConfig, ProfileRoute, load_agent_config
from .dedupe import TtlLruCache, compute_text_hash, normalize_text
from .queue import PayloadQueue


def _get_active_window_info() -> Tuple[Optional[str], Optional[str]]:
    if not win32gui or not win32process or not psutil:
        return None, None
    try:
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid).name()
        return title, process
    except Exception:
        return None, None


def _allowed_by_profile(title: Optional[str], process: Optional[str], profile: ProfileRoute) -> bool:
    if not profile.whitelist_titles and not profile.whitelist_processes:
        return True
    title_ok = True
    proc_ok = True
    if profile.whitelist_titles and title:
        title_ok = any(substr.lower() in title.lower() for substr in profile.whitelist_titles)
    if profile.whitelist_processes and process:
        proc_ok = process in profile.whitelist_processes
    return title_ok and proc_ok


def _ocr_png(path: Path, cfg: AgentConfig) -> str:
    if pytesseract is None:
        raise RuntimeError("pytesseract not installed. Install it and ensure Tesseract OCR is available.")
    if cfg.tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = cfg.tesseract_path
    return pytesseract.image_to_string(str(path))


def capture_once(config: Optional[AgentConfig] = None, profile: Optional[str] = None, dedupe: Optional[TtlLruCache] = None) -> Optional[Dict]:
    cfg = config or load_agent_config()
    chosen_profile = next((p for p in cfg.profiles if p.app == profile), cfg.profiles[0])

    if mss is None:
        raise RuntimeError("mss not installed. Install mss for screen capture.")

    title, proc = _get_active_window_info()
    if not _allowed_by_profile(title, proc, chosen_profile):
        return None

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        raw = sct.grab(monitor)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as fp:
            img_path = Path(fp.name)
        mss.tools.to_png(raw.rgb, raw.size, output=str(img_path))

    try:
        raw_text = _ocr_png(img_path, cfg)
    finally:
        if not cfg.debug_keep_png:
            try:
                os.remove(img_path)
            except OSError:
                pass

    normalized = normalize_text(raw_text)
    if not normalized:
        return None

    ocr_hash = compute_text_hash(normalized)
    if dedupe and dedupe.seen(ocr_hash):
        return None
    if dedupe:
        dedupe.add(ocr_hash)

    payload = {
        "user_id": cfg.user_id,
        "app": chosen_profile.app,
        "metadata": {
            "source": "screen-ocr",
            "window_title": title or "",
            "process": proc or "",
            "capture_mode": "manual",
            "ocr_hash": ocr_hash,
        },
        "infer": cfg.mem0_infer,
        "text": normalized,
    }
    return payload


class SubmitError(Exception):
    pass


async def submit_to_openmemory_async(payload: Dict, cfg: Optional[AgentConfig] = None) -> Dict:
    config = cfg or load_agent_config()
    url = f"{config.openmemory_url.rstrip('/')}/api/v1/memories/"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload)
            if r.status_code >= 400:
                # Try to parse error JSON, else raise text
                try:
                    detail = r.json()
                except Exception:
                    detail = {"error": r.text}
                raise SubmitError(f"HTTP {r.status_code}: {detail}")
            return r.json()
    except httpx.RequestError as e:
        raise SubmitError(str(e))


def submit_to_openmemory(payload: Dict, cfg: Optional[AgentConfig] = None) -> Dict:
    """Sync wrapper for convenience in CLI."""
    import asyncio

    return asyncio.run(submit_to_openmemory_async(payload, cfg))


def run_once_and_submit(config_path: Optional[str] = None, profile: Optional[str] = None) -> Dict[str, Optional[str]]:
    cfg = load_agent_config(config_path)
    result: Dict[str, Optional[str]] = {"status": None, "error": None}
    try:
        memory_payload = capture_once(cfg, profile=profile, dedupe=TtlLruCache(ttl_seconds=cfg.dedupe_ttl_sec))
        if not memory_payload:
            result["status"] = "skipped"
            return result
        try:
            submit_to_openmemory(memory_payload, cfg)
            result["status"] = "ok"
        except SubmitError as e:
            # enqueue for retry
            queue = PayloadQueue()
            queue.enqueue(memory_payload)
            result["status"] = "queued"
            result["error"] = str(e)
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return result


def drain_queue(config_path: Optional[str] = None, batch_size: int = 25) -> Dict[str, int]:
    cfg = load_agent_config(config_path)
    queue = PayloadQueue()
    processed = 0
    succeeded = 0
    failed = 0

    for pid, payload in queue.dequeue_batch(limit=batch_size):
        processed += 1
        try:
            submit_to_openmemory(payload, cfg)
            queue.mark_success(pid)
            succeeded += 1
        except SubmitError:
            queue.mark_failure(pid)
            failed += 1
    return {"processed": processed, "succeeded": succeeded, "failed": failed}


