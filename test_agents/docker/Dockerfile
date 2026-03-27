FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git openssh-client build-essential gosu \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ARG UID=1000
ARG GID=1000
RUN groupadd -g $GID appuser 2>/dev/null || true \
    && useradd -m -u $UID -g $GID appuser 2>/dev/null || true

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_DEV=1

WORKDIR /app

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
