"""Generate the code-derived parts of the docs.

- docs/cli.md: every command and option, from the Click definitions.
- docs/rules.md: the per-pack summary tables between GENERATED markers.

Run `uv run python scripts/gen_docs.py` after changing commands or rules.
`--check` exits 1 if the committed docs are out of date (used by the tests).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parents[1]
RULES_MD = ROOT / "docs" / "rules.md"
CLI_MD = ROOT / "docs" / "cli.md"

PACK_ORDER = ["universal", "quality", "python", "frontend", "react", "seo", "security", "autopilot"]
PACK_ACTIVATION = {
    "universal": "Always active",
    "quality": "Always active",
    "python": "Auto: `pyproject.toml` or `setup.py`",
    "frontend": "Auto: `package.json`",
    "react": "Auto: `react` in `package.json` dependencies",
    "seo": "Auto: an SSR/SSG framework in `package.json` (Next.js, Nuxt, Astro, ...)",
    "security": "Opt-in",
    "autopilot": "Opt-in, experimental",
}
_BEGIN = "<!-- BEGIN GENERATED: {name} (scripts/gen_docs.py) -->"
_END = "<!-- END GENERATED: {name} -->"


def _rules():
    from agentlint.packs import PACK_MODULES, load_rules

    return load_rules(list(PACK_MODULES))


def _events(rule) -> str:
    return ", ".join(e.value for e in rule.events)


def pack_table(pack: str) -> str:
    rows = sorted((r for r in _rules() if r.pack == pack), key=lambda r: r.id)
    lines = [
        "| Rule | Severity | Events | What it does |",
        "|------|----------|--------|--------------|",
    ]
    for r in rows:
        description = r.description.rstrip(".").replace("|", "\\|")
        lines.append(
            f"| [`{r.id}`](#{r.id}) | {r.severity.value.upper()} | {_events(r)} | {description} |"
        )
    return "\n".join(lines)


def overview_table() -> str:
    counts: dict[str, int] = {}
    for r in _rules():
        counts[r.pack] = counts.get(r.pack, 0) + 1
    lines = ["| Pack | Rules | Activation |", "|------|-------|------------|"]
    for pack in PACK_ORDER:
        lines.append(f"| [{pack}](#{pack}) | {counts.get(pack, 0)} | {PACK_ACTIVATION[pack]} |")
    lines.append(f"| **Total** | **{sum(counts.values())}** | |")
    return "\n".join(lines)


def _replace_block(text: str, name: str, body: str) -> str:
    begin, end = _BEGIN.format(name=name), _END.format(name=name)
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(text):
        raise SystemExit(f"docs/rules.md is missing the '{name}' generated block")
    return pattern.sub(lambda _: f"{begin}\n{body}\n{end}", text)


def render_rules(text: str) -> str:
    text = _replace_block(text, "overview", overview_table())
    for pack in PACK_ORDER:
        text = _replace_block(text, f"pack-{pack}", pack_table(pack))
    return text


def _command_help(command: click.Command, path: list[str]) -> str:
    ctx = click.Context(command, info_name=" ".join(path), max_content_width=88, terminal_width=88)
    return command.get_help(ctx)


def _walk(command: click.Command, path: list[str]):
    yield path, command
    if isinstance(command, click.Group):
        for name in sorted(command.commands):
            sub = command.commands[name]
            if sub.hidden:
                continue
            yield from _walk(sub, [*path, name])


def render_cli() -> str:
    from agentlint.cli import main

    out = [
        "# CLI reference",
        "",
        "Generated from the command definitions by `scripts/gen_docs.py`; do not edit by hand.",
        "Run `agentlint <command> --help` for the same text in your terminal.",
        "",
        "## Commands",
        "",
    ]
    entries = list(_walk(main, ["agentlint"]))[1:]
    for path, command in entries:
        name = " ".join(path)
        anchor = re.sub(r"[^a-z0-9 -]", "", name.lower()).replace(" ", "-")
        summary = (command.get_short_help_str(limit=90) or "").strip()
        out.append(f"- [`{name}`](#{anchor}) — {summary}")
    out.append("")
    for path, command in entries:
        name = " ".join(path)
        out += [f"## {name}", "", "```text", _command_help(command, path).rstrip(), "```", ""]
    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    rules_current = RULES_MD.read_text()
    rules_new = render_rules(rules_current)
    cli_new = render_cli()
    cli_current = CLI_MD.read_text() if CLI_MD.exists() else ""
    stale = [
        p.name
        for p, old, new in ((RULES_MD, rules_current, rules_new), (CLI_MD, cli_current, cli_new))
        if old != new
    ]
    if check:
        if stale:
            print(f"Out of date: {', '.join(stale)}. Run: uv run python scripts/gen_docs.py")
            return 1
        return 0
    RULES_MD.write_text(rules_new)
    CLI_MD.write_text(cli_new)
    print("Updated:", ", ".join(stale) or "nothing (already current)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
