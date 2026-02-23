"""AGENTS.md parser and config mapper for AgentLint.

Reads AGENTS.md from a project root, extracts conventions by section headings,
and maps them to AgentLint configuration (packs, rules, severity).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger("agentlint")

# Canonical AGENTS.md file names (case-insensitive search).
AGENTS_MD_FILENAMES = ["AGENTS.md", "agents.md", "Agents.md"]

# Section keywords → pack/rule mapping.
_PACK_KEYWORDS: dict[str, list[str]] = {
    "python": ["python", "pip", "pyproject", "pytest", "django", "flask", "fastapi", "poetry", "uv"],
    "frontend": ["frontend", "css", "html", "javascript", "typescript", "webpack", "vite", "eslint", "prettier"],
    "react": ["react", "jsx", "tsx", "next.js", "nextjs", "remix", "gatsby"],
    "seo": ["seo", "meta tags", "open graph", "structured data", "sitemap", "lighthouse"],
    "security": ["security", "secrets", "credentials", "api key", "token", "authentication", "vulnerability"],
}

_RULE_KEYWORDS: dict[str, list[str]] = {
    "no-env-commit": [".env", "env file", "environment variable", "dotenv"],
    "commit-message-format": ["commit message", "conventional commit", "commit format", "git commit"],
    "no-destructive-commands": ["destructive", "rm -rf", "force delete", "dangerous command"],
    "no-force-push": ["force push", "force-push", "--force"],
    "no-secrets": ["secret", "api key", "credential", "password", "token", "private key"],
    "no-test-weakening": ["test coverage", "don't skip test", "don't weaken test"],
    "drift-detector": ["test", "testing", "run tests", "test after change"],
}


def find_agents_md(project_dir: str) -> Path | None:
    """Find an AGENTS.md file in the project root."""
    root = Path(project_dir)
    for name in AGENTS_MD_FILENAMES:
        path = root / name
        if path.exists():
            return path
    return None


def parse_agents_md(path: str | Path) -> dict[str, str]:
    """Parse AGENTS.md into sections keyed by heading text.

    Splits on H2 (##) and H3 (###) headings.
    Returns a dict of {heading_text: body_text}.
    """
    path = Path(path)
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("Could not read AGENTS.md at %s", path)
        return {}

    if not content.strip():
        return {}

    sections: dict[str, str] = {}
    current_heading: str | None = None
    current_body: list[str] = []

    for line in content.splitlines():
        heading_match = re.match(r"^(#{2,3})\s+(.+)", line)
        if heading_match:
            # Save previous section.
            if current_heading is not None:
                sections[current_heading] = "\n".join(current_body).strip()
            current_heading = heading_match.group(2).strip()
            current_body = []
        elif current_heading is not None:
            current_body.append(line)

    # Save last section.
    if current_heading is not None:
        sections[current_heading] = "\n".join(current_body).strip()

    return sections


def map_to_config(sections: dict[str, str]) -> dict:
    """Map parsed AGENTS.md sections to AgentLint config.

    Returns a dict suitable for generating agentlint.yml.
    Conservative mapping: only activates packs/rules when keywords clearly match.
    """
    packs: set[str] = {"universal", "quality"}
    rules: dict[str, dict] = {}

    # Combine all section text for keyword scanning.
    all_text = " ".join(
        f"{heading} {body}" for heading, body in sections.items()
    ).lower()

    # Detect packs from keywords.
    for pack_name, keywords in _PACK_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in all_text:
                packs.add(pack_name)
                break

    # Detect rule configurations from keywords.
    for rule_id, keywords in _RULE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in all_text:
                rules[rule_id] = {"enabled": True}
                break

    # Special: if testing keywords found, configure drift-detector.
    testing_keywords = {"test", "testing", "pytest", "jest", "mocha", "vitest"}
    if testing_keywords & set(all_text.split()):
        rules.setdefault("drift-detector", {})["threshold"] = 3

    return {
        "packs": sorted(packs),
        "rules": rules,
    }


def generate_config(mapped: dict) -> str:
    """Generate an agentlint.yml YAML string from mapped config."""
    config = {
        "stack": "auto",
        "severity": "standard",
        "packs": mapped.get("packs", ["universal", "quality"]),
    }

    rules = mapped.get("rules", {})
    if rules:
        config["rules"] = rules

    header = (
        "# AgentLint Configuration\n"
        "# Generated from AGENTS.md — review and adjust as needed\n"
        "# Docs: https://github.com/mauhpr/agentlint\n\n"
    )
    return header + yaml.dump(config, default_flow_style=False, sort_keys=False)


def merge_with_existing(existing_yaml: str, mapped: dict) -> str:
    """Merge AGENTS.md-derived config into existing agentlint.yml content.

    Additive: enables additional packs/rules without removing existing ones.
    """
    try:
        existing = yaml.safe_load(existing_yaml) or {}
    except yaml.YAMLError:
        existing = {}

    # Merge packs (additive).
    existing_packs = set(existing.get("packs", ["universal", "quality"]))
    new_packs = set(mapped.get("packs", []))
    merged_packs = sorted(existing_packs | new_packs)

    # Merge rules (additive, don't overwrite existing rule configs).
    existing_rules = existing.get("rules", {}) or {}
    new_rules = mapped.get("rules", {})
    for rule_id, rule_cfg in new_rules.items():
        if rule_id not in existing_rules:
            existing_rules[rule_id] = rule_cfg

    existing["packs"] = merged_packs
    if existing_rules:
        existing["rules"] = existing_rules

    header = (
        "# AgentLint Configuration\n"
        "# Updated with conventions from AGENTS.md\n"
        "# Docs: https://github.com/mauhpr/agentlint\n\n"
    )
    return header + yaml.dump(existing, default_flow_style=False, sort_keys=False)
