.PHONY: up down api test test-unit test-contract test-integration test-integration-pg test-safety test-invariants scenarios lint type-check reset clean

up:
	docker compose up -d postgres

down:
	docker compose down

api:
	uv run uvicorn app.main:app --reload --port 8000

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit

test-contract:
	uv run pytest tests/contract

test-integration:
	uv run pytest tests/integration

# The real acceptance target: FAILS if PostgreSQL is not reachable, instead of
# silently falling back to SQLite (which masks FK/trigger/lock behaviour that
# only PostgreSQL enforces - see B17/B30 in the backend audit).
# Requires: docker compose up -d postgres (or DATABASE_URL pointed at a real one).
test-integration-pg:
	REQUIRE_POSTGRES=1 uv run pytest tests/integration -v

test-safety:
	uv run pytest tests/safety -v

test-invariants:
	uv run pytest tests/unit/test_invariants.py -v

scenarios:
	uv run python -m app.eval.runner

reset:
	uv run python -m app.db.seed

lint:
	uv run ruff check app tests

type-check:
	uv run mypy app

clean:
	rm -rf .pytest_cache .mypy_cache __pycache__ storage/evidence/*
