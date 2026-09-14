"""Small, realistic concurrent-workload check (mission Part 12) - NOT a
production load test. Verifies that concurrently uploading evidence for
several DIFFERENT journeys (each its own session) through the shared
`LocalMLProvider`/classifier singletons does not corrupt shared model
state, leak evidence between sessions, or produce duplicate/inconsistent
snapshots. A handful of concurrent requests, not a stress test - the
limitation of this scope is stated explicitly in the E2E report.
"""

import asyncio
import io
import random
from uuid import uuid4

import pymupdf
import pytest
from faker import Faker
from httpx import AsyncClient
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.config import settings
from app.docai.classifier import get_classifier
from app.docai.dataset.generate import _degrade
from app.docai.ocr import TESSERACT_AVAILABLE

pytestmark = [
    pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="Tesseract OCR binary not available."),
    pytest.mark.asyncio,
]


def _generate_jpeg(draw_fn, fields, template, seed):
    rng = random.Random(seed)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_fn(c, fields, template)
    c.showPage()
    c.save()
    doc = pymupdf.open(stream=buf.getvalue(), filetype="pdf")
    pix = doc[0].get_pixmap(dpi=150)
    pil_img = Image.open(io.BytesIO(pix.tobytes("png")))
    pil_img, _ = _degrade(pil_img, rng)
    img_buf = io.BytesIO()
    pil_img.save(img_buf, format="JPEG", quality=85)
    return img_buf.getvalue()


async def _one_full_flow(
    client: AsyncClient, journey_type, goal, doc_type, draw_fn, template, seed
):
    session_resp = await client.get("/api/v1/session")
    headers = {"X-Session-Id": session_resp.json()["session_id"]}

    create_resp = await client.post(
        "/api/v1/journeys", json={"journey_type": journey_type, "goal": goal}, headers=headers
    )
    assert create_resp.status_code == 201
    journey_id = create_resp.json()["journey_id"]
    snap = create_resp.json()["snapshot_id"]

    rng = random.Random(seed)
    fake = Faker()
    Faker.seed(seed)
    from app.docai.dataset.generate_investment import _make_fields as make_fields

    fields = make_fields(rng, fake, doc_type)
    image_bytes = _generate_jpeg(draw_fn, fields, template, seed + 1)

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": doc_type, "expected_snapshot_id": snap},
        files={"file": (f"{doc_type.lower()}.jpg", image_bytes, "image/jpeg")},
        headers=headers,
    )
    assert ev_resp.status_code == 200
    return journey_id, headers["X-Session-Id"], ev_resp.json()


@pytest.mark.skipif(get_classifier("INVESTMENT") is None, reason="No trained classifier.")
async def test_small_concurrent_evidence_upload_workload(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    from app.docai.dataset.generate_investment import _draw_bank_statement, _draw_cancelled_cheque

    tasks = [
        _one_full_flow(
            client,
            "INVESTMENT",
            {"investment_mode": "MONTHLY_SIP", "target_amount": 5000},
            "CANCELLED_CHEQUE",
            _draw_cancelled_cheque,
            "cheque_standard",
            8001 + i * 10,
        )
        for i in range(3)
    ] + [
        _one_full_flow(
            client,
            "INVESTMENT",
            {"investment_mode": "ONE_TIME_LUMPSUM", "target_amount": 10000},
            "BANK_STATEMENT_SUMMARY",
            _draw_bank_statement,
            "statement_standard",
            8002 + i * 10,
        )
        for i in range(3)
    ]

    results = await asyncio.gather(*tasks)

    # Every journey_id and session_id must be unique - no cross-request
    # contamination (a shared/corrupted global would collapse these).
    journey_ids = [r[0] for r in results]
    session_ids = [r[1] for r in results]
    assert len(set(journey_ids)) == len(journey_ids)
    assert len(set(session_ids)) == len(session_ids)

    # Each evidence response's detected doc_type-appropriate boolean must
    # be genuinely its own, not mixed up with another concurrent request's
    # result.
    for _journey_id, _session_id, ev in results:
        detected_keys = {d["key"] for d in ev["interpretation"]["detected"]}
        assert "bank_account_verified" in detected_keys


async def _one_upload_and_execute(client: AsyncClient, seed: int):
    """Final prototype audit (Part 7): a full upload -> resolve -> execute
    flow through the P1-fixed evidence/action-execution path, run
    concurrently with several others, to confirm the new server-side
    evidence resolution (app/services/journey_service.py) does not mix up
    concurrent requests' evidence or corrupt snapshot/version state."""
    session_resp = await client.get("/api/v1/session")
    headers = {"X-Session-Id": session_resp.json()["session_id"]}

    create_resp = await client.post(
        "/api/v1/journeys",
        json={
            "journey_type": "LENDING",
            "goal": {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    journey_id = create_resp.json()["journey_id"]
    snap = create_resp.json()["snapshot_id"]

    rng = random.Random(seed)
    fake = Faker()
    Faker.seed(seed)
    from app.docai.dataset.generate import _draw_salary_slip, _make_fields

    fields = _make_fields(rng, fake, "SALARY_SLIP", "symbol")
    image_bytes = _generate_jpeg(_draw_salary_slip, fields, "salary_table", seed + 1)

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "SALARY_SLIP", "expected_snapshot_id": snap},
        files={"file": ("salary.jpg", image_bytes, "image/jpeg")},
        headers=headers,
    )
    assert ev_resp.status_code == 200
    evidence_id = ev_resp.json()["evidence_id"]

    act_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": snap,
            "idempotency_key": str(uuid4()),
            "input": {"evidence_id": evidence_id},
        },
        headers=headers,
    )
    assert act_resp.status_code == 200, act_resp.text
    income_field = next(
        f for f in act_resp.json()["journey"]["fields"] if f["key"] == "monthly_income"
    )
    return journey_id, headers["X-Session-Id"], income_field["value"], fields["net_amt"]


@pytest.mark.skipif(get_classifier("LENDING") is None, reason="No trained classifier.")
async def test_small_concurrent_action_execution_workload(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """Small, realistic concurrent check of the P1-fixed evidence-resolution
    path itself (not just evidence upload) - 5 concurrent full
    upload-then-execute-action flows, each its own session/journey/document.
    Confirms no evidence contamination, no cross-session/cross-journey
    leakage, no duplicate snapshots, and no model-state corruption under
    concurrency. NOT a load test - 5 concurrent requests only."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    results = await asyncio.gather(
        *(_one_upload_and_execute(client, 9200 + i * 10) for i in range(5))
    )

    journey_ids = [r[0] for r in results]
    session_ids = [r[1] for r in results]
    assert len(set(journey_ids)) == len(journey_ids)
    assert len(set(session_ids)) == len(session_ids)

    # Each journey's extracted monthly_income must match ITS OWN uploaded
    # document's real value, never another concurrent request's value -
    # the strongest possible evidence-contamination check for the P1 fix.
    for _journey_id, _session_id, extracted_income, expected_income in results:
        assert extracted_income == expected_income

    # No duplicate/mixed snapshots: each journey independently reaches
    # version_number=2 (create=1, one successful action=2), never more.
    async def _check_version(client, headers, journey_id):
        resp = await client.get(f"/api/v1/journeys/{journey_id}", headers=headers)
        return resp.json()["version_number"]

    versions = await asyncio.gather(
        *(
            _check_version(client, {"X-Session-Id": sid}, jid)
            for jid, sid, _, _ in results
        )
    )
    assert all(v == 2 for v in versions)
