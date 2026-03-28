FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (required for npx mcp-remote MCP server proxy)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

ARG UID=1000
ARG GID=1000

RUN groupadd -g $GID appuser 2>/dev/null || true \
    && useradd -m -u $UID -g $GID appuser 2>/dev/null || true

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

USER $UID:$GID
WORKDIR /workspace
