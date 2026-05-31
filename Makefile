.PHONY: dev test lint verify verify-feeds verify-ai verify-release verify-production seed-sources migrate run worker docker-up docker-down check-comments check-migrations check-frontend

PYTHON = .venv/bin/python
PY_SCRIPTS = migrate.py verify_feeds.py ai_gate_test.py seed_sources.py run_pipeline.py add_sources.py verify_release.py verify_production.py scripts/check_comment_policy.py scripts/check_migration_policy.py scripts/check_frontend_policy.py

venv:
	uv venv .venv
	uv pip install -p .venv/bin/python -e ".[dev]"

dev: venv

run:
	.venv/bin/uvicorn src.main:app --host $${API_HOST:-127.0.0.1} --port $${API_PORT:-8100} --loop asyncio --reload

worker:
	$(PYTHON) -m src.scheduler.jobs

test:
	.venv/bin/pytest -v

lint:
	.venv/bin/ruff check src/ tests/ $(PY_SCRIPTS)
	$(MAKE) check-comments
	$(MAKE) check-migrations
	$(MAKE) check-frontend

check-comments:
	$(PYTHON) scripts/check_comment_policy.py

check-migrations:
	$(PYTHON) scripts/check_migration_policy.py

check-frontend:
	$(PYTHON) scripts/check_frontend_policy.py

verify: lint test
	python3 -m compileall -q src tests $(PY_SCRIPTS)

verify-feeds:
	$(PYTHON) verify_feeds.py --min-ok $${MIN_OK:-3}

verify-ai:
	$(PYTHON) ai_gate_test.py

verify-release:
	$(PYTHON) verify_release.py

verify-production:
	$(PYTHON) verify_production.py

seed-sources:
	$(PYTHON) seed_sources.py

format:
	.venv/bin/ruff check --fix src/ tests/ $(PY_SCRIPTS)
	.venv/bin/ruff format src/ tests/ $(PY_SCRIPTS)

migrate:
	$(PYTHON) migrate.py

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f
