"""Exercise race defenses and conservative classification at release boundaries."""

from __future__ import annotations

import os
import shlex

import pytest

import agentlint.approvals as approvals
from agentlint.models import HookEvent, RuleContext
from agentlint.packs.quality.no_error_handling_removal import NoErrorHandlingRemoval
from agentlint.packs.security.no_bash_file_write import NoBashFileWrite


@pytest.mark.parametrize(
    "mutation,error",
    [("unchanged", None), ("grow", "size limit"), ("replace", "changed during inspection")],
)
def test_upload_inspection_rejects_bytes_changed_while_hashing(
    tmp_path, monkeypatch, mutation, error
):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    original_hash = approvals.hashlib.sha256

    class DigestWithMutation:
        def __init__(self):
            self.digest = original_hash()
            self.updated = False

        def update(self, data):
            self.digest.update(data)
            if self.updated:
                return
            self.updated = True
            if mutation == "grow":
                with source.open("ab") as file:
                    file.write(b"more")
            elif mutation == "replace":
                before = source.stat()
                source.write_bytes(b"other")
                # A distinct timestamp makes the same-size race deterministic.
                os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))

        def hexdigest(self):
            return self.digest.hexdigest()

    monkeypatch.setattr(approvals.hashlib, "sha256", DigestWithMutation)
    operation = (
        f"curl --disable --request POST --upload-file {source} "
        "'https://storage.googleapis.com/upload/storage/v1/b/private/o?uploadType=media&name=video.mp4&ifGenerationMatch=0'"
    )
    options = dict(
        repository=str(tmp_path), reason="hash race boundary", operation=operation, max_bytes=5
    )
    if error:
        with pytest.raises(ValueError, match=error):
            approvals.create_grant("cloud-upload", **options)
        assert approvals.active_grants() == []
    else:
        grant = approvals.create_grant("cloud-upload", **options)
        assert grant["upload"]["source_sha256"] == original_hash(b"video").hexdigest()
        assert approvals.matching_grant(
            "no-network-exfil", repository=str(tmp_path), command=operation
        )


@pytest.mark.parametrize(
    "case,warning",
    [
        ("nested-old-guard", True),
        ("renamed-scope", True),
        ("duplicate-scope", True),
        ("malformed-helper", True),
        ("malformed-caller", True),
        ("exception-rebinding", True),
        ("pattern-rebinding", True),
        ("docstring", False),
        ("parent-relative-import", False),
    ],
)
def test_guard_extraction_requires_unambiguous_valid_scopes(tmp_path, case, warning):
    old = "def run(result):\n    if result is None:\n        raise ValueError('missing')\n"
    new = "from .guards import check\ndef run(result):\n    check(result)\n"
    helper = "def check(result):\n    if result is None:\n        raise ValueError('missing')\n"
    helper_path = tmp_path / "pkg" / "guards.py"
    if case == "nested-old-guard":
        old = "def run(result):\n    if enabled:\n        if result is None:\n            raise ValueError('missing')\n"
    elif case == "renamed-scope":
        new = new.replace("def run", "def renamed")
    elif case == "duplicate-scope":
        new += "def run(result):\n    check(result)\n"
    elif case == "malformed-helper":
        helper = "def check(\n"
    elif case == "malformed-caller":
        new = "from .guards import check\ndef run(\n"
    elif case == "exception-rebinding":
        helper += "try:\n    load()\nexcept ValueError as check:\n    pass\n"
    elif case == "pattern-rebinding":
        helper += "match values:\n    case [*check]:\n        pass\n"
    elif case == "docstring":
        helper = helper.replace(
            "def check(result):\n", 'def check(result):\n    """Validate result."""\n'
        )
    elif case == "parent-relative-import":
        new = new.replace("from .guards", "from ..guards")
        helper_path = tmp_path / "guards.py"
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Edit",
        project_dir=str(tmp_path),
        tool_input={"file_path": "pkg/app.py", "content": new},
        file_content=new,
        file_content_before=old,
        related_files={str(helper_path): helper},
    )
    assert bool(NoErrorHandlingRemoval().evaluate(context)) is warning


@pytest.mark.parametrize(
    "invocation",
    [
        "arguments",
        "'git cat-file -e HEAD'",
        "['git', 'cat-file', '-e']",
        "['git', 'cat-file', '-e', 123]",
        "['git', 'cat-file', '-e', '-unknown-option']",
        "['git', 'cat-file', '-e', 'HEAD;other']",
        "['git', 'checkout', '-e', 'HEAD']",
        "['git', 'cat-file', '-e', 'HEAD'], extra",
        "['git', 'cat-file', '-e', 'HEAD'], timeout=0",
        "['git', 'cat-file', '-e', 'HEAD'], timeout=True",
        "['git', 'cat-file', '-e', 'HEAD'], check=1",
        "['git', 'cat-file', '-e', 'HEAD'], cwd='/elsewhere'",
    ],
)
def test_unsupported_git_subprocess_forms_remain_blocked(invocation):
    # These payloads are inspected as text; subprocess.run is never executed.
    code = f"import subprocess; subprocess.run({invocation})"
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        project_dir="/project",
        tool_input={"command": "python3 -c " + shlex.quote(code)},
    )
    findings = NoBashFileWrite().evaluate(context)
    assert findings
    assert "Cannot classify" in findings[0].message


def test_supported_git_options_keep_the_read_only_exemption():
    code = "import subprocess; subprocess.run(('git', 'cat-file', '-e', 'HEAD'), shell=False, timeout=1, check=False, capture_output=True, text=True)"
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        project_dir="/project",
        tool_input={"command": "python3 -c " + shlex.quote(code)},
    )
    assert NoBashFileWrite().evaluate(context) == []
