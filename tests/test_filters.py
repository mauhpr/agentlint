"""Comprehensive tests for the inline ignore directive filter."""
from __future__ import annotations

from agentlint.filters import filter_inline_ignores
from agentlint.models import Severity, Violation


def _v(rule_id: str = "test-rule", severity: Severity = Severity.WARNING, line: int | None = None) -> Violation:
    return Violation(rule_id=rule_id, message="test", severity=severity, line=line)


class TestFilterInlineIgnores:
    """Tests for filter_inline_ignores()."""

    # ── # agentlint:ignore-file (8 tests) ──────────────────────────────

    def test_ignore_file_suppresses_all(self):
        content = "# agentlint:ignore-file\nx = 1\n"
        violations = [_v("rule-a"), _v("rule-b")]
        assert filter_inline_ignores(violations, content) == []

    def test_ignore_file_with_whitespace(self):
        content = "  # agentlint:ignore-file\nx = 1\n"
        violations = [_v()]
        assert filter_inline_ignores(violations, content) == []

    def test_ignore_file_anywhere(self):
        content = "x = 1\ny = 2\n# agentlint:ignore-file\nz = 3\n"
        violations = [_v()]
        assert filter_inline_ignores(violations, content) == []

    def test_ignore_file_with_trailing_comment(self):
        content = "# agentlint:ignore-file -- legacy code\nx = 1\n"
        violations = [_v()]
        assert filter_inline_ignores(violations, content) == []

    def test_no_directive_passes_through(self):
        content = "x = 1\ny = 2\n"
        violations = [_v("rule-a"), _v("rule-b")]
        result = filter_inline_ignores(violations, content)
        assert result == violations

    def test_empty_file_content(self):
        violations = [_v()]
        result = filter_inline_ignores(violations, "")
        assert result == violations

    def test_none_file_content(self):
        violations = [_v()]
        result = filter_inline_ignores(violations, None)
        assert result == violations

    def test_ignore_file_suppresses_errors_too(self):
        content = "# agentlint:ignore-file\n"
        violations = [
            _v("rule-a", severity=Severity.ERROR),
            _v("rule-b", severity=Severity.WARNING),
            _v("rule-c", severity=Severity.INFO),
        ]
        assert filter_inline_ignores(violations, content) == []

    # ── # agentlint:ignore rule-id (8 tests) ───────────────────────────

    def test_ignore_specific_rule(self):
        content = "# agentlint:ignore max-file-size\nx = 1\n"
        v_match = _v("max-file-size")
        v_other = _v("no-secrets")
        result = filter_inline_ignores([v_match, v_other], content)
        assert result == [v_other]

    def test_ignore_multiple_rules(self):
        content = "# agentlint:ignore max-file-size\n# agentlint:ignore no-secrets\nx = 1\n"
        v1 = _v("max-file-size")
        v2 = _v("no-secrets")
        v3 = _v("other-rule")
        result = filter_inline_ignores([v1, v2, v3], content)
        assert result == [v3]

    def test_ignore_rule_not_in_violations(self):
        content = "# agentlint:ignore nonexistent-rule\nx = 1\n"
        violations = [_v("rule-a"), _v("rule-b")]
        result = filter_inline_ignores(violations, content)
        assert result == violations

    def test_partial_rule_id_no_match(self):
        content = "# agentlint:ignore max\nx = 1\n"
        violations = [_v("max-file-size")]
        result = filter_inline_ignores(violations, content)
        assert result == violations

    def test_case_sensitive(self):
        content = "# agentlint:ignore Max-File-Size\nx = 1\n"
        violations = [_v("max-file-size")]
        result = filter_inline_ignores(violations, content)
        assert result == violations

    def test_ignore_rule_with_hyphen(self):
        content = "# agentlint:ignore no-dead-imports\nx = 1\n"
        v_match = _v("no-dead-imports")
        v_other = _v("other")
        result = filter_inline_ignores([v_match, v_other], content)
        assert result == [v_other]

    def test_ignore_error_rule(self):
        content = "# agentlint:ignore no-secrets\n"
        violations = [_v("no-secrets", severity=Severity.ERROR)]
        assert filter_inline_ignores(violations, content) == []

    def test_other_violations_preserved(self):
        content = "# agentlint:ignore rule-a\n"
        v_a = _v("rule-a")
        v_b = _v("rule-b")
        v_c = _v("rule-c")
        result = filter_inline_ignores([v_a, v_b, v_c], content)
        assert result == [v_b, v_c]

    # ── # agentlint:ignore-next-line (9 tests) ─────────────────────────

    def test_ignore_next_line_basic(self):
        content = "x = 1\n# agentlint:ignore-next-line\ny = 2\n"
        # Directive is on line 2, so line 3 is suppressed
        v_suppressed = _v(line=3)
        v_kept = _v(line=1)
        result = filter_inline_ignores([v_suppressed, v_kept], content)
        assert result == [v_kept]

    def test_ignore_next_line_does_not_suppress_same_line(self):
        content = "x = 1\n# agentlint:ignore-next-line\ny = 2\n"
        # Directive is on line 2; violation on line 2 should NOT be suppressed
        v = _v(line=2)
        result = filter_inline_ignores([v], content)
        assert result == [v]

    def test_ignore_next_line_does_not_suppress_two_lines_later(self):
        content = "# agentlint:ignore-next-line\nx = 1\ny = 2\n"
        # Directive on line 1 suppresses line 2 only, not line 3
        v_line2 = _v(line=2)
        v_line3 = _v(line=3)
        result = filter_inline_ignores([v_line2, v_line3], content)
        assert result == [v_line3]

    def test_multiple_ignore_next_line(self):
        content = "# agentlint:ignore-next-line\nx = 1\n# agentlint:ignore-next-line\ny = 2\n"
        # Line 1 directive -> suppresses line 2; line 3 directive -> suppresses line 4
        v2 = _v(line=2)
        v3 = _v(line=3)
        v4 = _v(line=4)
        result = filter_inline_ignores([v2, v3, v4], content)
        assert result == [v3]

    def test_ignore_next_line_no_line_number(self):
        content = "# agentlint:ignore-next-line\nx = 1\n"
        v = _v(line=None)
        result = filter_inline_ignores([v], content)
        assert result == [v]

    def test_ignore_next_line_at_end_of_file(self):
        content = "x = 1\n# agentlint:ignore-next-line"
        # Directive on last line, no next line exists — should not crash
        v = _v(line=2)
        result = filter_inline_ignores([v], content)
        assert result == [v]

    def test_ignore_next_line_blank_line_between(self):
        content = "# agentlint:ignore-next-line\n\ny = 2\n"
        # Directive on line 1, blank line on line 2 (suppressed), violation on line 3 NOT suppressed
        v = _v(line=3)
        result = filter_inline_ignores([v], content)
        assert result == [v]

    def test_ignore_next_line_indented(self):
        content = "x = 1\n    # agentlint:ignore-next-line\n    y = 2\n"
        v = _v(line=3)
        result = filter_inline_ignores([v], content)
        assert result == []

    def test_ignore_next_line_combined_with_ignore_file(self):
        content = "# agentlint:ignore-file\n# agentlint:ignore-next-line\nx = 1\n"
        violations = [_v(line=1), _v(line=2), _v(line=3)]
        # ignore-file takes precedence — everything suppressed
        assert filter_inline_ignores(violations, content) == []

    # ── Edge cases (3+ tests) ──────────────────────────────────────────

    def test_empty_violations_list(self):
        content = "# agentlint:ignore-file\n"
        assert filter_inline_ignores([], content) == []

    def test_directive_in_string_literal(self):
        content = 'msg = "# agentlint:ignore-file"\nx = 1\n'
        # We scan raw content, not parsed AST — this SHOULD match
        violations = [_v()]
        assert filter_inline_ignores(violations, content) == []

    def test_ignore_with_tabs(self):
        content = "#\tagentlint:ignore-file\nx = 1\n"
        violations = [_v()]
        assert filter_inline_ignores(violations, content) == []

    # --- Additional adversarial tests ---

    def test_ignore_rule_trailing_whitespace(self):
        content = "# agentlint:ignore max-file-size   \nx = 1\n"
        v = _v(rule_id="max-file-size")
        assert filter_inline_ignores([v], content) == []

    def test_ignore_file_in_multiline_comment(self):
        content = '"""\n# agentlint:ignore-file\n"""\nx = 1\n'
        # Raw content scan matches inside docstrings too (by design)
        assert filter_inline_ignores([_v()], content) == []

    def test_ignore_next_line_multiple_violations_same_line(self):
        """Multiple violations on the same line, all suppressed."""
        content = "# agentlint:ignore-next-line\nx = 1\n"
        v1 = _v(rule_id="rule-a", line=2)
        v2 = _v(rule_id="rule-b", line=2)
        assert filter_inline_ignores([v1, v2], content) == []

    def test_ignore_rule_with_underscores(self):
        content = "# agentlint:ignore custom_rule_name\nx = 1\n"
        # Our regex is [\w-]+ which matches underscores
        v = _v(rule_id="custom_rule_name")
        assert filter_inline_ignores([v], content) == []

    def test_ignore_next_line_at_line_1(self):
        """Directive at line 1 suppresses line 2."""
        content = "# agentlint:ignore-next-line\nx = 1\n"
        v = _v(line=2)
        assert filter_inline_ignores([v], content) == []

    def test_no_false_negative_without_directive(self):
        """File with comments but no agentlint directives → all violations pass through."""
        content = "# This is a normal comment\n# Another comment\nx = 1\n"
        v = _v(rule_id="test-rule", line=3)
        assert filter_inline_ignores([v], content) == [v]

    def test_large_file_with_many_directives(self):
        """Performance: 1000-line file with 50 ignore-next-line directives."""
        lines = []
        for i in range(1000):
            if i % 20 == 0:
                lines.append("# agentlint:ignore-next-line")
            else:
                lines.append(f"x_{i} = {i}")
        content = "\n".join(lines)
        violations = [_v(line=i) for i in range(1, 1001)]
        result = filter_inline_ignores(violations, content)
        # 50 lines should be suppressed (the lines after each directive)
        assert len(result) == 950

    def test_mixed_ignore_file_and_ignore_rule(self):
        """ignore-file takes precedence over ignore-rule."""
        content = "# agentlint:ignore-file\n# agentlint:ignore specific-rule\n"
        v1 = _v(rule_id="specific-rule")
        v2 = _v(rule_id="other-rule")
        assert filter_inline_ignores([v1, v2], content) == []  # ignore-file wins
