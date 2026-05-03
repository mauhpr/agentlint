"""Output formatting for agent violations."""
from __future__ import annotations

import json

from agentlint.formats.base import OutputFormatter
from agentlint.formats.claude_hooks import ClaudeHookFormatter
from agentlint.models import AgentEvent, Severity, Violation


class Reporter:
    """Formats violations for agent output.

    Uses a pluggable OutputFormatter for platform-specific hook protocols,
    while session summary/report formatting remains generic.
    """

    def __init__(
        self,
        violations: list[Violation],
        rules_evaluated: int = 0,
        formatter: OutputFormatter | None = None,
    ):
        self.violations = violations
        self.rules_evaluated = rules_evaluated
        self.formatter = formatter or ClaudeHookFormatter()

    def has_blocking_violations(self) -> bool:
        return any(v.severity == Severity.ERROR for v in self.violations)

    def exit_code(self, event: str = "") -> int:
        """Return exit code for the configured formatter."""
        return self.formatter.exit_code(self.violations, event)

    def format_hook_output(self, event: str = "") -> str | None:
        """Format violations as hook output via the configured formatter."""
        return self.formatter.format(self.violations, event)

    def format_subagent_start_output(self) -> str | None:
        """Format SubagentStart output for injection into subagent context."""
        return self.formatter.format_subagent_start(self.violations)

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
        hook_timing = state.get("_hook_timing", {})

        # v1.10.0 visibility additions: inline ignores (with reasons), per-rule
        # circuit-breaker history, and per-rule fire rates so users can tune
        # noisy rules from the summary alone.
        inline_ignores = state.get("inline_ignores", [])
        rule_fire_rates: list[dict] = []
        if total_evals > 0:
            for rid, count in sorted(rule_violations.items(), key=lambda x: x[1], reverse=True):
                rule_fire_rates.append({
                    "rule_id": rid,
                    "fires": count,
                    "evaluations": total_evals,
                    "rate": round(count / total_evals, 4),
                })
        circuit_breaker_per_rule: list[dict] = []
        for rid, cb_data in sorted(cb_state.items()):
            circuit_breaker_per_rule.append({
                "rule_id": rid,
                "fire_count": cb_data.get("fire_count", 0),
                "state": cb_data.get("state", "active"),
                "transitions": cb_data.get("transitions", []),
            })

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
            if hook_timing:
                data["hook_timing"] = {
                    "total_ms": round(hook_timing.get("total_ms", 0), 1),
                    "count": hook_timing.get("count", 0),
                    "avg_ms": round(hook_timing.get("total_ms", 0) / max(hook_timing.get("count", 1), 1), 1),
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

            # v1.10.0: surface visibility data so summaries are auditable
            # without needing to read raw session state.
            if inline_ignores:
                data["inline_ignores"] = inline_ignores
            if circuit_breaker_per_rule:
                data["circuit_breaker_per_rule"] = circuit_breaker_per_rule
            if rule_fire_rates:
                data["rule_fire_rates"] = rule_fire_rates
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

        # Hook timing
        if hook_timing and hook_timing.get("count", 0) > 0:
            total_ms = hook_timing["total_ms"]
            count = hook_timing["count"]
            avg_ms = total_ms / count
            if total_ms >= 1000:
                lines.append(f"Hook latency: {count} evaluations, avg {avg_ms:.0f}ms, total {total_ms / 1000:.1f}s")
            else:
                lines.append(f"Hook latency: {count} evaluations, avg {avg_ms:.0f}ms, total {total_ms:.0f}ms")

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

        # Inline ignores (v1.10.0): list overrides with their reasons so
        # suppressions are auditable rather than anonymous.
        if inline_ignores:
            lines.append("")
            lines.append(f"Inline Ignores ({len(inline_ignores)} total)")
            for entry in inline_ignores[:10]:  # cap at 10 for readability
                file_label = entry.get("file") or "<unknown>"
                rule_id = entry.get("rule_id", "?")
                reason = entry.get("reason")
                if reason:
                    lines.append(f"  {file_label} — {rule_id} — \"{reason}\"")
                else:
                    lines.append(f"  {file_label} — {rule_id}")
            if len(inline_ignores) > 10:
                lines.append(f"  ... and {len(inline_ignores) - 10} more")

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
