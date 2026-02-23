#!/bin/sh
# Resolve the agentlint binary across common install methods.
# Claude Code runs hooks via /bin/sh with a minimal PATH, so we
# probe well-known locations before falling back to python -m.

set -e

if command -v agentlint >/dev/null 2>&1; then
  exec agentlint "$@"
elif [ -x "$HOME/.local/bin/agentlint" ]; then
  exec "$HOME/.local/bin/agentlint" "$@"
elif [ -x "$HOME/.local/share/uv/tools/agentlint/bin/agentlint" ]; then
  exec "$HOME/.local/share/uv/tools/agentlint/bin/agentlint" "$@"
else
  # Probe the Python sysconfig scripts dir (where pip puts console_scripts).
  # Covers Framework installs like /Library/Frameworks/Python.framework/.
  SCRIPTS_DIR=$(python3 -c "import sysconfig; print(sysconfig.get_path('scripts'))" 2>/dev/null)
  if [ -n "$SCRIPTS_DIR" ] && [ -x "$SCRIPTS_DIR/agentlint" ]; then
    exec "$SCRIPTS_DIR/agentlint" "$@"
  elif python3 -m agentlint --help >/dev/null 2>&1; then
    exec python3 -m agentlint "$@"
  elif python -m agentlint --help >/dev/null 2>&1; then
    exec python -m agentlint "$@"
  else
    echo "agentlint: command not found. Install with: pip install agentlint" >&2
    exit 127
  fi
fi
