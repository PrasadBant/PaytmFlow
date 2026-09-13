.PHONY: up down api test test-unit test-contract test-integration test-integration-pg test-safety test-invariants scenarios lint type-check reset clean

up:
	docker compose up -d postgres

down:
	docker compose down

# --loop none: uvicorn's default ("auto") builds its own event loop via
# asyncio.run(loop_factory=...), which bypasses whatever event loop policy the
# app sets - on native Windows that silently breaks psycopg3's async driver
# (app/db/session.py sets WindowsSelectorEventLoopPolicy for exactly this
# reason: without it, GET /health reports db:false and every other endpoint
# 500s). "none" makes uvicorn fall back to asyncio.run()'s own loop creation,
# which does respect the policy. No effect on Docker/Linux, where this policy
# branch never runs.
#
# No --reload here: uvicorn's --reload runs the server in a spawned child
# process, and on native Windows that child does not end up honouring
# --loop none the same way the parent does (confirmed by direct testing -
# the exact same ProactorEventLoop/psycopg3 failure returns). Prefer
# correctness (a backend that can reach its database) over auto-restart;
# restart `make api` manually after code changes, or run
# `uv run uvicorn app.main:app --reload --port 8000` yourself and accept the
# Windows caveat if hot-reload is worth more to you locally. Unaffected on
# Docker/Linux either way.
api:
	uv run uvicorn app.main:app --port 8000 --loop none

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
