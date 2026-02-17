"""Git utilities for AgentLint."""
from __future__ import annotations

import subprocess
from pathlib import Path


def get_changed_files(project_dir: str) -> list[str]:
    """Get list of files changed (staged + unstaged) vs HEAD."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            root = Path(project_dir)
            return [str(root / f) for f in result.stdout.strip().split("\n") if f]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []
