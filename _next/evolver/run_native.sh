#!/usr/bin/env bash
# Native macOS Metal evolver — no Podman.
# Run from repo root:  bash evolver/run_native.sh [--resume] [--epochs N]

set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
echo "Repo root: $REPO"

VENV="$REPO/.venv-evolver"

# Prefer newest python (MPS requires 3.11+)
for PYTHON in python3.14 python3.13 python3.12 python3.11 \
              /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if command -v "$PYTHON" &>/dev/null 2>&1; then
    break
  fi
done
echo "Using Python: $PYTHON ($($PYTHON --version 2>&1))"

# Create venv if missing
if [ ! -d "$VENV" ]; then
  echo "Creating virtualenv $VENV …"
  "$PYTHON" -m venv "$VENV"
  if [ ! -f "$VENV/bin/activate" ]; then
    echo "venv creation failed — trying --without-pip"
    "$PYTHON" -m venv --without-pip "$VENV" || { echo "venv creation failed"; exit 1; }
  fi
fi

source "$VENV/bin/activate" || { echo "Failed to activate venv"; exit 1; }

# Install / update deps
pip install -q --upgrade pip
pip install -q -r evolver/requirements_native.txt

# Ensure gallery dir exists
mkdir -p "$REPO/gallery"

# Run
exec python "$REPO/evolver/evolver_native.py" "$@"
