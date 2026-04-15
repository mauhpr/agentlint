"""Tests for agentlint.utils.bash."""
from agentlint.utils.bash import get_command_binary, strip_string_args


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


class TestGetCommandBinary:
    def test_simple_command(self):
        assert get_command_binary("bq cp dataset.t1 dataset.t2") == "bq"

    def test_sudo_prefix(self):
        assert get_command_binary("sudo bq cp dataset.t1 dataset.t2") == "bq"

    def test_env_prefix(self):
        assert get_command_binary("env VAR=val gcloud compute ssh") == "gcloud"

    def test_env_var_assignment(self):
        assert get_command_binary("PYTHONPATH=/app python script.py") == "python"

    def test_nohup_prefix(self):
        assert get_command_binary("nohup kubectl apply -f deploy.yml") == "kubectl"

    def test_empty_string(self):
        assert get_command_binary("") == ""

    def test_single_command(self):
        assert get_command_binary("ls") == "ls"

    def test_regular_command(self):
        assert get_command_binary("cp file1.txt file2.txt") == "cp"

    def test_multiple_wrappers(self):
        assert get_command_binary("sudo nice aws s3 cp s3://b/k /tmp/") == "aws"
