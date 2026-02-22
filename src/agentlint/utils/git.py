"""Git utilities for AgentLint."""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

logger = logging.getLogger("agentlint")


def get_changed_files(project_dir: str) -> list[str]:
    """Get list of files changed (staged + unstaged) vs HEAD, plus untracked files."""
    root = Path(project_dir)
    files: set[str] = set()

    # Staged + unstaged changes vs HEAD.
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            files.update(str(root / f) for f in result.stdout.strip().split("\n") if f)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Untracked files (new files not yet committed).
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            files.update(str(root / f) for f in result.stdout.strip().split("\n") if f)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return sorted(files)


def is_git_repo(project_dir: str) -> bool:
    """Check if the directory is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def git_has_changes(project_dir: str) -> bool:
    """Check if the working tree has uncommitted changes (staged or unstaged)."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def git_stash_push(project_dir: str, message: str) -> bool:
    """Create a git stash with the given message. Returns True if stash was created."""
    try:
        result = subprocess.run(
            ["git", "stash", "push", "-m", message],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and "No local changes" not in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        logger.debug("git stash push failed", exc_info=True)
        return False


def git_clean_stashes(project_dir: str, prefix: str, max_age_hours: int) -> int:
    """Remove stashes matching prefix older than max_age_hours. Returns count removed."""
    try:
        result = subprocess.run(
            ["git", "stash", "list"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return 0

    now = time.time()
    cutoff = now - (max_age_hours * 3600)
    removed = 0

    # Parse stash list, find matching entries.
    # Format: stash@{N}: On branch: message
    lines = result.stdout.strip().splitlines()
    # Process from highest index to lowest to avoid index shifting.
    stash_indices: list[int] = []
    for line in lines:
        if prefix not in line:
            continue
        # Extract stash index.
        try:
            idx_str = line.split("stash@{")[1].split("}")[0]
            stash_indices.append(int(idx_str))
        except (IndexError, ValueError):
            continue

    # Get stash creation times and drop old ones.
    for idx in sorted(stash_indices, reverse=True):
        try:
            ts_result = subprocess.run(
                ["git", "log", "-1", "--format=%ct", f"stash@{{{idx}}}"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if ts_result.returncode != 0:
                continue
            stash_time = int(ts_result.stdout.strip())
            if stash_time < cutoff:
                drop_result = subprocess.run(
                    ["git", "stash", "drop", f"stash@{{{idx}}}"],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if drop_result.returncode == 0:
                    removed += 1
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
            continue

    return removed
