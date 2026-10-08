"""Docs stay in sync with the code: generated pages, rule coverage, links."""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _gen_docs():
    spec = importlib.util.spec_from_file_location("gen_docs", ROOT / "scripts" / "gen_docs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_docs_are_current():
    assert _gen_docs().main(["--check"]) == 0, "Run: uv run python scripts/gen_docs.py"


def test_every_rule_has_a_section():
    from agentlint.packs import PACK_MODULES, load_rules

    text = (ROOT / "docs" / "rules.md").read_text()
    missing = [r.id for r in load_rules(list(PACK_MODULES)) if f"### `{r.id}`" not in text]
    assert missing == []


def _slug(heading: str) -> str:
    """GitHub-style heading anchor."""
    text = heading.strip().lower()
    text = re.sub(r"[`*~]", "", text)
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    in_code = False
    for line in path.read_text().splitlines():
        if line.startswith("```"):
            in_code = not in_code
        if in_code:
            continue
        match = re.match(r"^#{1,6}\s+(.*)$", line)
        if match:
            slug = _slug(match.group(1))
            n = counts.get(slug, 0)
            counts[slug] = n + 1
            anchors.add(slug if n == 0 else f"{slug}-{n}")
    return anchors


_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _markdown_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "*.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [ROOT / p for p in [*out, *untracked] if (ROOT / p).exists()]


def test_relative_links_and_anchors_resolve():
    broken = []
    for path in _markdown_files():
        in_code = False
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if line.startswith("```"):
                in_code = not in_code
            if in_code:
                continue
            for target in _LINK.findall(line):
                if re.match(r"^[a-z]+:", target) or target.startswith("<"):
                    continue
                file_part, _, anchor = target.partition("#")
                dest = (path.parent / file_part).resolve() if file_part else path
                if not dest.exists():
                    broken.append(f"{path.relative_to(ROOT)}:{number} -> {target}")
                elif anchor and dest.suffix == ".md" and anchor not in _anchors(dest):
                    broken.append(f"{path.relative_to(ROOT)}:{number} -> {target} (no anchor)")
    assert broken == []
