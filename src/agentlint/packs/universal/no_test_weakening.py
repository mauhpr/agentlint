"""Rule: detect patterns that weaken test suites."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}

# File patterns that indicate test files.
_TEST_FILE_RE = re.compile(r"(?:^|/)(?:test_|tests?/|spec_|__tests__/|.*\.test\.|.*\.spec\.)", re.IGNORECASE)

# --- Weakening patterns ---
# Skip markers.
_PYTEST_SKIP_RE = re.compile(r"@pytest\.mark\.skip\b")
_UNITTEST_SKIP_RE = re.compile(r"@unittest\.skip\b")
_JEST_SKIP_RE = re.compile(r"\b(?:it|test|describe)\.skip\b")

# Trivially passing assertions.
_ASSERT_TRUE_RE = re.compile(r"\bassert\s+True\b")
_ASSERT_TRUE_METHOD_RE = re.compile(r"\bself\.assertTrue\s*\(\s*True\s*\)")
_EXPECT_TRUE_RE = re.compile(r"\bexpect\s*\(\s*true\s*\)\s*\.toBe\s*\(\s*true\s*\)", re.IGNORECASE)

# Commented-out assertions.
_COMMENTED_ASSERT_RE = re.compile(r"^\s*#\s*assert\b", re.MULTILINE)
_COMMENTED_EXPECT_RE = re.compile(r"^\s*//\s*expect\b", re.MULTILINE)

# pytest.mark.xfail without reason.
_XFAIL_NO_REASON_RE = re.compile(r"@pytest\.mark\.xfail\s*(?:\(\s*\))?$", re.MULTILINE)

# Empty test functions.
_EMPTY_TEST_RE = re.compile(
    r"def\s+test_\w+\s*\([^)]*\)\s*:\s*\n\s+pass\b",
    re.MULTILINE,
)


class NoTestWeakening(Rule):
    """Detect patterns that weaken test suites."""

    id = "no-test-weakening"
    description = "Warns when tests are skipped, trivialized, or commented out"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _WRITE_TOOLS:
            return []

        file_path: str | None = context.file_path
        if not file_path or not _TEST_FILE_RE.search(file_path):
            return []

        content = context.tool_input.get("content", "")
        if not content:
            return []

        violations: list[Violation] = []

        # Skip markers.
        if _PYTEST_SKIP_RE.search(content):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Test skip marker detected: @pytest.mark.skip",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Fix the test instead of skipping it, or use @pytest.mark.xfail with a reason.",
                )
            )

        if _UNITTEST_SKIP_RE.search(content):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Test skip marker detected: @unittest.skip",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Fix the test instead of skipping it.",
                )
            )

        if _JEST_SKIP_RE.search(content):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Test skip detected: .skip()",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Fix the test instead of skipping it.",
                )
            )

        # Trivially passing assertions.
        if _ASSERT_TRUE_RE.search(content):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Trivially passing assertion: assert True",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Replace 'assert True' with a meaningful assertion.",
                )
            )

        if _ASSERT_TRUE_METHOD_RE.search(content):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Trivially passing assertion: self.assertTrue(True)",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Replace 'assertTrue(True)' with a meaningful assertion.",
                )
            )

        if _EXPECT_TRUE_RE.search(content):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Trivially passing assertion: expect(true).toBe(true)",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Replace with a meaningful expectation.",
                )
            )

        # Commented-out assertions.
        if _COMMENTED_ASSERT_RE.search(content):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Commented-out assertion detected",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Remove or restore commented-out assertions instead of leaving dead test code.",
                )
            )

        if _COMMENTED_EXPECT_RE.search(content):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Commented-out expectation detected",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Remove or restore commented-out expectations instead of leaving dead test code.",
                )
            )

        # xfail without reason.
        if _XFAIL_NO_REASON_RE.search(content):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="@pytest.mark.xfail without reason",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Add a reason parameter: @pytest.mark.xfail(reason='...')",
                )
            )

        # Empty test functions.
        if _EMPTY_TEST_RE.search(content):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Empty test function detected (pass only)",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Implement the test or remove the empty placeholder.",
                )
            )

        return violations
