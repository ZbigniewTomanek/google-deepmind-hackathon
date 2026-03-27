#!/bin/sh
set -e

if [ "$(id -u)" = "0" ]; then
    PROJECT_ROOT="/home/dw/programing/google-deepmind-hackathon"
    VENV_DIR="${PROJECT_ROOT}/.venv"
    OPENCODE_DATA="${PROJECT_ROOT}/test_agents/.opencode/data"

    chown -R 1000:1000 "$VENV_DIR" 2>/dev/null || true
    mkdir -p "$OPENCODE_DATA" && chown -R 1000:1000 "$OPENCODE_DATA" 2>/dev/null || true

    exec gosu appuser "$@"
fi

exec "$@"
