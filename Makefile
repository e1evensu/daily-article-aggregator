.PHONY: dev test lint migrate run worker docker-up docker-down

PYTHON = .venv/bin/python

venv:
	uv venv .venv
	uv pip install -p .venv/bin/python -e ".[dev]"

dev: venv

run:
	.venv/bin/uvicorn src.main:app --host $${API_HOST:-127.0.0.1} --port $${API_PORT:-8100} --reload

worker:
	$(PYTHON) -m src.scheduler.jobs

test:
	.venv/bin/pytest -v

lint:
	.venv/bin/ruff check src/ tests/

format:
	.venv/bin/ruff check --fix src/ tests/
	.venv/bin/ruff format src/ tests/

migrate:
	$(PYTHON) -c "import asyncio; from src.models.base import Base; from src.models import *; from src.db import engine; asyncio.run(Base.metadata.create_all(engine))" 2>/dev/null || \
	ssh root@114 'docker exec -i intelligence-mysql mysql -u intelligence -pintl_svc_2026 intelligence' < migrations/001_init.sql

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f
