"""AgentChute credential and setting resolution.

Environment variables still win, but ``agentlint login`` also writes a local
credential file so the current shell can use AgentChute immediately.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ENV_AGENTCHUTE_ENABLED = "AGENTCHUTE_ENABLED"
ENV_AGENTCHUTE_LICENSE_KEY = "AGENTCHUTE_LICENSE_KEY"
ENV_AGENTCHUTE_API_URL = "AGENTCHUTE_API_URL"
ENV_AGENTCHUTE_CREDENTIALS_FILE = "AGENTLINT_AGENTCHUTE_CREDENTIALS_FILE"

DEFAULT_API_URL = "https://api.agentchute.com/v1"


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def local_credentials_path() -> Path:
    override = os.environ.get(ENV_AGENTCHUTE_CREDENTIALS_FILE)
    if override:
        return Path(override).expanduser()
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    root = Path(xdg_home).expanduser() if xdg_home else Path.home() / ".config"
    return root / "agentlint" / "agentchute.json"


def load_local_credentials() -> dict[str, Any]:
    path = local_credentials_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_local_credentials(
    *, api_url: str, license_key: str, enabled: bool = True
) -> Path:
    path = local_credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "api_url": api_url.rstrip("/"),
        "enabled": enabled,
        "license_key": license_key,
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def get_license_key() -> str | None:
    env_value = os.environ.get(ENV_AGENTCHUTE_LICENSE_KEY)
    if env_value:
        return env_value
    local_value = load_local_credentials().get("license_key")
    if isinstance(local_value, str) and local_value.strip():
        return local_value.strip()
    return None


def get_api_url() -> str:
    env_value = os.environ.get(ENV_AGENTCHUTE_API_URL)
    if env_value:
        return env_value.rstrip("/")
    local_value = load_local_credentials().get("api_url")
    if isinstance(local_value, str) and local_value.strip():
        return local_value.strip().rstrip("/")
    return DEFAULT_API_URL


def get_enabled_value(config: Any | None = None) -> bool:
    env_value = _parse_bool(os.environ.get(ENV_AGENTCHUTE_ENABLED))
    if env_value is not None:
        return env_value

    local_value = _parse_bool(load_local_credentials().get("enabled"))
    if local_value is not None:
        return local_value

    if config is not None:
        agentchute_cfg = getattr(config, "agentchute", None)
        if isinstance(agentchute_cfg, dict) and "enabled" in agentchute_cfg:
            return bool(agentchute_cfg.get("enabled", False))

    return False


def has_agentchute_credentials() -> bool:
    return get_license_key() is not None


def is_agentchute_enabled(config: Any | None = None) -> bool:
    return bool(get_license_key()) and get_enabled_value(config)
