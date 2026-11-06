"""Evaluate command text only: none of these Python payloads are executed."""

from __future__ import annotations

import shlex

import pytest

from agentlint.models import HookEvent, RuleContext
from agentlint.packs.security.no_bash_file_write import NoBashFileWrite


def violations(command: str):
    return NoBashFileWrite().evaluate(
        RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": command},
            project_dir="/project",
        )
    )


@pytest.mark.parametrize(
    "prefix",
    [
        "python",
        "python3",
        ".venv/bin/python",
        "python3.12 -I",
        "env MODE=dev python3 -B",
        "command python3",
        "/usr/bin/python3.13 -B -I",
        "/usr/bin/env MODE=dev command python3 -OO",
        "python2.7 -u",
        "python3 -E -q -s -S",
    ],
)
@pytest.mark.parametrize(
    "code",
    [
        "from pathlib import Path; print(Path('report.json'))",
        "from pathlib import Path as P; print(P('report.json').read_text())",
        "import pathlib; print(pathlib.Path('report.json').read_bytes())",
        "print(open('report.json').read())",
        "print(open('report.json', 'rb').read())",
        "print(open(file='report.json', mode='rt').read())",
        "from io import open as read_file; print(read_file('report.json', 'r').read())",
        "import io as i; print(i.open('report.json', mode='rb').read())",
        "from pathlib import Path; print(Path('report.json').open().read())",
        "from pathlib import Path; print(Path('report.json').open('rb').read())",
        "print(\"Path('example').write_text('documentation')\")",
        "print(open('report.json', 'br').read())",
        "print(open('report.json', 'tr').read())",
        "from builtins import open as read_file; print(read_file('report.json').read())",
        "print('no file access')",
        "print(payload['open'])",
        "print(payload[key])",
        "lookup[key]()",
        "lookup['read']()",
        "import shutil; print(shutil.which('python'))",
        "import subprocess; print(subprocess.list2cmdline(['python']))",
        "print({'field': 1}.copy())",
        "from source import run; run()",
        "obj" + ".attr" * 1100,
    ],
)
def test_literal_reads_are_not_file_writes(prefix, code):
    assert violations(f"{prefix} -c {shlex.quote(code)}") == []


def test_reported_bundle_verification_is_allowed():
    code = (
        "from pathlib import Path; from source import load_bundle, validate_context_change; "
        "b=Path('/project/evidence'); original=load_bundle(b/'original/bundle.json'); "
        "amended=load_bundle(b/'corrected/bundle.json'); "
        "validate_context_change(original[1],amended[1]); "
        "assert original[0]['source_object']==amended[0]['source_object'] "
        "and original[2]==amended[2]; print('Source object and bytes unchanged')"
    )
    assert violations(f".venv/bin/python -c {shlex.quote(code)}") == []


@pytest.mark.parametrize(
    "code",
    [
        "open('file', 'w')",
        "open('file', 'a')",
        "open('file', 'x')",
        "open('file', 'r+')",
        "open('file', mode='wb')",
        "open('file', mode=mode)",
        "open(*args)",
        "open('file', **kwargs)",
        "from pathlib import Path; Path('file').write_text('data')",
        "from pathlib import Path; Path('file').write_bytes(b'data')",
        "from pathlib import Path; Path('file').open('w')",
        "from pathlib import Path; Path('file').open(mode='a')",
        "import pathlib as p; p.Path('file').open('w')",
        "from io import open as save; save('file', 'w')",
        "import builtins as b; b.open('file', 'w')",
        "import os; os.open('file', flags)",
        "from os import open as os_open; os_open('file', flags)",
        "handle.write('data')",
        "handle.writelines(['data'])",
        "handle.truncate()",
        "from pathlib import Path; save=Path('file').write_text; save('data')",
        "from pathlib import Path; Path('file').touch()",
        "from pathlib import Path; Path('file').rename('other')",
        "from pathlib import Path; Path('file').unlink()",
        "exec(\"from pathlib import Path; Path('file').write_text('data')\")",
        "from pathlib import Path; getattr(Path('file'), method)('data')",
        "save = open; save('file', 'w')",
        "import io; save = io.open; save('file', 'w')",
        "from io import open as opener; save = opener; save('file', 'w')",
        "from pathlib import Path; save = Path('file').open; save('w')",
        "ex = exec; ex(payload)",
        "open('file', f'{mode}')",
        "open('file', None)",
        "write_text('data')",
        "__import__('module')",
        "compile(source, '<string>', 'exec')",
        "globals()['open']('file', 'w')",
        "locals()['open']('file', 'w')",
        "vars(builtins)['open']('file', 'w')",
        "__builtins__['open']('file', 'w')",
        "__builtins__[key]('file', 'w')",
        "import builtins as b; b.__dict__[key]('file', 'w')",
        "import builtins as b; b.__dict__['open']('file', 'w')",
        "lookup['open']('file', 'w')",
        "lookup['exec'](payload)",
        "import os; os.remove('file')",
        "import os as o; o.makedirs('directory')",
        "from os import removedirs as remove; remove('directory')",
        "import os; os.symlink('file', 'link')",
        "import os; os.link('file', 'link')",
        "import shutil; shutil.copy('file', 'other')",
        "import shutil as s; s.copy2('file', 'other')",
        "from shutil import copyfile as save; save('file', 'other')",
        "import shutil; shutil.copytree('directory', 'other')",
        "import shutil; shutil.move('file', 'other')",
        "import shutil; shutil.rmtree('directory')",
        "import shutil; save = shutil.copy; save('file', 'other')",
        "import os; os.system(command)",
        "from os import popen as spawn; spawn(command)",
        "import subprocess; subprocess.run(['command'])",
        "import subprocess as s; s.call(['command'])",
        "from subprocess import check_call as spawn; spawn(['command'])",
        "import subprocess; subprocess.check_output(['command'])",
        "import subprocess; subprocess.Popen(['command'])",
        "obj" + ".attr" * 1100 + ".open('w')",
    ],
)
def test_writes_and_unknown_modes_remain_blocked(code):
    result = violations(f".venv/bin/python -c {shlex.quote(code)}")
    assert len(result) == 1
    assert result[0].rule_id == "no-bash-file-write"
    assert result[0].operation
    assert "Python" in result[0].message


@pytest.mark.parametrize(
    "command",
    [
        "python -c \"print(open('file').read())\" && echo data > target",
        "python -c \"from pathlib import Path; print(Path('file'))\"; python -c \"open('file','w')\"",
        "python -c \"from pathlib import Path; Path('file').write_text('data')\" > /tmp/log",
        "python -c \"from pathlib import Path; print(Path('$(touch file)'))\"",
        'python -c "open(',
        'python -c "open(' + "(" * 300 + '"',
        "python -c \"open('file','w');" + " " * 65536 + '"',
        "python -X dev -c \"open('file','w')\"",
        "python -W ignore -c \"open('file','w')\"",
        "python -c\"open('file','w')\"",
        'python -Bu -c "handle.truncate()"',
        "python -X dev -c \"from io import open as save; save('file','w')\"",
        "python -c \"open('file', 'w')\" > /dev/null",
        "python -c \"open('file', 'w')\" 2>/tmp/log",
        "python -c \"open('file', 'w')\" > scratch/log",
        "python -c \"handle.writelines(['data'])\" > /tmp/log",
        'python -c "exec(payload)" > /tmp/log',
        "python -c \"open('file', 'w')\"\n",
        "python -c \"open('file', 'w')\x00\"",
        "env -i python -c \"open('file', 'w')\"",
        "python -X dev -c \"globals()['open']('file', 'w')\"",
        "python -X dev -c \"__builtins__['open']('file', 'w')\"",
        "python -X dev -c \"from shutil import copy as save; save('file', 'other')\"",
        "python -X dev -c \"from subprocess import run as spawn; spawn(['command'])\"",
    ],
)
def test_unsupported_commands_do_not_gain_a_read_exception(command):
    assert violations(command)


@pytest.mark.parametrize("error", [SyntaxError, ValueError, RecursionError])
def test_parser_failure_keeps_text_detection(monkeypatch, error):
    def fail_parse(source):
        raise error

    monkeypatch.setattr("agentlint.packs.security.no_bash_file_write.ast.parse", fail_parse)
    assert violations("python -c \"open('file', 'w')\"")


def test_empty_wrapper_is_not_a_python_write():
    assert violations("command") == []


@pytest.mark.parametrize(
    "suffix",
    [
        "> maintained.py",
        "2> maintained.py",
        ">> maintained.py",
        "&> maintained.py",
        "&>> maintained.py",
        ">& maintained.py",
        '> "maintained file.py"',
    ],
)
def test_readonly_python_still_blocks_shell_redirect_writes(suffix):
    command = "python -c \"from pathlib import Path; print(Path('input').read_text())\" " + suffix
    assert violations(command)


@pytest.mark.parametrize("target", ["/dev/null", "/tmp/check.json", "/private/tmp/check.json"])
def test_readonly_python_allows_ephemeral_output(target):
    assert violations(f'python -c "print(1)" > {target}') == []


@pytest.mark.parametrize("redirect", ["2>&1", "1>&-", "< input.json"])
def test_python_descriptor_operations_and_input_are_not_file_writes(redirect):
    assert violations(f'python -c "print(1)" {redirect}') == []


def test_scratch_redirect_does_not_hide_python_write():
    assert violations("python -c \"open('maintained.py', 'w')\" > /tmp/check.json")


def test_cloud_cli_exemption_cannot_hide_shell_redirect():
    assert violations("gh pr view 85 > maintained.py")


def test_later_rg_flags_do_not_turn_sed_read_into_write():
    assert (
        violations(
            "sed -n '1,20p' README.md; rg --files .github | "
            "rg -i 'pull_request_template|contributing'"
        )
        == []
    )
    assert violations("python -c \"print(Path('file'))\" | cat") == []


def test_literal_string_replace_is_not_path_replace():
    assert violations("python -c \"print('old'.replace('old', 'new'))\"") == []
    assert violations("python -c \"from pathlib import Path; Path('old').replace('new')\"")


@pytest.mark.parametrize(
    "code",
    [
        "import json; from pathlib import Path; print(json.loads(Path('a').read_text()))",
        "import hashlib; from pathlib import Path; print(hashlib.sha256(Path('a').read_bytes()).hexdigest() == hashlib.sha256(Path('b').read_bytes()).hexdigest())",
        "from source import read_bundle; print(read_bundle('a') == read_bundle('b'))",
    ],
)
def test_json_hash_and_repository_helper_inspection(code):
    assert violations(f"python -c {shlex.quote(code)}") == []
    assert violations(f"python - <<'PY'\n{code}\nPY") == []


def test_python_diagnostic_distinguishes_write_from_unknown():
    write = violations("python -c \"from pathlib import Path\nPath('a').write_text('b')\"")[0]
    unknown = violations('python -c "open(path, mode)"')[0]
    assert write.line == 2
    assert "write_text" in write.operation
    assert "confirmed" in write.message.lower()
    assert "cannot classify" in unknown.message.lower()
    assert unknown.line == 1


@pytest.mark.parametrize(
    "source",
    [
        "from pathlib import Path; Path('a').replace('b')",
        "from pathlib import Path as P; P('a').unlink()",
        "open('a', 'w')",
    ],
)
def test_known_mutations_remain_confirmed(source):
    result = violations(f"python -c {shlex.quote(source)}")[0]
    assert "Confirmed" in result.message


def test_untyped_methods_stay_blocked_without_claiming_proven_write():
    for source in ["obj.replace('a', 'b')", "obj.write('a')", "exec(payload)"]:
        assert "Cannot classify" in violations(f"python -c {shlex.quote(source)}")[0].message


@pytest.mark.parametrize(
    "source",
    [
        "from pathlib import Path; save=Path('a').write_text; print(save)",
        "import os; print(os.remove)",
    ],
)
def test_uninvoked_mutator_reference_is_inconclusive(source):
    assert "Cannot classify" in violations(f"python -c {shlex.quote(source)}")[0].message


def test_python_diagnostics_do_not_echo_argument_values():
    result = violations(
        "python -c \"from pathlib import Path; Path('secret-path').write_text('secret-value')\""
    )[0]
    assert "secret" not in result.message
    assert "secret" not in result.operation


def test_scratch_exemption_cannot_hide_another_operation_write():
    assert violations("echo x > /tmp/log; cp source maintained.py")
    assert violations("cp source maintained.py; echo x > /tmp/log")
    assert violations("sed -i s/a/b/ maintained.py; rg -i query /tmp/log")
    assert violations("gcloud storage ls; echo x > maintained.py")
    assert violations("echo x > /tmp/log; tee maintained.py")
    assert violations("echo x > /tmp/log; echo y > /private/tmp/log") == []


def test_unrelated_allow_path_cannot_exempt_python_write():
    result = NoBashFileWrite().evaluate(
        RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "python -c \"open('file', 'w')\" > scratch/log"},
            project_dir="/project",
            config={"no-bash-file-write": {"allow_paths": ["scratch/*"]}},
        )
    )
    assert len(result) == 1
    assert result[0].file_path is None
