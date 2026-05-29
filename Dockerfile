FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml ./
RUN uv pip install --system --no-cache .

COPY src/ src/
COPY migrations/ migrations/

EXPOSE 8100

CMD ["sh", "-c", "${API_COMMAND:-uvicorn src.main:app} --host ${API_HOST:-127.0.0.1} --port ${API_PORT:-8100}"]
