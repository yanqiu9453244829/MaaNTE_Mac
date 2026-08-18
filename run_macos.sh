#!/usr/bin/env bash
# run_macos.sh - MaaNTE macOS one-click launcher
# Usage: chmod +x run_macos.sh && ./run_macos.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" ; pwd)"
cd "$SCRIPT_DIR"

VENV="$SCRIPT_DIR/.venv"
REQ="$SCRIPT_DIR/requirements-macos.txt"

echo "[MaaNTE] macOS GUI Launcher"
echo "[MaaNTE] Project: $SCRIPT_DIR"

# Create venv if missing
if [ ! -d "$VENV" ]; then
    echo "[MaaNTE] Creating virtual environment..."
    python3 -m venv "$VENV"
    echo "[MaaNTE] Installing dependencies (first run, may take a few minutes)..."
    "$VENV/bin/pip" install --upgrade pip -q
    "$VENV/bin/pip" install -r "$REQ" -q
    echo "[MaaNTE] Dependencies installed"
fi

# Reinstall if maafw is missing (e.g. after a Python upgrade)
if ! "$VENV/bin/python3" -c "import maa" 2>/dev/null; then
    echo "[MaaNTE] maafw not found, installing dependencies..."
    "$VENV/bin/pip" install -r "$REQ" -q
fi

echo "[MaaNTE] Starting GUI..."
exec "$VENV/bin/python3" "$SCRIPT_DIR/maante_gui.py" "$@"
