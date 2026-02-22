---
name: fix
description: Auto-fix common AgentLint violations in the codebase
---

You are an auto-fix agent for common AgentLint violations.

## Steps

1. **Check current status:**
   Run `agentlint status` to see the current session state and active rules.

2. **Scan for fixable violations:**
   For each violation type below, search the project files and propose fixes:

   - **no-debug-artifacts**: Find and remove leftover debug statements:
     - `console.log(`, `console.debug(`, `console.warn(` (JS/TS)
     - `print(` debugging statements, `breakpoint()` (Python)
     - `debugger` statements (JS/TS)

   - **a11y-image-alt**: Find `<img>` tags without `alt` attributes and add descriptive alt text based on context (image filename, surrounding text).

   - **a11y-form-labels**: Find `<input>`, `<select>`, `<textarea>` elements without associated `<label>` elements and add appropriate labels.

   - **no-todo-left**: Find TODO, FIXME, HACK, and XXX comments. For each one:
     - Show the comment and surrounding context
     - Suggest whether to resolve it, convert to an issue, or keep it
     - Only remove if the TODO has been addressed

   - **no-dead-imports**: Find unused imports in Python and JS/TS files and remove them.

3. **Show proposed changes:**
   For each fix, display a clear diff of what will change. Group changes by file.

4. **Apply fixes:**
   Only apply changes after the user confirms. Apply one category at a time to allow selective approval.

5. **Verify:**
   After applying fixes, run a quick check to confirm the violations are resolved.
