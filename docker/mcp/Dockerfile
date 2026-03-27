FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN pip install --no-cache-dir uv \
    && uv sync --frozen

COPY src/ src/

EXPOSE 8000

CMD ["uv", "run", "python", "-m", "neocortex"]
