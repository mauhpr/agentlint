"""Cached AgentChute org policy and declarative policy rules."""
from __future__ import annotations

import fnmatch
import json
import logging
import os
import time
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any

from agentlint.agentchute.client import (
    DEFAULT_API_URL,
    ENV_AGENTCHUTE_API_URL,
    ENV_AGENTCHUTE_LICENSE_KEY,
    _CONNECT_TIMEOUT_S,
    _READ_TIMEOUT_S,
)
from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

logger = logging.getLogger("agentlint.agentchute.policy")

_MAX_POLICY_BYTES = 512 * 1024
_SUPPORTED_OPERATORS = {
    "equals",
    "contains",
    "starts_with",
    "ends_with",
    "glob",
    "path_under",
    "command_verb",
    "package_name",
}


def _policy_root() -> Path:
    return Path(
        os.environ.get("AGENTLINT_AGENTCHUTE_POLICY_DIR", "~/.cache/agentlint/agentchute")
    ).expanduser()


def _policy_path() -> Path:
    return _policy_root() / "policy.json"


def _meta_path() -> Path:
    return _policy_root() / "policy-meta.json"


def load_cached_policy() -> dict | None:
    path = _policy_path()
    if not path.exists():
        return None
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        _write_meta({"error": f"invalid cached policy: {e}", "checked_at": time.time()})
        return None
    errors = validate_policy(policy)
    if errors:
        _write_meta({"error": "; ".join(errors), "checked_at": time.time()})
        return None
    return policy


@dataclass
class PolicyRefreshResult:
    ok: bool
    version: int | None = None
    error: str | None = None


def refresh_policy() -> PolicyRefreshResult:
    license_key = os.environ.get(ENV_AGENTCHUTE_LICENSE_KEY)
    if not license_key:
        return PolicyRefreshResult(ok=False, error="AGENTCHUTE_LICENSE_KEY not set")

    api_url = os.environ.get(ENV_AGENTCHUTE_API_URL, DEFAULT_API_URL).rstrip("/")
    meta = _read_meta()
    headers = {
        "Authorization": f"Bearer {license_key}",
        "User-Agent": "agentlint/agentchute/policy",
        "Accept": "application/json",
    }
    if meta.get("etag"):
        headers["If-None-Match"] = meta["etag"]

    try:
        import requests
    except ImportError:
        return PolicyRefreshResult(ok=False, error="requests not installed")

    try:
        response = requests.get(
            f"{api_url}/policy",
            headers=headers,
            timeout=(_CONNECT_TIMEOUT_S, _READ_TIMEOUT_S),
        )
    except Exception as e:  # noqa: BLE001
        return PolicyRefreshResult(ok=False, error=str(e))

    if response.status_code == 304:
        cached = load_cached_policy()
        return PolicyRefreshResult(ok=True, version=(cached or {}).get("version"))
    if response.status_code != 200:
        return PolicyRefreshResult(ok=False, error=f"HTTP {response.status_code}")
    if len(response.content) > _MAX_POLICY_BYTES:
        return PolicyRefreshResult(ok=False, error="policy payload too large")

    try:
        policy = response.json()
    except ValueError:
        return PolicyRefreshResult(ok=False, error="policy response is not JSON")

    errors = validate_policy(policy)
    if errors:
        return PolicyRefreshResult(ok=False, error="; ".join(errors))

    _policy_root().mkdir(parents=True, exist_ok=True)
    _policy_path().write_text(json.dumps(policy, sort_keys=True), encoding="utf-8")
    _write_meta({
        "etag": response.headers.get("ETag"),
        "fetched_at": time.time(),
        "version": policy.get("version"),
        "updated_at": policy.get("updated_at"),
        "error": None,
    })
    return PolicyRefreshResult(ok=True, version=policy.get("version"))


def policy_status() -> dict:
    meta = _read_meta()
    cached = load_cached_policy()
    return {
        "cached": cached is not None,
        "version": (cached or {}).get("version") or meta.get("version"),
        "updated_at": (cached or {}).get("updated_at") or meta.get("updated_at"),
        "error": meta.get("error"),
    }


def validate_policy(policy: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(policy, dict):
        return ["policy must be an object"]
    if "version" in policy and not isinstance(policy["version"], int):
        errors.append("version must be an integer")
    rules = policy.get("rules", [])
    if not isinstance(rules, list):
        errors.append("rules must be a list")
        return errors
    if len(rules) > 200:
        errors.append("rules must contain at most 200 entries")
    for i, rule in enumerate(rules):
        prefix = f"rules[{i}]"
        if not isinstance(rule, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if not isinstance(rule.get("id"), str) or not rule["id"]:
            errors.append(f"{prefix}.id is required")
        if rule.get("tool") == "Any":
            errors.append(f"{prefix}.tool must be omitted to match any tool")
        if rule.get("severity", "warning") not in {"error", "warning", "info"}:
            errors.append(f"{prefix}.severity is invalid")
        if rule.get("event") and rule["event"] not in {e.value for e in HookEvent}:
            errors.append(f"{prefix}.event is invalid")
        match = rule.get("match")
        if not isinstance(match, dict):
            errors.append(f"{prefix}.match is required")
            continue
        if match.get("operator") not in _SUPPORTED_OPERATORS:
            errors.append(f"{prefix}.match.operator is unsupported")
        if not isinstance(match.get("field"), str) or not match["field"]:
            errors.append(f"{prefix}.match.field is required")
        if not isinstance(match.get("value"), (str, int, float, bool)):
            errors.append(f"{prefix}.match.value must be scalar")
    packs = policy.get("required_packs", [])
    if packs and not isinstance(packs, list):
        errors.append("required_packs must be a list")
    return errors


def build_policy_rules(policy: dict | None = None) -> list[Rule]:
    policy = policy if policy is not None else load_cached_policy()
    if not policy:
        return []
    rules: list[Rule] = []
    for raw in policy.get("rules") or []:
        if raw.get("source", "declarative") != "declarative":
            continue
        if raw.get("enabled", True) is False:
            continue
        try:
            rules.append(DeclarativePolicyRule(raw))
        except Exception:
            logger.debug("agentlint.agentchute.policy: skipped invalid policy rule", exc_info=True)
    return rules


def required_packs(policy: dict | None = None) -> list[dict]:
    policy = policy if policy is not None else load_cached_policy()
    if not policy:
        return []
    packs = policy.get("required_packs") or []
    return [p for p in packs if isinstance(p, dict) and (p.get("name") or p.get("id"))]


def missing_required_packs(policy: dict | None = None) -> list[str]:
    missing: list[str] = []
    for pack in required_packs(policy):
        if pack.get("type") == "cloud_feed" or pack.get("managed_by") == "agentchute":
            continue
        name = str(pack.get("name") or "")
        if not name:
            continue
        try:
            package_version(name)
        except PackageNotFoundError:
            missing.append(name)
    return missing


class DeclarativePolicyRule(Rule):
    pack = "universal"

    def __init__(self, raw: dict):
        self.raw = raw
        self.id = str(raw["id"])
        self.description = str(raw.get("description") or raw.get("message") or self.id)
        self.severity = Severity(str(raw.get("severity", "warning")))
        event = raw.get("event")
        self.events = [HookEvent.from_string(event)] if event else list(HookEvent)
        self.locked = bool(raw.get("locked", False))

    def evaluate(self, context: RuleContext) -> list[Violation]:
        tool = self.raw.get("tool")
        if tool and tool != context.tool_name:
            return []
        if not _matches(context, self.raw.get("match") or {}):
            return []
        return [
            Violation(
                rule_id=self.id,
                message=str(self.raw.get("message") or self.description),
                severity=self.severity,
                file_path=context.file_path,
                suggestion=self.raw.get("suggestion"),
            )
        ]


def _matches(context: RuleContext, match: dict) -> bool:
    field = str(match.get("field") or "")
    operator = str(match.get("operator") or "")
    expected = str(match.get("value") or "")
    actual = _field_value(context, field)
    actual_s = "" if actual is None else str(actual)

    if operator == "equals":
        return actual_s == expected
    if operator == "contains":
        return expected in actual_s
    if operator == "starts_with":
        return actual_s.startswith(expected)
    if operator == "ends_with":
        return actual_s.endswith(expected)
    if operator == "glob":
        return fnmatch.fnmatch(actual_s, expected)
    if operator == "path_under":
        path = actual_s.replace("\\", "/")
        root = expected.rstrip("/").replace("\\", "/")
        return path == root or path.startswith(root + "/")
    if operator == "command_verb":
        return (actual_s.strip().split() or [""])[0] == expected
    if operator == "package_name":
        return actual_s.lower() == expected.lower()
    return False


def _field_value(context: RuleContext, field: str) -> Any:
    if field == "command":
        return context.command
    if field == "file_path":
        return context.file_path
    if field == "tool_name":
        return context.tool_name
    if field == "event":
        return context.event.value
    if field == "prompt":
        return context.prompt
    if field.startswith("tool_input."):
        value: Any = context.tool_input
        for part in field.split(".")[1:]:
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value
    return context.tool_input.get(field)


def _read_meta() -> dict:
    try:
        return json.loads(_meta_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_meta(meta: dict) -> None:
    _policy_root().mkdir(parents=True, exist_ok=True)
    _meta_path().write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")
