"""Genuine concurrency tests: simultaneous requests, each on its own pooled
PostgreSQL connection, against the real row-lock / snapshot-chain logic."""

import asyncio
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.models import IdempotencyKeyModel, JourneyModel, JourneySnapshotModel, ReviewCaseModel

N = 6
GOAL = {
    "journey_type": "LENDING",
    "goal": {"loan_amount": 250000, "loan_purpose": "EDUCATION", "tenure_months": 36},
}


@pytest.fixture(autouse=True)
def _postgres_only(db_engine: AsyncEngine) -> None:
    if db_engine.dialect.name != "postgresql":
        pytest.skip("Concurrency semantics require PostgreSQL row locks")


async def _count(engine: AsyncEngine, stmt) -> int:
    factory = async_sessionmaker(engine, class_=AsyncSession)
    async with factory() as s:
        return int(await s.scalar(stmt) or 0)


async def _journey_row(engine: AsyncEngine, jid: str) -> JourneyModel:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        row = await s.get(JourneyModel, UUID(jid))
        assert row is not None
        return row


async def _snapshots(engine: AsyncEngine, jid: str) -> int:
    return await _count(
        engine,
        select(func.count())
        .select_from(JourneySnapshotModel)
        .where(JourneySnapshotModel.journey_id == UUID(jid)),
    )


async def _create(client: AsyncClient, headers: dict) -> dict:
    r = await client.post("/api/v1/journeys", json=GOAL, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _action(jid, snap, action_id, key=None, **inp):
    return {
        "action_id": action_id,
        "expected_snapshot_id": snap,
        "idempotency_key": key or str(uuid4()),
        "input": inp,
    }


async def test_conflicting_concurrent_updates_one_wins_rest_stale(
    client: AsyncClient, session_headers: dict, db_engine: AsyncEngine
) -> None:
    j = await _create(client, session_headers)
    jid, snap = j["journey_id"], j["snapshot_id"]
    bodies = [_action(jid, snap, "UPLOAD_INCOME_PROOF", monthly_income=50000 + i) for i in range(N)]
    results = await asyncio.gather(
        *[
            client.post(f"/api/v1/journeys/{jid}/actions", json=b, headers=session_headers)
            for b in bodies
        ]
    )
    codes = sorted(r.status_code for r in results)
    assert codes.count(200) == 1, codes
    assert all(c == 409 for c in codes if c != 200), codes
    assert await _snapshots(db_engine, jid) == 2
    row = await _journey_row(db_engine, jid)
    winner = next(r for r in results if r.status_code == 200).json()
    assert str(row.current_snapshot_id) == winner["journey"]["snapshot_id"]


async def test_duplicate_concurrent_submissions_apply_once(
    client: AsyncClient, session_headers: dict, db_engine: AsyncEngine
) -> None:
    j = await _create(client, session_headers)
    jid, snap = j["journey_id"], j["snapshot_id"]
    body = _action(jid, snap, "UPLOAD_INCOME_PROOF", key=str(uuid4()), monthly_income=60000)
    results = await asyncio.gather(
        *[
            client.post(f"/api/v1/journeys/{jid}/actions", json=body, headers=session_headers)
            for _ in range(N)
        ]
    )
    codes = [r.status_code for r in results]
    assert 500 not in codes, codes
    assert codes.count(200) >= 1, codes
    assert all(c in (200, 409) for c in codes), codes
    ok = [r.json() for r in results if r.status_code == 200]
    assert len({o["journey"]["snapshot_id"] for o in ok}) == 1
    assert await _snapshots(db_engine, jid) == 2
    assert (
        await _count(
            db_engine,
            select(func.count())
            .select_from(IdempotencyKeyModel)
            .where(IdempotencyKeyModel.key == body["idempotency_key"]),
        )
        == 1
    )


async def test_concurrent_clarifications_resolve_once(
    client: AsyncClient, session_headers: dict, db_engine: AsyncEngine
) -> None:
    j = await _create(client, session_headers)
    jid = j["journey_id"]
    opened = await client.post(
        f"/api/v1/journeys/{jid}/actions",
        json=_action(
            jid,
            j["snapshot_id"],
            "UPLOAD_INCOME_PROOF",
            monthly_income=60000,
            ambiguity_id="INCOME_MISMATCH",
        ),
        headers=session_headers,
    )
    assert opened.status_code == 200, opened.text
    snap = opened.json()["journey"]["snapshot_id"]
    before = await _snapshots(db_engine, jid)
    results = await asyncio.gather(
        *[
            client.post(
                f"/api/v1/journeys/{jid}/clarifications",
                json={
                    "ambiguity_id": "INCOME_MISMATCH",
                    "field": "monthly_income",
                    "answer": 70000 + i,
                    "expected_snapshot_id": snap,
                },
                headers=session_headers,
            )
            for i in range(N)
        ]
    )
    codes = sorted(r.status_code for r in results)
    assert codes.count(200) == 1, codes
    assert all(c in (409, 422) for c in codes if c != 200), codes
    assert await _snapshots(db_engine, jid) == before + 1


async def test_concurrent_review_claims_single_owner(
    client: AsyncClient, db_engine: AsyncEngine
) -> None:
    customer = {"X-Session-Id": str(uuid4())}
    j = await _create(client, customer)
    r = await client.post(
        f"/api/v1/journeys/{j['journey_id']}/actions",
        json=_action(
            j["journey_id"],
            j["snapshot_id"],
            "UPLOAD_INCOME_PROOF",
            monthly_income=60000,
            ambiguity_id="INCOME_MISMATCH",
        ),
        headers=customer,
    )
    assert r.status_code == 200, r.text
    reviewers = [{"X-Session-Id": str(uuid4())} for _ in range(N)]
    for h in reviewers:
        assert (
            await client.post("/api/v1/review/role", json={"role": "REVIEW_OFFICER"}, headers=h)
        ).status_code == 200
    cases = (await client.get("/api/v1/review/cases", headers=reviewers[0])).json()["cases"]
    case = next(c for c in cases if c["journey_id"] == j["journey_id"])
    detail = (
        await client.get(f"/api/v1/review/cases/{case['case_id']}", headers=reviewers[0])
    ).json()
    version = detail.get("case_version", detail.get("version", 1))
    results = await asyncio.gather(
        *[
            client.post(
                f"/api/v1/review/cases/{case['case_id']}/claim",
                json={"expected_case_version": version},
                headers=h,
            )
            for h in reviewers
        ]
    )
    codes = sorted(r.status_code for r in results)
    assert 500 not in codes, codes
    assert codes.count(200) == 1, codes
    factory = async_sessionmaker(db_engine, class_=AsyncSession)
    async with factory() as s:
        row = await s.get(ReviewCaseModel, UUID(case["case_id"]))
        assert row is not None and row.assigned_reviewer is not None


async def test_failure_mid_mutation_rolls_back_everything(
    client: AsyncClient,
    session_headers: dict,
    db_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.audit.writer import AuditWriter

    j = await _create(client, session_headers)
    jid, snap = j["journey_id"], j["snapshot_id"]

    async def boom(*_a, **_k):
        raise RuntimeError("injected failure after snapshot write")

    monkeypatch.setattr(AuditWriter, "record_action_executed", boom)
    body = _action(jid, snap, "UPLOAD_INCOME_PROOF", monthly_income=60000)
    with pytest.raises(RuntimeError):
        await client.post(f"/api/v1/journeys/{jid}/actions", json=body, headers=session_headers)

    assert await _snapshots(db_engine, jid) == 1
    row = await _journey_row(db_engine, jid)
    assert str(row.current_snapshot_id) == snap
    assert (
        await _count(
            db_engine,
            select(func.count())
            .select_from(IdempotencyKeyModel)
            .where(IdempotencyKeyModel.key == body["idempotency_key"]),
        )
        == 0
    )

    monkeypatch.undo()
    retry = await client.post(f"/api/v1/journeys/{jid}/actions", json=body, headers=session_headers)
    assert retry.status_code == 200, retry.text
    assert await _snapshots(db_engine, jid) == 2


async def test_same_key_different_payload_concurrently_never_replays_or_500s(
    client: AsyncClient, session_headers: dict, db_engine: AsyncEngine
) -> None:
    j = await _create(client, session_headers)
    jid, snap = j["journey_id"], j["snapshot_id"]
    key = str(uuid4())
    bodies = [
        _action(jid, snap, "UPLOAD_INCOME_PROOF", key=key, monthly_income=50000 + i)
        for i in range(N)
    ]
    results = await asyncio.gather(
        *[
            client.post(f"/api/v1/journeys/{jid}/actions", json=b, headers=session_headers)
            for b in bodies
        ]
    )
    codes = [r.status_code for r in results]
    assert codes.count(200) == 1, codes
    # Losers must be told their request conflicts, never handed the winner's response.
    assert all(c == 400 for c in codes if c != 200), codes
    assert await _snapshots(db_engine, jid) == 2


async def test_same_key_on_two_journeys_concurrently_no_500_no_leak(
    client: AsyncClient, db_engine: AsyncEngine
) -> None:
    key = str(uuid4())
    owners = [{"X-Session-Id": str(uuid4())} for _ in range(N)]
    journeys = [await _create(client, h) for h in owners]
    results = await asyncio.gather(
        *[
            client.post(
                f"/api/v1/journeys/{j['journey_id']}/actions",
                json=_action(
                    j["journey_id"],
                    j["snapshot_id"],
                    "UPLOAD_INCOME_PROOF",
                    key=key,
                    monthly_income=60000,
                ),
                headers=h,
            )
            for j, h in zip(journeys, owners, strict=True)
        ]
    )
    codes = [r.status_code for r in results]
    assert codes.count(200) == 1, codes
    assert all(c == 400 for c in codes if c != 200), codes
    winner = next(r for r in results if r.status_code == 200).json()["journey"]["journey_id"]
    for r, j in zip(results, journeys, strict=True):
        if r.status_code == 400:
            assert winner not in r.text
            assert await _snapshots(db_engine, j["journey_id"]) == 1
    assert await _snapshots(db_engine, winner) == 2
