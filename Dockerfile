FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml README.md ./
COPY config/ config/
COPY migrate.py run_pipeline.py seed_sources.py ./
COPY src/ src/
COPY migrations/ migrations/

RUN uv pip install --system --no-cache .

EXPOSE 8100

CMD ["sh", "-c", "${API_COMMAND:-uvicorn src.main:app} --host ${API_HOST:-127.0.0.1} --port ${API_PORT:-8100} --loop asyncio"]
