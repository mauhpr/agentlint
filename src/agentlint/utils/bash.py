"""Bash command parsing utilities."""
from __future__ import annotations

def strip_string_args(command: str) -> str:
    """Strip content inside double-quoted string arguments.

    Preserves command structure while removing string literal content that
    could cause false positive pattern matches. For example:

        gh pr create --body "verify pip install works"
        →  gh pr create --body ""

    Handles nested command substitutions: content inside $(...) within
    quotes is preserved because it contains actual commands.
    """
    result: list[str] = []
    i = 0
    n = len(command)

    while i < n:
        if command[i] == '"':
            # Found opening double quote — scan to closing quote
            result.append('"')
            i += 1
            depth = 0  # track $(...) nesting
            while i < n:
                if command[i] == '$' and i + 1 < n and command[i + 1] == '(':
                    # Entering command substitution — preserve content
                    depth += 1
                    result.append(command[i])
                elif command[i] == '(' and depth > 0:
                    depth += 1
                    result.append(command[i])
                elif command[i] == ')' and depth > 0:
                    depth -= 1
                    result.append(command[i])
                elif command[i] == '"' and depth == 0:
                    # Closing quote (not inside command substitution)
                    result.append('"')
                    i += 1
                    break
                elif command[i] == '\\' and i + 1 < n:
                    # Escaped character inside quotes — skip both
                    i += 2
                    continue
                elif depth > 0:
                    # Inside command substitution — preserve
                    result.append(command[i])
                # else: inside quotes but outside $() — strip (don't append)
                i += 1
        else:
            result.append(command[i])
            i += 1

    return "".join(result)
