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
        "lookup['read']()",
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
        "import builtins as b; b.__dict__['open']('file', 'w')",
        "lookup['open']('file', 'w')",
        "lookup['exec'](payload)",
        "obj" + ".attr" * 1100 + ".open('w')",
    ],
)
def test_writes_and_unknown_modes_remain_blocked(code):
    result = violations(f".venv/bin/python -c {shlex.quote(code)}")
    assert len(result) == 1
    assert result[0].rule_id == "no-bash-file-write"
    assert result[0].message.endswith("python -c write")


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
        "python -c \"print(Path('file'))\" | cat",
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
