"""AgentLint evaluation engine."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, replace
from fnmatch import fnmatch

from agentlint.circuit_breaker import apply_circuit_breaker
from agentlint.config import AgentLintConfig, get_rule_setting
from agentlint.exceptions import applies as exception_applies
from agentlint.exceptions import audit_use
from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.recorder import safe_command_summary
from agentlint.utils.shell import Operation, active_operations, mutation_command

logger = logging.getLogger("agentlint")

# Only built-in operation guards use the display-argument projection. Credential,
# file-write, custom and organization policies continue inspecting original input.
_MUTATION_RULES = {
    "no-force-push",
    "no-push-to-main",
    "no-skip-hooks",
    "no-destructive-commands",
    "package-publish-guard",
    "production-guard",
    "cloud-resource-deletion",
    "cloud-infra-mutation",
    "destructive-confirmation-gate",
    "network-firewall-guard",
    "docker-volume-guard",
    "bash-rate-limiter",
    "dry-run-required",
    "cloud-paid-resource-creation",
    "cross-account-guard",
    "system-scheduler-guard",
    "remote-boot-partition-guard",
    "remote-chroot-guard",
    "ssh-destructive-command-guard",
    "package-manager-in-chroot",
}

# Rules whose patterns describe a single command. They are evaluated once per
# state-changing operation so text from one operation (e.g. `gh pr create
# --base main`) cannot complete a match started in another (`git push ...`).
# Rules that legitimately correlate operations (dry-run-required, production
# context, rate limits) keep seeing the joined state-changing operations.
_PER_OPERATION_RULES = {"no-destructive-commands", "no-push-to-main", "no-force-push"}


def _operation_allowed(operation: Operation, allowances: list) -> bool:
    """Match a structured `allow_operations` entry against one parsed operation."""
    words = list(operation.words)
    if words and words[0] in {"command", "env"}:
        from agentlint.utils.shell import unwrap_simple_command

        words = unwrap_simple_command(words) or words
    if not words:
        return False
    binary, args = words[0].rsplit("/", 1)[-1], words[1:]
    for entry in allowances:
        if not isinstance(entry, dict) or entry.get("binary") != binary:
            continue
        prefix = entry.get("args_prefix")
        pattern = entry.get("args_regex")
        if prefix is not None and isinstance(prefix, list) and args[: len(prefix)] == prefix:
            return True
        if isinstance(pattern, str):
            import re

            if re.fullmatch(pattern, " ".join(args)):
                return True
    return False


@dataclass
class EvaluationResult:
    """Result of evaluating rules against a context."""

    violations: list[Violation] = field(default_factory=list)
    rules_evaluated: int = 0
    rule_ids_evaluated: list[str] = field(default_factory=list)

    @property
    def is_blocking(self) -> bool:
        return any(v.severity == Severity.ERROR for v in self.violations)


class Engine:
    """Orchestrates rule loading and evaluation."""

    def __init__(self, config: AgentLintConfig, rules: list[Rule]):
        self.config = config
        self.rules = rules

    def evaluate(self, context: RuleContext) -> EvaluationResult:
        """Evaluate all applicable rules against the context."""
        result = EvaluationResult()
        required = set(self.config.required_rules)
        mutation_context = context
        operations: list[Operation] | None = None
        if context.tool_name == "Bash" and isinstance(context.command, str):
            operations = active_operations(context.command)
            projected = (
                " ; ".join(op.text for op in operations)
                if operations is not None
                else mutation_command(context.command)
            )
            mutation_context = replace(
                context,
                tool_input={**context.tool_input, "command": projected},
            )
        if context.event == HookEvent.PRE_TOOL_USE:
            from agentlint.approvals import self_approval_attempt

            attempt = self_approval_attempt(context.tool_name, context.tool_input or {})
            if attempt:
                result.violations.append(
                    Violation(
                        rule_id="approval-self-grant",
                        severity=Severity.ERROR,
                        message=f"Agents cannot create approvals: this tool call {attempt}",
                        operation=context.tool_name,
                        policy_source="AgentLint approvals (built-in, always on)",
                        suggestion=(
                            "Ask the user to run `agentlint approve grant <class>` in their own "
                            "terminal if they want to approve this action."
                        ),
                    )
                )
        protected = required | {rule.id for rule in self.rules if getattr(rule, "locked", False)}
        protected.add("approval-self-grant")
        if protected:
            cb = {
                **self.config.circuit_breaker,
                **context.config.get("_circuit_breaker_global", {}),
            }
            cb["never_degrade"] = list(set(cb.get("never_degrade", [])) | protected)
            context = replace(context, config={**context.config, "_circuit_breaker_global": cb})

        for rule in self.rules:
            if rule.pack not in self.config.packs and rule.id not in required:
                continue
            if not getattr(rule, "locked", False) and not self.config.is_rule_enabled(rule.id):
                continue
            if not rule.matches_event(context.event):
                continue

            # Global ignore_paths — skip all rules for matching files
            if context.file_path and context.config and rule.id not in required:
                ignore_paths = context.config.get("ignore_paths", [])
                if isinstance(ignore_paths, list) and ignore_paths:
                    basename = os.path.basename(context.file_path)
                    if any(
                        fnmatch(context.file_path, p)
                        or fnmatch(context.relative_file_path or "", p)
                        or fnmatch(basename, p)
                        for p in ignore_paths
                    ):
                        continue

            # Per-rule allow_paths — skip this specific rule for matching files
            if context.file_path and context.config:
                rule_config = context.config.get(rule.id, {})
                rule_allow = (
                    rule_config.get("allow_paths", [])
                    if rule.id in required
                    else get_rule_setting(context.config, rule.id, "allow_paths", [])
                )
                if isinstance(rule_allow, list) and rule_allow:
                    basename = os.path.basename(context.file_path)
                    if any(
                        fnmatch(context.file_path, p)
                        or fnmatch(context.relative_file_path or "", p)
                        or fnmatch(basename, p)
                        for p in rule_allow
                    ):
                        continue

                # Per-rule ignore_paths — accepted-pattern alias for allow_paths.
                # Useful when teams want to document why a rule does not apply
                # to a local convention without disabling the rule globally.
                rule_ignore = (
                    rule_config.get("ignore_paths", [])
                    if rule.id in required
                    else get_rule_setting(context.config, rule.id, "ignore_paths", [])
                )
                if isinstance(rule_ignore, list) and rule_ignore:
                    basename = os.path.basename(context.file_path)
                    if any(
                        fnmatch(context.file_path, p)
                        or fnmatch(context.relative_file_path or "", p)
                        or fnmatch(basename, p)
                        for p in rule_ignore
                    ):
                        continue

            result.rules_evaluated += 1
            result.rule_ids_evaluated.append(rule.id)

            try:
                projected_rule = (
                    rule.id in _MUTATION_RULES
                    and type(rule).__module__.startswith("agentlint.packs.")
                    and not getattr(rule, "locked", False)
                )
                checked = mutation_context if projected_rule else context
                if rule.id in required:
                    checked = replace(
                        checked,
                        config={
                            key: value
                            for key, value in checked.config.items()
                            if key
                            not in {
                                "allow_paths",
                                "allow_patterns",
                                "allow_operations",
                                "ignore_paths",
                            }
                        },
                    )
                allowances = (
                    []
                    if rule.id in required
                    else get_rule_setting(context.config, rule.id, "allow_operations", [])
                )
                if (
                    projected_rule
                    and operations is not None
                    and (rule.id in _PER_OPERATION_RULES or allowances)
                ):
                    violations = self._evaluate_per_operation(
                        rule,
                        checked,
                        operations,
                        allowances if isinstance(allowances, list) else [],
                    )
                else:
                    violations = rule.evaluate(checked)
            except Exception:
                logger.exception("Rule %s raised an exception", rule.id)
                if rule.id in required:
                    result.violations.append(
                        Violation(
                            rule_id=rule.id,
                            severity=Severity.ERROR,
                            message="Required workspace rule could not complete its check",
                        )
                    )
                continue

            for v in violations:
                if not getattr(rule, "locked", False) and rule.id not in required:
                    v.severity = self.config.effective_severity(v.severity)
                if v.severity == Severity.ERROR:
                    if not v.operation:
                        v.operation = (
                            safe_command_summary(context.command or "")
                            if context.tool_name == "Bash"
                            else context.tool_name
                        )
                    if not v.policy_source:
                        v.policy_source = self.config.describe_policy_source(
                            rule.id,
                            rule.pack,
                            builtin=type(rule).__module__.startswith("agentlint.packs."),
                        )
                    if not v.suggestion:
                        v.suggestion = (
                            "Run 'agentlint policy explain' or inspect the rule configuration."
                        )

            if (
                not getattr(rule, "locked", False)
                and rule.id not in required
                and type(rule).__module__.startswith("agentlint.packs.")
            ):
                self._apply_approvals(rule.id, context, violations)

            for v in violations:
                exempted = False
                if (
                    context.tool_name == "Bash"
                    and not getattr(rule, "locked", False)
                    and not type(rule).__module__.startswith("agentlint.agentchute.")
                    and rule.id not in required
                ):
                    for grant in self.config.exceptions:
                        if exception_applies(
                            grant,
                            rule_id=v.rule_id,
                            repository=context.project_dir,
                            command=context.command or "",
                        ) and audit_use(
                            grant, repository=context.project_dir, command=context.command or ""
                        ):
                            exempted = True
                            break
                if not exempted:
                    result.violations.append(v)

        # Apply circuit breaker degradation
        result.violations = apply_circuit_breaker(
            result.violations,
            context.session_state,
            context.config,
        )

        # Suppress acknowledged rules (ERRORs are never suppressed)
        suppressed = set(context.session_state.get("suppressed_rules", []))
        if suppressed:
            result.violations = [
                v
                for v in result.violations
                if v.rule_id not in suppressed or v.severity == Severity.ERROR
            ]

        # Auto-suppress: track consecutive fires per rule (after manual suppress
        # filter so already-suppressed rules don't accumulate counts)
        auto_suppress_threshold = (
            context.config.get("auto_suppress_after", 0) if context.config else 0
        )
        if auto_suppress_threshold and auto_suppress_threshold > 0:
            fire_counts = context.session_state.setdefault("rule_fire_counts", {})
            # Count once per rule per invocation, not per violation
            fired_non_error_ids: set[str] = {
                v.rule_id for v in result.violations if v.severity != Severity.ERROR
            }
            for rule_id in fired_non_error_ids:
                count = fire_counts.get(rule_id, 0) + 1
                fire_counts[rule_id] = count
                threshold = get_rule_setting(
                    context.config,
                    rule_id,
                    "auto_suppress_after",
                    auto_suppress_threshold,
                )
                if count > threshold:
                    suppressed_rules = context.session_state.setdefault("suppressed_rules", [])
                    if rule_id not in suppressed_rules:
                        suppressed_rules.append(rule_id)
                        logger.info("Auto-suppressed '%s' after %d fires", rule_id, count)
            # Reset count for rules that didn't fire
            for rid in list(fire_counts):
                if rid not in fired_non_error_ids:
                    fire_counts[rid] = 0

            # Filter newly auto-suppressed violations from this evaluation
            newly_suppressed = set(context.session_state.get("suppressed_rules", [])) - suppressed
            if newly_suppressed:
                result.violations = [
                    v
                    for v in result.violations
                    if v.rule_id not in newly_suppressed or v.severity == Severity.ERROR
                ]

        return result

    @staticmethod
    def _evaluate_per_operation(rule, context, operations, allowances):
        """Evaluate a rule against each state-changing operation separately."""
        violations: list[Violation] = []
        seen: set[tuple[str, str]] = set()
        for operation in operations:
            if allowances and _operation_allowed(operation, allowances):
                continue
            for v in rule.evaluate(
                replace(context, tool_input={**context.tool_input, "command": operation.text})
            ):
                key = (v.rule_id, v.message)
                if key in seen:
                    continue
                seen.add(key)
                if not v.operation:
                    v.operation = safe_command_summary(operation.text)
                violations.append(v)
        return violations

    @staticmethod
    def _apply_approvals(rule_id: str, context: RuleContext, violations: list[Violation]) -> None:
        """Relax ERRORs covered by a typed, unexpired, audited human approval."""
        from agentlint.approvals import RULE_ACTION_CLASS, audit_use, matching_grant

        if rule_id not in RULE_ACTION_CLASS:
            return
        command = context.command if context.tool_name == "Bash" else None
        for v in violations:
            if v.severity != Severity.ERROR:
                continue
            grant = matching_grant(rule_id, repository=context.project_dir, command=command)
            if grant and audit_use(
                grant, rule_id=rule_id, repository=context.project_dir, command=command
            ):
                v.severity = Severity.WARNING
                v.message += (
                    f" (allowed by approval {grant['id']}: {grant['action_class']}, "
                    f"until {grant['expires_at']})"
                )
