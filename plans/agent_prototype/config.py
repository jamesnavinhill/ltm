from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tomllib  # py311+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


@dataclasses.dataclass
class ProfileRoute:
    hotkey: Optional[str] = None
    app: str = "work"
    whitelist_titles: List[str] = dataclasses.field(default_factory=list)
    whitelist_processes: List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class AgentConfig:
    openmemory_url: str = "http://localhost:8765"
    user_id: str = os.environ.get("USER", "default_user")
    profiles: List[ProfileRoute] = dataclasses.field(default_factory=lambda: [ProfileRoute(app="work")])
    capture_interval_sec: int = 15
    dedupe_ttl_sec: int = 300
    debug_keep_png: bool = False
    tesseract_path: Optional[str] = None
    mem0_infer: bool = True
    mem0_fallback: bool = False

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "AgentConfig":
        profiles_data = data.get("profiles", []) or []
        profiles = [
            ProfileRoute(
                hotkey=p.get("hotkey"),
                app=p.get("app", "work"),
                whitelist_titles=p.get("whitelist_titles", []) or [],
                whitelist_processes=p.get("whitelist_processes", []) or [],
            )
            for p in profiles_data
        ]
        return AgentConfig(
            openmemory_url=str(data.get("openmemory_url", "http://localhost:8765")),
            user_id=str(data.get("user_id", os.environ.get("USER", "default_user"))),
            profiles=profiles if profiles else [ProfileRoute(app="work")],
            capture_interval_sec=int(data.get("capture_interval_sec", 15)),
            dedupe_ttl_sec=int(data.get("dedupe_ttl_sec", 300)),
            debug_keep_png=bool(data.get("debug_keep_png", False)),
            tesseract_path=data.get("tesseract_path"),
            mem0_infer=bool(data.get("mem0_infer", True)),
            mem0_fallback=bool(data.get("mem0_fallback", False)),
        )


def _read_yaml(path: Path) -> Dict[str, Any]:
    if yaml is None:
        raise RuntimeError("pyyaml is required to read YAML config. Install pyyaml.")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _read_toml(path: Path) -> Dict[str, Any]:
    if tomllib is None:
        raise RuntimeError("tomllib unavailable. Use Python 3.11+ or install tomli.")
    with path.open("rb") as f:
        return tomllib.load(f) or {}


def load_agent_config(config_path: Optional[str] = None) -> AgentConfig:
    if not config_path:
        # prefer local dev path under plans/agent_prototype/agent.config.yaml
        default_yaml = Path(__file__).parent / "agent.config.yaml"
        default_toml = Path(__file__).parent / "agent.config.toml"
        if default_yaml.exists():
            return AgentConfig.from_dict(_read_yaml(default_yaml))
        if default_toml.exists():
            return AgentConfig.from_dict(_read_toml(default_toml))
        return AgentConfig()  # defaults

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    if path.suffix.lower() in {".yaml", ".yml"}:
        return AgentConfig.from_dict(_read_yaml(path))
    if path.suffix.lower() == ".toml":
        return AgentConfig.from_dict(_read_toml(path))
    raise ValueError("Unsupported config format. Use YAML or TOML.")


