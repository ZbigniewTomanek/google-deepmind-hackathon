FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-install-project

COPY src/ src/
COPY migrations/ migrations/

RUN uv sync --frozen

EXPOSE 8000

CMD ["uv", "run", "python", "-m", "neocortex"]
