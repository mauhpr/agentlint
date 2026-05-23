"""Rule: block exact critical NVD CVE matches from cached AgentChute data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.utils.bash import strip_string_args

_BASH_TOOLS = {"Bash"}
_INSTALL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(?:npm|yarn|pnpm)\s+(?:install|i|add)\s+(?!-)"
        r"(?P<name>@?[\w][\w@/\-.]*)@(?P<version>[\w][\w\-+.~:]*)", re.I,
    ),
    re.compile(
        r"\bpip3?\s+install\s+(?!-)"
        r"(?P<name>[\w][\w\-.]*)==(?P<version>[\w][\w\-+.~:]*)", re.I,
    ),
    re.compile(
        r"\bcargo\s+(?:add|install)\s+(?!-)"
        r"(?P<name>[\w][\w\-.]*)\s+--version\s+(?P<version>[\w][\w\-+.~:]*)", re.I,
    ),
    re.compile(
        r"\b(?:apt|apt-get)\s+install\s+(?:-[\w-]+\s+)*"
        r"(?P<name>[\w][\w+.-]*)=(?P<version>[\w][\w\-+.~:]*)", re.I,
    ),
]
_DOCKER_IMAGE = re.compile(
    r"\bdocker\s+(?:pull|run|create)\s+(?:-[\w-]+(?:\s+\S+)?\s+)*"
    r"(?P<image>[\w./:-]+:[\w][\w.\-+_]*)", re.I,
)
_SEPARATORS = re.compile(r"[\s_.]+")


@dataclass(frozen=True)
class VersionedArtifact:
    product: str
    version: str


def _normalize_product(value: str) -> str:
    value = value.strip().lower().replace("\\", "").replace("@", "")
    value = _SEPARATORS.sub("-", value)
    return re.sub(r"[^a-z0-9/-]+", "-", value).strip("-")


def _version_variants(value: str) -> set[str]:
    raw = value.strip().lower().replace("\\", "")
    if not raw or raw in {"*", "-", "na", "n/a"}:
        return set()
    variants = {raw, raw.lstrip("v")}
    for sep in ("-", "+", "~"):
        if sep in raw:
            variants.add(raw.split(sep, 1)[0].lstrip("v"))
    return {item for item in variants if item}


def _package_name_variants(name: str) -> set[str]:
    normalized = _normalize_product(name)
    if not normalized:
        return set()
    return {normalized, normalized.rsplit("/", 1)[-1]} if "/" in normalized else {normalized}


def _docker_artifact(image: str) -> VersionedArtifact | None:
    if ":" not in image:
        return None
    name, version = image.strip().rsplit(":", 1)
    product = _normalize_product(name.rsplit("/", 1)[-1])
    if not product or not version or version == "latest":
        return None
    return VersionedArtifact(product, version)


def _extract_versioned_artifacts(command: str) -> list[VersionedArtifact]:
    artifacts: list[VersionedArtifact] = []
    for pattern in _INSTALL_PATTERNS:
        for match in pattern.finditer(command):
            version = match.group("version")
            artifacts.extend(
                VersionedArtifact(p, version) for p in _package_name_variants(match.group("name"))
            )
    for match in _DOCKER_IMAGE.finditer(command):
        artifact = _docker_artifact(match.group("image"))
        if artifact is not None:
            artifacts.append(artifact)
    return sorted(set(artifacts), key=lambda item: (item.product, item.version))


def _split_cpe_23(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    escaped = False
    for char in value:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def _cpe_product_versions(cpe: str) -> list[VersionedArtifact]:
    if cpe.startswith("cpe:2.3:"):
        parts = _split_cpe_23(cpe.strip())
        product = _normalize_product(parts[4]) if len(parts) >= 6 else ""
        versions = _version_variants(parts[5]) if len(parts) >= 6 else set()
    elif cpe.startswith("cpe:/"):
        parts = cpe.strip().split(":")
        product = _normalize_product(parts[3]) if len(parts) >= 5 else ""
        versions = _version_variants(parts[4]) if len(parts) >= 5 else set()
    else:
        return []
    return [VersionedArtifact(product, version) for version in versions if product]


def _is_blocking_cve(record: dict[str, Any]) -> bool:
    if str(record.get("severity") or "").upper() == "CRITICAL":
        return True
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    cisa = metadata.get("cisa") if isinstance(metadata, dict) else {}
    return isinstance(cisa, dict) and bool(cisa)


def _critical_cpe_index(records: list[Any]) -> dict[VersionedArtifact, list[dict[str, Any]]]:
    index: dict[VersionedArtifact, list[dict[str, Any]]] = {}
    for record in records:
        if not isinstance(record, dict) or not _is_blocking_cve(record):
            continue
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        cpes = metadata.get("cpe_matches") if isinstance(metadata, dict) else []
        for cpe in cpes if isinstance(cpes, list) else []:
            if isinstance(cpe, str):
                for artifact in _cpe_product_versions(cpe):
                    index.setdefault(artifact, []).append(record)
    return index


class NoNvdCriticalCveInstall(Rule):
    id = "no-nvd-critical-cve-install"
    description = (
        "Blocks explicit package installs or container pulls when AgentChute's "
        "cached NVD feed has an exact critical CVE CPE product+version match."
    )
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS or not context.command:
            return []
        artifacts = _extract_versioned_artifacts(strip_string_args(context.command))
        if not artifacts:
            return []
        try:
            from agentlint.agentchute import cloud_feed
        except ImportError:
            return []

        feed_data = cloud_feed.get("nvd-cves", default={"records": []}, allow_network=False)
        records = feed_data.get("records") if isinstance(feed_data, dict) else []
        index = _critical_cpe_index(records) if isinstance(records, list) else {}
        violations: list[Violation] = []
        for artifact in artifacts:
            matches = [
                record
                for version in _version_variants(artifact.version)
                for record in index.get(VersionedArtifact(artifact.product, version), [])
            ]
            if matches:
                violations.append(self._violation(artifact, matches[0]))
        return violations

    def _violation(self, artifact: VersionedArtifact, record: dict[str, Any]) -> Violation:
        cve_id = record.get("cve_id") or "CVE"
        severity = record.get("severity") or "UNKNOWN"
        summary = str(record.get("summary") or "").strip()
        suffix = f" — {summary}" if summary else ""
        return Violation(
            rule_id=self.id,
            message=(
                f"{artifact.product}@{artifact.version} matches {cve_id} "
                f"in the cached NVD feed (severity: {severity}){suffix}"
            ),
            severity=self.severity,
            suggestion=("Use a fixed version or verify the artifact is not the affected product. "
                        "NVD CPE matches are exact local cache matches; refresh with "
                        "`agentlint policy refresh` if needed."),
        )
