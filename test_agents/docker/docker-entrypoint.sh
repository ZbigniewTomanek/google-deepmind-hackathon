#!/bin/sh
set -e

if [ "$(id -u)" = "0" ]; then
    # Fix ownership on docker-managed volumes
    chown -R "${HOST_UID:-1000}:${HOST_GID:-1000}" /workspace/.docker-venv 2>/dev/null || true
    mkdir -p /workspace/test_agents/.opencode/data
    chown -R "${HOST_UID:-1000}:${HOST_GID:-1000}" /workspace/test_agents/.opencode/data 2>/dev/null || true

    exec gosu "${HOST_UID:-1000}:${HOST_GID:-1000}" "$@"
fi

exec "$@"
