#!/bin/bash
# Wrapper to run Plaud automation with correct PYTHONPATH
# This script ensures that the 'toolbox' dependency is found.

# Resolve script directory (plaud/bin)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# Repo root (plaud)
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
# Toolbox root (assuming sibling directory)
TOOLBOX_DIR="$(dirname "$REPO_ROOT")/toolbox"

if [ ! -d "$TOOLBOX_DIR" ]; then
    echo "Error: toolbox directory not found at $TOOLBOX_DIR"
    # Fallback to checking typical paths
    if [ -d "$HOME/github/tariqk00/toolbox" ]; then
        TOOLBOX_DIR="$HOME/github/tariqk00/toolbox"
    elif [ -d "$HOME/repos/personal/toolbox" ]; then
        TOOLBOX_DIR="$HOME/repos/personal/toolbox"
    else
        echo "Critical: Could not locate toolbox directory."
        exit 1
    fi
fi

# Set PYTHONPATH to include plaud root and the parent of the toolbox root (to import 'toolbox' as a package)
PARENT_DIR="$(dirname "$REPO_ROOT")"
export PYTHONPATH="$REPO_ROOT:$PARENT_DIR:$PYTHONPATH"

# Detect Python Executable (prefer local venv, then shared toolbox runtime).
if [ -f "$REPO_ROOT/venv/bin/python3" ]; then
    PYTHON_EXEC="$REPO_ROOT/venv/bin/python3"
elif [ -f "$TOOLBOX_DIR/venv/bin/python3" ]; then
    PYTHON_EXEC="$TOOLBOX_DIR/venv/bin/python3"
elif [ -f "$TOOLBOX_DIR/google-drive/venv/bin/python3" ]; then
    PYTHON_EXEC="$TOOLBOX_DIR/google-drive/venv/bin/python3"
else
    PYTHON_EXEC="/usr/bin/python3"
fi

echo "Starting Plaud Automation..."
echo "Repo Root: $REPO_ROOT"
echo "Toolbox: $TOOLBOX_DIR"
echo "Python: $PYTHON_EXEC"

# Execute logic
$PYTHON_EXEC "$REPO_ROOT/src/automation.py"
