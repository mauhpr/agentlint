"""Output formatting for Claude Code hook protocol."""
from __future__ import annotations

import json

from agentlint.models import Severity, Violation


class Reporter:
    """Formats violations for Claude Code hook output."""

    def __init__(self, violations: list[Violation], rules_evaluated: int = 0):
        self.violations = violations
        self.rules_evaluated = rules_evaluated

    def has_blocking_violations(self) -> bool:
        return any(v.severity == Severity.ERROR for v in self.violations)

    def exit_code(self, event: str = "") -> int:
        """Return exit code for Claude Code hook protocol.

        PreToolUse blocking uses exit 0 + JSON deny protocol (exit 2 ignores JSON).
        Other events use exit 2 for blocking (stderr-based).
        """
        if not self.has_blocking_violations():
            return 0
        if event == "PreToolUse":
            return 0  # Deny protocol requires exit 0 with JSON
        return 2

    def format_hook_output(self, event: str = "") -> str | None:
        """Format violations as Claude Code hook JSON output. Returns None if no violations.

        Output channel depends on event type:
        - PreToolUse ERROR: hookSpecificOutput with permissionDecision="deny"
        - PreToolUse advisory (WARNING/INFO): hookSpecificOutput with additionalContext
        - PostToolUse/PostToolUseFailure: hookSpecificOutput with additionalContext
          (+ decision "block" for WARNINGs as strong advisory signal)
        - Other events (Stop, Notification, etc.): systemMessage for user visibility
        """
        if not self.violations:
            return None

        errors = [v for v in self.violations if v.severity == Severity.ERROR]
        warnings = [v for v in self.violations if v.severity == Severity.WARNING]
        infos = [v for v in self.violations if v.severity == Severity.INFO]

        # For PreToolUse with blocking violations, use the deny protocol
        if event == "PreToolUse" and errors:
            reason_lines = []
            for v in errors:
                reason_lines.append(f"[{v.rule_id}] {v.message}")
                if v.suggestion:
                    reason_lines.append(f"  -> {v.suggestion}")
            # Include warnings/info as additional context
            for v in warnings + infos:
                reason_lines.append(f"[{v.rule_id}] {v.message}")
                if v.suggestion:
                    reason_lines.append(f"  -> {v.suggestion}")

            return json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "\n".join(reason_lines),
                }
            })

        # Build formatted violation lines for reuse across output paths
        context_lines: list[str] = []
        for v in errors + warnings + infos:
            context_lines.append(f"[{v.rule_id}] {v.message}")
            if v.suggestion:
                context_lines.append(f"  -> {v.suggestion}")

        # PreToolUse advisory (no errors) — inject into agent context before tool runs
        if event == "PreToolUse":
            return json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": "\n".join(context_lines),
                }
            })

        # PostToolUse — inject into agent context so it influences next action
        if event in ("PostToolUse", "PostToolUseFailure"):
            result: dict = {
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": "\n".join(context_lines),
                }
            }
            # PostToolUse "block" is a strong advisory signal — the tool already ran,
            # so this doesn't undo the action. Claude Code treats it as "hook is
            # unhappy, reconsider before next action." If the protocol adds a
            # dedicated advisory decision value in the future, switch to that.
            if warnings or errors:
                reason_violations = errors + warnings
                result["decision"] = "block"
                result["reason"] = "\n".join(
                    f"[{v.rule_id}] {v.message}" for v in reason_violations
                )
            return json.dumps(result)

        # Other events (Stop, Notification, etc.) — systemMessage for user visibility
        lines = ["", "AgentLint:"]
        if errors:
            lines.append("  BLOCKED:")
            for v in errors:
                lines.append(f"    [{v.rule_id}] {v.message}")
                if v.suggestion:
                    lines.append(f"      -> {v.suggestion}")
        if warnings:
            lines.append("  WARNINGS:")
            for v in warnings:
                lines.append(f"    [{v.rule_id}] {v.message}")
                if v.suggestion:
                    lines.append(f"      -> {v.suggestion}")
        if infos:
            lines.append("  INFO:")
            for v in infos:
                lines.append(f"    [{v.rule_id}] {v.message}")
                if v.suggestion:
                    lines.append(f"      -> {v.suggestion}")
        return json.dumps({"systemMessage": "\n".join(lines)})

    def format_subagent_start_output(self) -> str | None:
        """Format SubagentStart output with additionalContext for injection into subagent.

        Uses hookSpecificOutput to inject safety messages into the subagent's context.
        Returns None if no violations (nothing to inject).
        """
        if not self.violations:
            return None

        context_lines = [v.message for v in self.violations]
        return json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContext": "\n".join(context_lines),
            }
        })

    def format_session_summary(
        self,
        session_state: dict | None = None,
        output_format: str = "text",
    ) -> str:
        """Format a cumulative session summary dashboard.

        Reads violation_log, token_budget, suppressed_rules, circuit_breaker,
        subagents_spawned, subagent_audits, files_touched, and edited_files
        from session_state to produce a comprehensive dashboard.
        """
        state = session_state or {}
        vlog = state.get("violation_log", {})
        total_evals = vlog.get("total_evaluations", 0)
        total_blocked = vlog.get("total_blocked", 0)
        total_warnings = vlog.get("total_warnings", 0)
        total_info = vlog.get("total_info", 0)
        total_violations = total_blocked + total_warnings + total_info
        rule_violations = vlog.get("rule_violations", {})

        # Top rules sorted by count descending
        top_rules = sorted(rule_violations.items(), key=lambda x: x[1], reverse=True)[:5]

        budget = state.get("token_budget", {})
        total_calls = budget.get("total_calls", 0)
        total_bytes = budget.get("total_bytes_written", 0)

        files_touched = state.get("files_touched", [])
        edited_files = state.get("edited_files", [])
        changed_files = state.get("changed_files", [])

        suppressed = state.get("suppressed_rules", [])
        cb_state = state.get("circuit_breaker", {})
        spawned = state.get("subagents_spawned", [])
        audits = state.get("subagent_audits", [])

        if output_format == "json":
            data = {
                "evaluations": total_evals,
                "tool_calls": total_calls,
                "bytes_written": total_bytes,
                "files_touched": len(files_touched),
                "files_edited": len(edited_files),
                "files_changed_git": len(changed_files),
                "violations": {
                    "total": total_violations,
                    "blocked": total_blocked,
                    "warnings": total_warnings,
                    "info": total_info,
                },
                "top_rules": [{"rule_id": r, "count": c} for r, c in top_rules],
                "suppressed_rules": suppressed,
                "subagents_spawned": len(spawned),
                "subagents_audited": len(audits),
            }
            # Add circuit breaker degraded rules
            degraded = {
                rid: data_cb for rid, data_cb in cb_state.items()
                if data_cb.get("state", "active") != "active"
            }
            if degraded:
                data["circuit_breaker"] = [
                    {"rule_id": rid, "state": d.get("state"), "fire_count": d.get("fire_count", 0)}
                    for rid, d in sorted(degraded.items())
                ]
            return json.dumps(data)

        # Text format
        lines = ["AgentLint Session Summary"]

        # Session overview
        parts = []
        if total_evals:
            parts.append(f"{total_evals} evaluations")
        if total_calls:
            parts.append(f"{total_calls} tool calls")
        if total_bytes:
            parts.append(f"{total_bytes:,} bytes written")
        if parts:
            lines.append(" | ".join(parts))

        # Files
        file_parts = []
        if files_touched:
            file_parts.append(f"{len(files_touched)} touched")
        if edited_files:
            file_parts.append(f"{len(edited_files)} edited")
        if changed_files:
            file_parts.append(f"{len(changed_files)} changed (git)")
        if file_parts:
            lines.append("Files: " + ", ".join(file_parts))

        # Violations
        if total_violations:
            lines.append("")
            lines.append(f"Violations ({total_violations} total)")
            lines.append(f"  Blocked: {total_blocked} | Warnings: {total_warnings} | Info: {total_info}")

        # Top rules
        if top_rules:
            lines.append("")
            lines.append("Top Rules")
            for rule_id, count in top_rules:
                lines.append(f"  {rule_id:<30} {count}")

        # Suppressed rules
        if suppressed:
            lines.append("")
            lines.append(f"Suppressed: {', '.join(suppressed)}")

        # Circuit breaker
        degraded = {
            rid: data_cb for rid, data_cb in cb_state.items()
            if data_cb.get("state", "active") != "active"
        }
        if degraded:
            lines.append("")
            lines.append("Circuit Breaker")
            for rid, data_cb in sorted(degraded.items()):
                s = data_cb.get("state", "unknown")
                c = data_cb.get("fire_count", 0)
                lines.append(f"  {rid} {s} ({c}x)")

        # Subagent activity
        if spawned or audits:
            lines.append("")
            lines.append(f"Subagents: {len(spawned)} spawned, {len(audits)} audited")

        return "\n".join(lines)

    def format_session_report(
        self,
        files_changed: int = 0,
        cb_state: dict | None = None,
        session_state: dict | None = None,
    ) -> str:
        """Format a session summary report for the Stop event."""
        errors = [v for v in self.violations if v.severity == Severity.ERROR]
        warnings = [v for v in self.violations if v.severity == Severity.WARNING]

        lines = [
            "AgentLint Session Report",
            f"Files changed: {files_changed}  |  Rules evaluated: {self.rules_evaluated}",
            f"Passed: {self.rules_evaluated - len(self.violations)}  |  "
            f"Warnings: {len(warnings)}  |  Blocked: {len(errors)}",
        ]

        if errors:
            lines.append("")
            lines.append("Blocked actions:")
            for v in errors:
                lines.append(f"  [{v.rule_id}] {v.message}")

        if warnings:
            lines.append("")
            lines.append("Warnings:")
            for v in warnings:
                lines.append(f"  [{v.rule_id}] {v.message}")

        # Circuit breaker activity (only show non-active rules)
        if cb_state:
            degraded = {
                rid: data for rid, data in cb_state.items()
                if data.get("state", "active") != "active"
            }
            if degraded:
                lines.append("")
                lines.append("Circuit Breaker:")
                for rid, data in sorted(degraded.items()):
                    state = data.get("state", "unknown")
                    count = data.get("fire_count", 0)
                    lines.append(f"  [{rid}] {state} (fired {count}x)")

        # Cumulative violation summary (from session-wide violation_log)
        state = session_state or {}
        vlog = state.get("violation_log")
        if vlog:
            cum_total = vlog.get("total_blocked", 0) + vlog.get("total_warnings", 0) + vlog.get("total_info", 0)
            if cum_total:
                lines.append("")
                lines.append(
                    f"Session totals: {cum_total} violation(s) across "
                    f"{vlog.get('total_evaluations', 0)} evaluations"
                )
                top_rules = sorted(
                    vlog.get("rule_violations", {}).items(),
                    key=lambda x: x[1], reverse=True,
                )[:5]
                if top_rules:
                    lines.append("Top rules:")
                    for rule_id, count in top_rules:
                        lines.append(f"  {rule_id:<30} {count}")

        # Subagent activity (from session state)
        audits = state.get("subagent_audits", [])
        spawned = state.get("subagents_spawned", [])
        if spawned or audits:
            lines.append("")
            lines.append(f"Subagent Activity: {len(spawned)} spawned, {len(audits)} audited")
            for audit in audits:
                agent_type = audit.get("agent_type", "unknown")
                agent_id = audit.get("agent_id", "")
                id_suffix = f" ({agent_id[:7]})" if agent_id and agent_id != "unknown" else ""
                cmds = audit.get("commands_count", 0)
                findings = audit.get("findings", [])
                if findings:
                    lines.append(f"  [{agent_type}{id_suffix}] {cmds} commands, {len(findings)} finding(s):")
                    for _label, cmd in findings:
                        lines.append(f"    - {cmd}")
                else:
                    lines.append(f"  [{agent_type}{id_suffix}] {cmds} commands, no findings")

        return "\n".join(lines)
