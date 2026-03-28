#!/bin/bash
# Setup script for NeoCortex Test Agents
# Run this once after cloning, or after cleaning build/.
#
# Usage: cd test_agents && bash setup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Check .env exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "  Edit test_agents/.env with your API keys and paths before starting Docker."
    echo ""
fi

# 2. Symlink .env into docker/ so docker compose picks up variable substitution
if [ ! -e docker/.env ]; then
    ln -s ../.env docker/.env
    echo "  Symlinked docker/.env -> ../.env"
fi

# 3. Compile agents (creates build/, .git marker, pyproject.toml)
echo "Compiling agents..."
cd "$SCRIPT_DIR/.."
uv run --directory "$SCRIPT_DIR/.." python test_agents/build_agents.py
echo ""

echo "Setup complete!"
echo ""
echo "To start:  cd test_agents/docker && docker compose up -d"
echo "API docs:  http://localhost:8003/docs"
echo "Web UI:    http://localhost:4098"
