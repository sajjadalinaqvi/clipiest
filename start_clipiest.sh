#!/usr/bin/env bash
set -e

# ============================================================
#                 CLIPIEST MASTER ENGINE (LINUX / MACOS)
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PATH=""

# 1. Check if .venv or venv exists
if [ -d "$SCRIPT_DIR/.venv" ] && [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    VENV_PATH="$SCRIPT_DIR/.venv"
elif [ -d "$SCRIPT_DIR/venv" ] && [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    VENV_PATH="$SCRIPT_DIR/venv"
fi

# 2. If not found, create .venv and install requirements
if [ -z "$VENV_PATH" ]; then
    echo "[Clipiest] Virtual environment (.venv / venv) not found."
    echo "[Clipiest] Creating virtual environment (.venv)..."

    # Detect python3 or python
    if command -v python3 &>/dev/null; then
        PY_CMD="python3"
    elif command -v python &>/dev/null; then
        PY_CMD="python"
    else
        echo "[ERROR] Python 3 is not installed or not in PATH!"
        echo "Please install Python 3.10+ (e.g. sudo apt install python3 python3-venv)"
        exit 1
    fi

    echo "[Clipiest] Using Python: $PY_CMD"
    "$PY_CMD" -m venv "$SCRIPT_DIR/.venv"
    VENV_PATH="$SCRIPT_DIR/.venv"

    echo "[Clipiest] Activating .venv and installing requirements..."
    source "$VENV_PATH/bin/activate"
    pip install --upgrade pip

    if [ -f "$SCRIPT_DIR/backend/requirements.txt" ]; then
        pip install -r "$SCRIPT_DIR/backend/requirements.txt"
    elif [ -f "$SCRIPT_DIR/requirements.txt" ]; then
        pip install -r "$SCRIPT_DIR/requirements.txt"
    else
        echo "[WARNING] No requirements.txt found!"
    fi
else
    echo "[Clipiest] Found virtual environment at: $VENV_PATH"
    echo "[Clipiest] Activating virtual environment..."
    source "$VENV_PATH/bin/activate"
fi

# 3. Launch server with run.py
echo "[Clipiest] Launching Clipiest Engine..."
cd "$SCRIPT_DIR/backend"
python run.py
