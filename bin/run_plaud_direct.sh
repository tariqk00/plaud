#!/bin/bash
# Wrapper to run Plaud Direct API automation with correct PYTHONPATH

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
PARENT_DIR="$(dirname "$REPO_ROOT")"
TOOLBOX_DIR="$PARENT_DIR/toolbox"

export PYTHONPATH="$REPO_ROOT:$PARENT_DIR:${PYTHONPATH:-}"

# Use plaud venv if present, then shared toolbox runtime, then compatibility venv, then system python
if [ -f "$REPO_ROOT/venv/bin/python3" ]; then
    PYTHON_EXEC="$REPO_ROOT/venv/bin/python3"
elif [ -f "$TOOLBOX_DIR/venv/bin/python3" ]; then
    PYTHON_EXEC="$TOOLBOX_DIR/venv/bin/python3"
elif [ -f "$TOOLBOX_DIR/google-drive/venv/bin/python3" ]; then
    PYTHON_EXEC="$TOOLBOX_DIR/google-drive/venv/bin/python3"
else
    PYTHON_EXEC="/usr/bin/python3"
fi

echo "Starting Plaud Direct..."
echo "Repo Root: $REPO_ROOT"
echo "Python: $PYTHON_EXEC"

exec "$PYTHON_EXEC" "$REPO_ROOT/bin/plaud_direct.py"
