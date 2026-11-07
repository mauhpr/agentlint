"""Sensitive data filenames retain detection without matching detector modules."""

from __future__ import annotations

import pytest

from agentlint.models import HookEvent, RuleContext
from agentlint.packs.universal.no_secrets import NoSecrets


@pytest.mark.parametrize(
    "filename",
    [
        "credentials.json",
        "secrets.prod.yaml",
        "aws_credentials.json",
        "app-secrets.yml",
        ".credentials.json",
    ],
)
def test_multipart_sensitive_data_filename(filename):
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Write",
        project_dir="/app",
        tool_input={"file_path": f"/app/{filename}", "content": "{}"},
    )
    assert NoSecrets().evaluate(context)


@pytest.mark.parametrize("filename", ["no_secrets.py", "secretsauce.json"])
def test_ordinary_detector_or_unrelated_filename(filename):
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Write",
        project_dir="/app",
        tool_input={"file_path": f"/app/{filename}", "content": "{}"},
    )
    assert NoSecrets().evaluate(context) == []
