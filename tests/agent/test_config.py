from __future__ import annotations

import tempfile
from pathlib import Path

from plans.agent_prototype.config import AgentConfig, load_agent_config


def test_from_dict_parses_profiles_and_defaults():
    data = {
        "openmemory_url": "http://test:1234",
        "user_id": "alice",
        "profiles": [
            {"hotkey": "ctrl+alt+w", "app": "work", "whitelist_titles": ["Code"], "whitelist_processes": ["Code.exe"]},
            {"hotkey": "ctrl+alt+p", "app": "personal"},
        ],
        "capture_interval_sec": 5,
        "dedupe_ttl_sec": 60,
        "debug_keep_png": True,
        "tesseract_path": None,
        "mem0_infer": True,
        "mem0_fallback": False,
        "log_path": None,
        "log_level": "DEBUG",
        "foreground_change_only": True,
    }
    cfg = AgentConfig.from_dict(data)
    assert cfg.openmemory_url.endswith(":1234")
    assert cfg.user_id == "alice"
    assert len(cfg.profiles) == 2
    assert cfg.profiles[0].app == "work"
    assert cfg.capture_interval_sec == 5
    assert cfg.log_level == "DEBUG"


def test_load_agent_config_yaml_roundtrip(tmp_path: Path):
    yaml_content = (
        "openmemory_url: 'http://localhost:8765'\n"
        "user_id: 'bob'\n"
        "profiles:\n"
        "  - hotkey: 'ctrl+alt+b'\n"
        "    app: 'work'\n"
    )
    cfg_path = tmp_path / "agent.config.yaml"
    cfg_path.write_text(yaml_content, encoding="utf-8")
    cfg = load_agent_config(str(cfg_path))
    assert cfg.user_id == "bob"
    assert cfg.profiles[0].app == "work"


