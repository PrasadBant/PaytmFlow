import json
from uuid import uuid4

import pymupdf
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Base
from app.db.session import create_immutability_triggers, get_db
from app.main import app
from app.packs.registry import pack_registry


def create_sample_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture(autouse=True)
def load_manifests(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "mock")
    pack_registry.load_all()


@pytest.fixture
async def client_with_db():
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_immutability_triggers(conn)

    session_maker = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db():
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_upload_evidence_verified_salary_slip_golden_path(
    client_with_db: AsyncClient,
):
    # 1. Obtain session
    session_res = await client_with_db.get("/api/v1/session")
    session_id = session_res.json()["session_id"]
    headers = {"X-Session-Id": session_id}

    # 2. Create Lending Journey
    create_res = await client_with_db.post(
        "/api/v1/journeys",
        headers=headers,
        json={
            "journey_type": "LENDING",
            "goal": {
                "loan_amount": 250000,
                "loan_purpose": "HOME_RENOVATION",
                "tenure_months": 24,
            },
        },
    )
    assert create_res.status_code == 201
    journey_data = create_res.json()
    journey_id = journey_data["journey_id"]
    snapshot_id = journey_data["snapshot_id"]
    version_before = journey_data["version_number"]

    # 3. Upload Salary Slip PDF
    pdf_bytes = create_sample_pdf(
        "ACME TECH SALARY SLIP\n"
        "Employee: Rohit Sharma\n"
        "PAN: ABCDE1234F\n"
        "Monthly Salary: INR 85,000\n"
    )

    files = {
        "file": ("salary_slip.pdf", pdf_bytes, "application/pdf"),
    }
    data = {
        "doc_type": "salary_slip",
        "expected_snapshot_id": snapshot_id,
    }

    upload_res = await client_with_db.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        headers=headers,
        data=data,
        files=files,
    )
    assert upload_res.status_code == 200
    res_json = upload_res.json()

    assert "evidence_id" in res_json
    assert res_json["filename"] == "salary_slip.pdf"
    assert res_json["interpretation"]["verified"] is True
    assert res_json["interpretation"]["confidence"] >= 0.85
    assert len(res_json["interpretation"]["detected"]) > 0
    assert res_json["requires_review"] is False
    assert res_json["proposed_action_id"] == "UPLOAD_INCOME_PROOF"

    # Deterministic consequence & diff preview present
    assert res_json["consequence_preview"] is not None
    assert res_json["diff_preview"] is not None

    # INVARIANT CHECK: Snapshot is UNCHANGED (No snapshot created by evidence upload)
    journey_res = await client_with_db.get(f"/api/v1/journeys/{journey_id}", headers=headers)
    assert journey_res.status_code == 200
    assert journey_res.json()["version_number"] == version_before
    assert journey_res.json()["snapshot_id"] == snapshot_id


@pytest.mark.asyncio
async def test_upload_evidence_manual_fields(client_with_db: AsyncClient):
    session_res = await client_with_db.get("/api/v1/session")
    session_id = session_res.json()["session_id"]
    headers = {"X-Session-Id": session_id}

    create_res = await client_with_db.post(
        "/api/v1/journeys",
        headers=headers,
        json={
            "journey_type": "LENDING",
            "goal": {
                "loan_amount": 100000,
                "loan_purpose": "HOME_RENOVATION",
                "tenure_months": 12,
            },
        },
    )
    journey_data = create_res.json()
    journey_id = journey_data["journey_id"]
    snapshot_id = journey_data["snapshot_id"]

    data = {
        "doc_type": "salary_slip",
        "expected_snapshot_id": snapshot_id,
        "manual_fields": json.dumps({"monthly_income": 85000, "employer_name": "Acme Corp"}),
    }

    upload_res = await client_with_db.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        headers=headers,
        data=data,
    )
    assert upload_res.status_code == 200
    res_json = upload_res.json()
    assert res_json["filename"] == "manual_entry.json"
    assert res_json["interpretation"]["verified"] is True


@pytest.mark.asyncio
async def test_upload_evidence_conflicting_statement_requires_review(
    client_with_db: AsyncClient,
):
    session_res = await client_with_db.get("/api/v1/session")
    session_id = session_res.json()["session_id"]
    headers = {"X-Session-Id": session_id}

    create_res = await client_with_db.post(
        "/api/v1/journeys",
        headers=headers,
        json={
            "journey_type": "LENDING",
            "goal": {
                "loan_amount": 200000,
                "loan_purpose": "HOME_RENOVATION",
                "tenure_months": 24,
            },
        },
    )
    journey_data = create_res.json()
    journey_id = journey_data["journey_id"]
    snapshot_id = journey_data["snapshot_id"]

    # PDF simulating conflict trigger keyword
    pdf_bytes = create_sample_pdf(
        "BANK STATEMENT CONFLICT REPORT\n"
        "Ambiguity detected: Discrepancy in monthly inflow vs declared income.\n"
    )

    files = {
        "file": ("bank_statement.pdf", pdf_bytes, "application/pdf"),
    }
    data = {
        "doc_type": "bank_statement",
        "expected_snapshot_id": snapshot_id,
    }

    upload_res = await client_with_db.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        headers=headers,
        data=data,
        files=files,
    )
    assert upload_res.status_code == 200
    res_json = upload_res.json()
    assert res_json["requires_review"] is True
    assert len(res_json["interpretation"]["conflicts"]) > 0


@pytest.mark.asyncio
async def test_upload_evidence_stale_snapshot_returns_409(
    client_with_db: AsyncClient,
):
    session_res = await client_with_db.get("/api/v1/session")
    session_id = session_res.json()["session_id"]
    headers = {"X-Session-Id": session_id}

    create_res = await client_with_db.post(
        "/api/v1/journeys",
        headers=headers,
        json={
            "journey_type": "LENDING",
            "goal": {
                "loan_amount": 100000,
                "loan_purpose": "HOME_RENOVATION",
                "tenure_months": 12,
            },
        },
    )
    journey_id = create_res.json()["journey_id"]
    current_snapshot_id = create_res.json()["snapshot_id"]

    wrong_snapshot_id = str(uuid4())
    pdf_bytes = create_sample_pdf("Sample PDF content")

    upload_res = await client_with_db.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        headers=headers,
        data={
            "doc_type": "salary_slip",
            "expected_snapshot_id": wrong_snapshot_id,
        },
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_res.status_code == 409
    err = upload_res.json()
    assert err["error"]["code"] == "ACTION_STALE"
    assert err["error"]["details"]["current_snapshot_id"] == current_snapshot_id


@pytest.mark.asyncio
async def test_upload_evidence_cross_session_returns_404(
    client_with_db: AsyncClient,
):
    # Session 1 creates journey
    s1 = str(uuid4())
    create_res = await client_with_db.post(
        "/api/v1/journeys",
        headers={"X-Session-Id": s1},
        json={
            "journey_type": "LENDING",
            "goal": {
                "loan_amount": 100000,
                "loan_purpose": "HOME_RENOVATION",
                "tenure_months": 12,
            },
        },
    )
    assert create_res.status_code == 201
    journey_id = create_res.json()["journey_id"]
    snapshot_id = create_res.json()["snapshot_id"]

    # Session 2 tries to upload evidence
    s2 = str(uuid4())
    pdf_bytes = create_sample_pdf("Sample PDF")
    upload_res = await client_with_db.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        headers={"X-Session-Id": s2},
        data={"doc_type": "salary_slip", "expected_snapshot_id": snapshot_id},
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_res.status_code == 404


@pytest.mark.asyncio
async def test_upload_evidence_missing_snapshot_returns_clean_404(
    client_with_db: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """Regression test: reconcile.py previously referenced the non-existent
    ErrorCode.NOT_FOUND enum member (ErrorCode has no NOT_FOUND value - see
    app/schemas/enums.py and contract/openapi.yaml's ErrorCode schema, both of
    which intentionally omit it; 404s use a plain string code instead, exactly
    like security.session.verify_journey_ownership already does). That made
    every "not found" branch inside submit_evidence raise an unhandled
    AttributeError instead of returning a 404, for any journey whose current
    snapshot cannot be loaded (a real, if rare, data-integrity edge case -
    e.g. a dangling current_snapshot_id). This forces that branch by
    monkeypatching SnapshotRepository.get_by_id to simulate a missing snapshot
    for an otherwise legitimate, correctly-owned request, and asserts a clean
    contract-shaped 404 comes back rather than a 500/crash.
    """
    from app.db.repositories.snapshots import SnapshotRepository

    async def fake_get_by_id(self, snapshot_id):
        return None

    monkeypatch.setattr(SnapshotRepository, "get_by_id", fake_get_by_id)

    s1 = str(uuid4())
    create_res = await client_with_db.post(
        "/api/v1/journeys",
        headers={"X-Session-Id": s1},
        json={
            "journey_type": "LENDING",
            "goal": {
                "loan_amount": 100000,
                "loan_purpose": "HOME_RENOVATION",
                "tenure_months": 12,
            },
        },
    )
    assert create_res.status_code == 201
    journey_id = create_res.json()["journey_id"]
    snapshot_id = create_res.json()["snapshot_id"]

    pdf_bytes = create_sample_pdf("Sample PDF")
    upload_res = await client_with_db.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        headers={"X-Session-Id": s1},
        data={"doc_type": "salary_slip", "expected_snapshot_id": snapshot_id},
        files={"file": ("doc.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_res.status_code == 404
    body = upload_res.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Snapshot not found"
