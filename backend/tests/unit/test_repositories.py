from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deterministic_check import deterministic_check
from app.core.models import CheckToken, CoreFieldStatus, CoreReadiness, CoreSnapshot
from app.db.models import Base
from app.db.repositories import (
    AuditRepository,
    ClarificationRepository,
    EvidenceRepository,
    IdempotencyRepository,
    JourneyRepository,
    PackRepository,
    SessionRepository,
    SnapshotRepository,
)
from app.db.session import create_immutability_triggers
from app.packs.registry import pack_registry
from app.schemas.enums import JourneyType


@pytest.fixture
async def db_session() -> AsyncSession:
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_immutability_triggers(conn)

    session_maker = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session

    await test_engine.dispose()


async def test_snapshot_repository_requires_check_token(db_session: AsyncSession):
    session_repo = SessionRepository(db_session)
    journey_repo = JourneyRepository(db_session)
    snapshot_repo = SnapshotRepository(db_session)

    now = datetime.now(UTC)
    sess = await session_repo.create(expires_at=now + timedelta(days=30))
    journey = await journey_repo.create(
        session_id=sess.id,
        journey_type="LENDING",
    )

    # Create initial v1 snapshot
    snap_v1 = await snapshot_repo.create_initial(
        journey_id=journey.id,
        readiness="NOT_READY",
        fields={"kyc_verified": {"status": "SATISFIED"}},
    )
    assert snap_v1.version_number == 1
    assert snap_v1.previous_snapshot_id is None

    # 1. Attempt to create v2 without a CheckToken (e.g. dict or object) -> TypeError
    with pytest.raises(TypeError) as exc_info:
        await snapshot_repo.create(
            token={"action_id": "UPLOAD_INCOME_PROOF"},  # type: ignore
            readiness="NOT_READY",
            fields={},
        )
    assert "CheckToken" in str(exc_info.value)

    # 2. Mint a real CheckToken via deterministic_check()
    pack_registry.load_all()
    pack = pack_registry.get_pack(JourneyType.LENDING)
    assert pack is not None

    core_snap = CoreSnapshot(
        snapshot_id=snap_v1.id,
        journey_id=journey.id,
        journey_type="LENDING",
        version_number=1,
        readiness=CoreReadiness.NOT_READY,
        fields={
            "kyc_verified": type("Obj", (), {"status": CoreFieldStatus.SATISFIED, "value": True})(),
        },
        goal={},
    )

    token = deterministic_check(
        snapshot=core_snap,
        expected_snapshot_id=snap_v1.id,
        action_id="UPLOAD_INCOME_PROOF",
        action_input={"monthly_income": 85000},
        manifest=pack,
        now=now,
    )
    assert isinstance(token, CheckToken)

    # 3. Create v2 passing the valid CheckToken -> Success
    snap_v2 = await snapshot_repo.create(
        token=token,
        readiness="NOT_READY",
        fields={"monthly_income": {"status": "SATISFIED", "value": 85000}},
    )
    assert snap_v2.version_number == 2
    assert snap_v2.previous_snapshot_id == snap_v1.id

    # 4. Attempt to create snapshot with mismatched previous_snapshot_id -> RuntimeError
    stale_token = CheckToken(
        token_id=uuid4(),
        journey_id=journey.id,
        journey_type="LENDING",
        action_id="SUBMIT_EMPLOYMENT_INFO",
        previous_snapshot_id=snap_v1.id,  # Stale! latest is snap_v2.id
        action_input={},
        new_values={},
        direct_fields=[],
        created_at=now,
    )
    with pytest.raises(RuntimeError) as exc_info:
        await snapshot_repo.create(
            token=stale_token,
            readiness="NOT_READY",
            fields={},
        )
    assert "does not match latest" in str(exc_info.value)


async def test_all_repositories(db_session: AsyncSession):
    session_repo = SessionRepository(db_session)
    journey_repo = JourneyRepository(db_session)
    evidence_repo = EvidenceRepository(db_session)
    audit_repo = AuditRepository(db_session)
    idemp_repo = IdempotencyRepository(db_session)
    clarification_repo = ClarificationRepository(db_session)
    pack_repo = PackRepository(db_session)

    now = datetime.now(UTC)
    sess = await session_repo.create(expires_at=now + timedelta(days=30))
    assert sess.id is not None

    # JourneyRepo
    journey = await journey_repo.create(
        session_id=sess.id,
        journey_type="LENDING",
        display_title="Personal Loan",
    )
    fetched_journey = await journey_repo.get_by_id_for_update(journey.id)
    assert fetched_journey is not None
    assert fetched_journey.id == journey.id

    journey_list = await journey_repo.list_by_session(sess.id)
    assert len(journey_list) == 1

    # EvidenceRepo
    evidence = await evidence_repo.create(
        journey_id=journey.id,
        doc_type="SALARY_SLIP",
        filename="salary.pdf",
        file_path="/uploads/salary.pdf",
        sha256="test-sha256-hash-01",
        file_size_bytes=2048,
        mime_type="application/pdf",
        extracted_text="Salary 85000",
        confidence=0.95,
    )
    by_sha = await evidence_repo.get_by_sha256("test-sha256-hash-01")
    assert by_sha is not None
    assert by_sha.id == evidence.id

    # AuditRepo
    audit = await audit_repo.create(
        journey_id=journey.id,
        session_id=sess.id,
        event_type="ACTION_EXECUTED",
        payload={"action_id": "UPLOAD_INCOME_PROOF"},
    )
    audits = await audit_repo.list_by_journey_id(journey.id)
    assert len(audits) == 1
    assert audits[0].id == audit.id

    # IdempotencyRepo
    idemp = await idemp_repo.create(
        key="idemp-key-unique-001",
        session_id=sess.id,
        journey_id=journey.id,
        action_id="UPLOAD_INCOME_PROOF",
        request_hash="hash_val",
        response_body={"ok": True},
        status_code=200,
    )
    assert idemp.key == "idemp-key-unique-001"
    fetched_idemp = await idemp_repo.get("idemp-key-unique-001")

    assert fetched_idemp is not None
    assert fetched_idemp.response_body == {"ok": True}

    # ClarificationRepo
    clar = await clarification_repo.create(
        journey_id=journey.id,
        ambiguity_id="INCOME_MISMATCH",
        field_key="monthly_income",
        question="Select income",
        answer_type="MONEY",
    )
    pending = await clarification_repo.get_pending_by_journey_id(journey.id)
    assert pending is not None
    assert pending.id == clar.id

    resolved = await clarification_repo.resolve(clar.id, user_response={"selected_income": 85000})
    assert resolved is not None
    assert resolved.resolved_at is not None

    # PackRepo
    pack_meta = await pack_repo.upsert(
        journey_type="LENDING",
        schema_version="1.0.0",
        display_name="Personal Loan",
        description="Instant personal loan",
        icon="rupee",
        flagship_demo=True,
    )
    assert pack_meta.journey_type == "LENDING"
    all_packs = await pack_repo.list_all()
    assert len(all_packs) == 1
