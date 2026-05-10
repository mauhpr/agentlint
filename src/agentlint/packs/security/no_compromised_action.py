"""Rule: block GitHub Actions ``uses:`` references whose action is
in the GHSA Actions advisory feed.

Hybrid rule (Phase 19, security pack). Catches the supply-chain
attack pattern where a popular Action (e.g. ``tj-actions/changed-files``)
is hijacked and the workflow author hasn't yet pinned to a known-safe
SHA or upgraded past the advisory's fix.

Detection scope:
    Only Edit/Write tools targeting files under ``.github/workflows/``
    (or with a ``.yml``/``.yaml`` extension that LOOKS like a workflow).
    The rule extracts every ``uses: owner/repo@ref`` from the new
    content and looks each up in the ``compromised-actions`` feed.

Version handling:
    Workflow refs come in three forms:
    1. ``uses: tj-actions/changed-files@v44``   (tag — recommended)
    2. ``uses: tj-actions/changed-files@<40-char SHA>``  (pinned)
    3. ``uses: tj-actions/changed-files``         (master — bad)

    We compare the ref against the advisory's vulnerable version
    range using the same crude semver tuple-compare from
    ``no-vulnerable-version-install``. SHA refs always fire a WARNING
    (we can't tell from the SHA alone whether it's affected, but a
    SHA pin means the workflow author trusts that exact commit — the
    advisory is at minimum worth surfacing).

Self-degrading: when AgentChute isn't configured, the rule is a no-op.
"""

from __future__ import annotations

import re
from typing import Any

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation


_FILE_TOOLS = {"Edit", "Write"}


# Match `uses: owner/repo@ref` lines in YAML. Owner+repo allow letters,
# digits, dashes, dots, underscores; ref can be a tag, branch, or SHA.
# Action references can also be local (``./.github/actions/foo``) or
# Docker (``docker://image``) — we skip those.
_USES_RE = re.compile(
    r"""\buses\s*:\s*(?:["']?)([a-zA-Z0-9][\w\-\.]*\/[a-zA-Z0-9][\w\-\.]*)(?:@([\w\-\.\/]+))?(?:["']?)""",
    re.MULTILINE,
)


def _looks_like_workflow(file_path: str | None, content: str) -> bool:
    """Best-effort: is this an Actions workflow file?"""
    if file_path:
        path_lower = file_path.lower()
        if ".github/workflows/" in path_lower:
            return True
        if path_lower.endswith((".yml", ".yaml")) and "uses:" in content:
            return True
    # No path? Heuristic: presence of GitHub-specific top-level keys
    if "uses:" in content and ("on:" in content or "jobs:" in content):
        return True
    return False


def _extract_uses(content: str) -> list[tuple[str, str | None]]:
    """Return ``[(owner/repo, ref_or_None), ...]`` extracted from the
    content. Skips local (./...) and docker:// refs implicitly because
    they don't match the regex's owner/repo shape."""
    out: list[tuple[str, str | None]] = []
    seen: set[tuple[str, str | None]] = set()
    for match in _USES_RE.finditer(content):
        repo = match.group(1)
        ref = match.group(2)
        # Defensive: skip relative-path style refs (e.g. ``./local``)
        if "/" not in repo or repo.startswith("./") or repo.startswith("../"):
            continue
        # Cap on length defensively
        if len(repo) > 200:
            continue
        key = (repo, ref)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


# ---------- Version comparison (mirror of no-vulnerable-version-install) ----------


_INT_PART = re.compile(r"\d+")


def _parse_version(v: str) -> tuple[int, ...]:
    if not v:
        return (0,)
    cleaned = v.lstrip("vV")
    parts = _INT_PART.findall(cleaned)
    if not parts:
        return (0,)
    return tuple(int(p) for p in parts[:6])


def _ref_looks_like_sha(ref: str) -> bool:
    """40-char hex string = git SHA (full pin). Workflow authors who
    use SHA pins typically did so deliberately — we still WARN on
    advisories that affect the action overall."""
    return bool(ref) and len(ref) == 40 and all(c in "0123456789abcdef" for c in ref.lower())


def _version_in_range(
    version: tuple[int, ...], events: list[dict[str, Any]]
) -> bool:
    introduced: tuple[int, ...] | None = None
    fixed: tuple[int, ...] | None = None
    last_affected: tuple[int, ...] | None = None
    for ev in events:
        if "introduced" in ev:
            introduced = _parse_version(ev["introduced"])
        elif "fixed" in ev:
            fixed = _parse_version(ev["fixed"])
        elif "last_affected" in ev:
            last_affected = _parse_version(ev["last_affected"])

    if introduced is not None and version < introduced:
        return False
    if fixed is not None and version >= fixed:
        return False
    if last_affected is not None and version > last_affected:
        return False
    return True


def _matches_any_range(version: tuple[int, ...], ranges: Any) -> bool:
    if not isinstance(ranges, list):
        return False
    for r in ranges:
        if not isinstance(r, dict):
            continue
        events = r.get("events")
        if not isinstance(events, list):
            continue
        if _version_in_range(version, events):
            return True
    return False


class NoCompromisedAction(Rule):
    """Block GitHub Actions ``uses:`` of an action with active GHSA
    advisories. Self-degrades to no-op when AgentChute isn't configured.
    """

    id = "no-compromised-action"
    description = (
        "Blocks GitHub Actions `uses: <owner/repo>@<ref>` in workflow "
        "files when the action has open GHSA advisories. Self-degrades "
        "to no-op when AgentChute is not configured."
    )
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "security"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _FILE_TOOLS:
            return []

        content = (
            context.tool_input.get("new_string")
            or context.tool_input.get("content")
            or ""
        )
        if not content:
            return []

        file_path = context.tool_input.get("file_path") or context.file_path
        if not _looks_like_workflow(file_path, content):
            return []

        uses_list = _extract_uses(content)
        if not uses_list:
            return []

        try:
            from agentlint.agentchute import cloud_feed
        except ImportError:
            return []

        feed_data = cloud_feed.get(
            "compromised-actions", default={"actions": []}, allow_network=False
        )
        if not isinstance(feed_data, dict):
            return []
        actions: list[dict[str, Any]] = feed_data.get("actions") or []
        if not actions:
            return []

        # Index by repo (lowercased) for O(1) lookup
        index: dict[str, list[dict[str, Any]]] = {}
        for rec in actions:
            if not isinstance(rec, dict):
                continue
            repo = (rec.get("repo") or "").lower()
            if not repo:
                continue
            index.setdefault(repo, []).append(rec)

        violations: list[Violation] = []
        for repo, ref in uses_list:
            advisories = index.get(repo.lower())
            if not advisories:
                continue

            sha_pin = bool(ref) and _ref_looks_like_sha(ref)

            # If we can't compute a tuple version (SHA pin or no ref),
            # still surface the most-severe advisory as a violation.
            # The user might have intentionally pinned to a known-safe
            # SHA, but the alert is still actionable.
            if sha_pin or not ref:
                best = advisories[0]
            else:
                version = _parse_version(ref)
                # Find a matching advisory by version range
                hit = None
                for rec in advisories:
                    if _matches_any_range(version, rec.get("vulnerable_versions")):
                        hit = rec
                        break
                if hit is None:
                    # ref is past the fix range — safe, skip
                    continue
                best = hit

            ghsa = best.get("ghsa_id", "GHSA-?")
            sev = best.get("severity") or "UNKNOWN"
            summary = (best.get("summary") or "").strip()
            suffix = f" — {summary}" if summary else ""
            ref_label = ref if ref else "(no ref)"
            violations.append(
                Violation(
                    rule_id=self.id,
                    message=(
                        f"GitHub Actions `uses: {repo}@{ref_label}` — open "
                        f"advisory {ghsa} (severity: {sev}){suffix}"
                    ),
                    severity=self.severity,
                    file_path=file_path,
                    suggestion=(
                        f"Upgrade {repo} to a version outside the affected "
                        f"range, or pin to a SHA you've verified is past "
                        f"the fix. See the GHSA references for the fix "
                        f"version."
                    ),
                )
            )

        return violations
