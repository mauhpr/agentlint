"""Rule: audit subagent transcripts for dangerous commands after completion."""
from __future__ import annotations

import json
import logging
import os

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.packs.autopilot._dangerous_patterns import DANGEROUS_PATTERNS

logger = logging.getLogger("agentlint")

# Maximum transcript size to process (1 MB).
_MAX_TRANSCRIPT_BYTES = 1_048_576

# Maximum size for a single JSONL line (100 KB).
_MAX_LINE_BYTES = 100_000


def _extract_bash_commands(transcript_path: str) -> list[str]:
    """Parse a JSONL transcript and extract Bash tool commands.

    Each line in the transcript is a JSON object. We look for tool_use
    entries where the tool name is "Bash" and extract the command.
    """
    commands: list[str] = []
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if len(line) > _MAX_LINE_BYTES:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Claude Code transcript format: look for tool_use content blocks
                # within assistant messages
                _extract_from_entry(entry, commands)
    except OSError as exc:
        logger.warning("Could not read transcript %s: %s", transcript_path, exc)

    return commands


def _extract_from_entry(entry: dict, commands: list[str]) -> None:
    """Extract Bash commands from a single transcript entry."""
    # Format 1: top-level tool_name + tool_input
    if entry.get("tool_name") == "Bash":
        cmd = entry.get("tool_input", {}).get("command", "")
        if cmd:
            commands.append(cmd)
        return

    # Format 2: content blocks with type=tool_use
    for block in entry.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use" and block.get("name") == "Bash":
            cmd = block.get("input", {}).get("command", "")
            if cmd:
                commands.append(cmd)


def _check_command(command: str) -> list[tuple[str, str]]:
    """Check a command against dangerous patterns. Returns list of (command, label) matches."""
    findings = []
    for pattern, label in DANGEROUS_PATTERNS:
        if pattern.search(command):
            findings.append((command, label))
    return findings


class SubagentTranscriptAudit(Rule):
    """Audit subagent transcripts for dangerous commands after completion."""

    id = "subagent-transcript-audit"
    description = "Audits subagent transcripts for dangerous commands post-execution"
    severity = Severity.WARNING
    events = [HookEvent.SUB_AGENT_STOP]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        transcript_path = context.agent_transcript_path
        if not transcript_path:
            return []

        # Defensive: skip oversized transcripts
        try:
            size = os.path.getsize(transcript_path)
        except OSError:
            return []

        if size > _MAX_TRANSCRIPT_BYTES:
            logger.warning(
                "Skipping transcript audit: %s is %d bytes (limit %d)",
                transcript_path, size, _MAX_TRANSCRIPT_BYTES,
            )
            return []

        commands = _extract_bash_commands(transcript_path)
        if not commands:
            # Record clean audit in session state
            self._record_audit(context, findings=[], commands_count=0)
            return []

        # Check all commands against dangerous patterns
        all_findings: list[tuple[str, str]] = []
        for cmd in commands:
            all_findings.extend(_check_command(cmd))

        # Record audit results in session state for Stop report
        self._record_audit(
            context,
            findings=[(label, cmd[:120]) for cmd, label in all_findings],
            commands_count=len(commands),
        )

        if not all_findings:
            return []

        violations = []
        for cmd, label in all_findings:
            # Truncate command for display
            display_cmd = cmd[:120] + "..." if len(cmd) > 120 else cmd
            violations.append(
                Violation(
                    rule_id=self.id,
                    message=f"Subagent executed dangerous command ({label}): {display_cmd}",
                    severity=self.severity,
                )
            )

        return violations

    def _record_audit(
        self,
        context: RuleContext,
        findings: list[tuple[str, str]],
        commands_count: int,
    ) -> None:
        """Record audit results in session state for the Stop report."""
        audits = context.session_state.setdefault("subagent_audits", [])
        audits.append({
            "agent_type": context.agent_type or "unknown",
            "agent_id": context.agent_id or "unknown",
            "commands_count": commands_count,
            "findings": findings,
        })
