"""Tests for agentlint.utils.bash."""
from agentlint.utils.bash import strip_string_args


class TestStripStringArgs:
    def test_strips_quoted_content(self):
        assert strip_string_args('gh pr create --body "pip install foo"') == 'gh pr create --body ""'

    def test_preserves_unquoted(self):
        assert strip_string_args("pip install requests") == "pip install requests"

    def test_preserves_command_substitution(self):
        result = strip_string_args('git commit -m "$(cat <<\'EOF\'\nhello\nEOF\n)"')
        assert "$(cat <<'EOF'" in result

    def test_multiple_quoted_args(self):
        result = strip_string_args('cmd "first arg" --flag "second arg"')
        assert result == 'cmd "" --flag ""'

    def test_escaped_quote_inside(self):
        result = strip_string_args(r'echo "hello \"world\""')
        assert result == 'echo ""'

    def test_no_quotes(self):
        assert strip_string_args("ls -la /tmp") == "ls -la /tmp"

    def test_empty_string(self):
        assert strip_string_args("") == ""

    def test_nested_command_sub_preserved(self):
        result = strip_string_args('echo "$(pip install requests)"')
        assert "pip install requests" in result

    def test_preserves_single_quotes(self):
        """Single quotes are intentionally not stripped."""
        assert strip_string_args("echo 'pip install malware'") == "echo 'pip install malware'"
