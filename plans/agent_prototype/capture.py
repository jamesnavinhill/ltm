from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Optional, Tuple

import httpx
import time
import logging
import threading

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


_LOGGER = logging.getLogger("agent.capture")


def configure_logging(cfg: AgentConfig) -> None:
    if _LOGGER.handlers:
        return
    level = getattr(logging, (getattr(cfg, "log_level", "INFO") or "INFO").upper(), logging.INFO)
    _LOGGER.setLevel(level)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler: logging.Handler
    log_path = getattr(cfg, "log_path", None)
    if log_path:
        handler = logging.FileHandler(log_path, encoding="utf-8")
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    _LOGGER.addHandler(handler)


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
        _LOGGER.debug("capture skipped: profile filters rejected window")
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
        _LOGGER.debug("capture skipped: OCR produced empty text")
        return None

    ocr_hash = compute_text_hash(normalized)
    if dedupe and dedupe.seen(ocr_hash):
        _LOGGER.debug("capture skipped: dedupe hash seen recently")
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
    _LOGGER.info(
        "capture accepted: app=%s title=%s process=%s hash=%s",
        chosen_profile.app,
        (title or "")[:120],
        proc or "",
        ocr_hash[:8],
    )
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
    configure_logging(cfg)
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


def _active_window_signature() -> Optional[str]:
    title, proc = _get_active_window_info()
    if title is None and proc is None:
        return None
    return f"{title}|{proc}"


def loop_foreground_changes(config_path: Optional[str] = None) -> None:
    """Capture loop that runs when the foreground window changes.

    Polls every `capture_interval_sec`. Uses dedupe cache and profile filters.
    """
    cfg = load_agent_config(config_path)
    configure_logging(cfg)
    dedupe = TtlLruCache(ttl_seconds=cfg.dedupe_ttl_sec)
    last_sig: Optional[str] = None
    _LOGGER.info(
        "loop started: foreground_change_only=%s interval=%ss",
        getattr(cfg, "foreground_change_only", True),
        cfg.capture_interval_sec,
    )
    try:
        while True:
            sig = _active_window_signature()
            if sig is None:
                time.sleep(cfg.capture_interval_sec)
                continue
            if not getattr(cfg, "foreground_change_only", True) or sig != last_sig:
                last_sig = sig
                title, proc = _get_active_window_info()
                chosen: Optional[ProfileRoute] = None
                for p in cfg.profiles:
                    if _allowed_by_profile(title, proc, p):
                        chosen = p
                        break
                if chosen is None:
                    _LOGGER.debug("loop skipped: no matching profile for active window")
                else:
                    payload = capture_once(cfg, profile=chosen.app, dedupe=dedupe)
                    if payload:
                        try:
                            submit_to_openmemory(payload, cfg)
                        except SubmitError as e:
                            queue = PayloadQueue()
                            queue.enqueue(payload)
                            _LOGGER.warning("submit queued: %s", str(e))
            time.sleep(cfg.capture_interval_sec)
    except KeyboardInterrupt:
        _LOGGER.info("loop interrupted by user")


def run_hotkey_listener(config_path: Optional[str] = None) -> None:
    """Register global hotkeys from config to trigger immediate capture per profile."""
    cfg = load_agent_config(config_path)
    configure_logging(cfg)
    try:
        import keyboard  # type: ignore
    except Exception as e:  # pragma: no cover
        _LOGGER.error("keyboard library not installed. Install with: pip install keyboard (%s)", e)
        raise

    dedupe = TtlLruCache(ttl_seconds=cfg.dedupe_ttl_sec)
    capture_lock = threading.Lock()

    def trigger_capture_for_profile(profile_app: str) -> None:
        with capture_lock:
            payload = capture_once(cfg, profile=profile_app, dedupe=dedupe)
            if payload:
                try:
                    submit_to_openmemory(payload, cfg)
                    _LOGGER.info("hotkey capture submitted: app=%s", profile_app)
                except SubmitError as e:
                    queue = PayloadQueue()
                    queue.enqueue(payload)
                    _LOGGER.warning("hotkey submit queued: %s", str(e))
            else:
                _LOGGER.debug("hotkey capture skipped by filters/dedupe/empty text")

    registered = 0
    for p in cfg.profiles:
        if p.hotkey:
            try:
                keyboard.add_hotkey(p.hotkey, lambda app=p.app: trigger_capture_for_profile(app))
                _LOGGER.info("registered hotkey '%s' for app=%s", p.hotkey, p.app)
                registered += 1
            except Exception as e:
                _LOGGER.error("failed to register hotkey '%s': %s", p.hotkey, e)

    if registered == 0:
        _LOGGER.warning("no hotkeys configured; nothing to listen for")
        return

    _LOGGER.info("hotkey listener running. Press Ctrl+C to stop.")
    try:
        keyboard.wait()
    except KeyboardInterrupt:
        _LOGGER.info("hotkey listener interrupted by user")


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


