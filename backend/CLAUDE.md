# PaytmFlow Backend — Agent Context

## What this is
A deterministic financial-journey recovery engine. AI proposes and explains;
deterministic code decides and writes. Spec: `docs/` (v4.2 canonical, read-only).

## Absolute rules — violating any is a build failure
1. `app/core/**` is PURE. No imports from app.ai, app.db, app.api, app.services,
   app.evidence. No I/O, no randomness, no time.now() except passed in. Enforced by
   .importlinter in CI.
2. AI NEVER writes state. AI output is advisory and schema-validated. It can only return
   an action_id that already exists in the server-computed candidate list.
3. Snapshots are IMMUTABLE and append-only. DB triggers enforce it. Only
   `deterministic_check()` can mint a CheckToken, and SnapshotRepository.create()
   requires one.
4. Readiness is an ENUM: READY | NOT_READY | NEEDS_REVIEW | DEAD_END. Never emit a
   numeric score, probability, percentage, or anything named *_score.
5. NEVER write journey-specific logic in engine code. No `if journey_type == "LENDING"`.
   All journey behaviour lives in `packs/manifests/*.yaml`.
6. Every mutation requires `expected_snapshot_id`. Mismatch → ACTION_STALE, no write.
7. Evidence is UNTRUSTED. Never execute it. Wrap extracted text in <untrusted_document>
   tags, cap at 8000 chars, and never let it influence readiness.
8. The planner is a TOPOLOGICAL SORT, not a search. See docs build plan §5.4 for why.
   Do not reintroduce BFS.
9. Never emit these words in any user-facing string: approved, approval, probability,
   credit score, eligibility score, readiness score, guaranteed.

## Stack
Python 3.12+, FastAPI, Pydantic v2 strict, SQLAlchemy 2 async, Alembic, PostgreSQL 16,
uv, PyMuPDF, pytest + HTTPX, ruff, mypy strict on app/core, structlog.

## Conventions
- Pydantic v2 only (model_validate / model_dump). No v1 syntax.
- Core domain objects are frozen dataclasses; no mutation in place.
- Every endpoint returns the ErrorEnvelope shape on failure; error.message is written
  for end users, never a stack trace or an internal identifier.
- Every log line carries request_id. Never log AI keys, cookie values, or file contents.
- Every response field that the UI renders must be server-formatted: label, display_value,
  explanation, ordering, resume_screen.
- Tests live beside their layer: tests/unit (pure), tests/integration (DB+HTTP),
  tests/packs, tests/safety, tests/scenarios.

## Definition of done for any module
Typed · unit-tested · no import-linter violation · no journey-specific branching ·
error paths return the right code · OpenAPI regenerated and matching the committed file.

## Commands
make up · make api · make test · make scenarios · make types · make refresh-fixtures · make reset
