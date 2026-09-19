"""Integration tests for the reviewer "AI Evidence Summary" endpoint
(spec: reviewer AI summary, advisory only)."""

from uuid import uuid4

from httpx import AsyncClient

from app.config import settings


async def _create_lending_journey(client: AsyncClient, headers: dict[str, str]) -> dict:
    resp = await client.post(
        "/api/v1/journeys",
        json={
            "journey_type": "LENDING",
            "goal": {"loan_amount": 200000, "loan_purpose": "EDUCATION", "tenure_months": 24},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _trigger_income_mismatch(
    client: AsyncClient, headers: dict[str, str], journey_id: str, snapshot_id: str
) -> dict:
    resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": snapshot_id,
            "idempotency_key": str(uuid4()),
            "input": {"monthly_income": 50000, "ambiguity_id": "INCOME_MISMATCH"},
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _become_reviewer(client: AsyncClient, headers: dict[str, str]) -> None:
    resp = await client.post(
        "/api/v1/review/role", json={"role": "REVIEW_OFFICER"}, headers=headers
    )
    assert resp.status_code == 200, resp.text


class TestAiEvidenceSummary:
    async def test_summary_is_advisory_and_grounded(
        self, client: AsyncClient, session_headers: dict
    ) -> None:
        journey = await _create_lending_journey(client, session_headers)
        mismatch_resp = await _trigger_income_mismatch(
            client, session_headers, journey["journey_id"], journey["snapshot_id"]
        )
        await _become_reviewer(client, session_headers)
        queue_resp = await client.get("/api/v1/review/cases", headers=session_headers)
        case = next(
            c for c in queue_resp.json()["cases"] if c["journey_id"] == journey["journey_id"]
        )

        resp = await client.post(
            f"/api/v1/review/cases/{case['case_id']}/ai-summary", headers=session_headers
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["summary"]
        assert "review system evidence" in body["disclaimer"].lower()
        for banned in ("approved", "approval", "guaranteed"):
            assert banned not in body["summary"].lower()
            assert banned not in body["disclaimer"].lower()

        del mismatch_resp  # only needed to advance journey state

    async def test_summary_requires_reviewer_role(
        self, client: AsyncClient, session_headers: dict
    ) -> None:
        journey = await _create_lending_journey(client, session_headers)
        await _trigger_income_mismatch(
            client, session_headers, journey["journey_id"], journey["snapshot_id"]
        )
        await _become_reviewer(client, session_headers)
        queue_resp = await client.get("/api/v1/review/cases", headers=session_headers)
        case = next(
            c for c in queue_resp.json()["cases"] if c["journey_id"] == journey["journey_id"]
        )

        # Switch back to a plain customer session - must be forbidden.
        resp = await client.post(
            "/api/v1/review/role", json={"role": "CUSTOMER"}, headers=session_headers
        )
        assert resp.status_code == 200

        forbidden_resp = await client.post(
            f"/api/v1/review/cases/{case['case_id']}/ai-summary", headers=session_headers
        )
        assert forbidden_resp.status_code == 403

    async def test_summary_disabled_returns_404(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        journey = await _create_lending_journey(client, session_headers)
        await _trigger_income_mismatch(
            client, session_headers, journey["journey_id"], journey["snapshot_id"]
        )
        await _become_reviewer(client, session_headers)
        queue_resp = await client.get("/api/v1/review/cases", headers=session_headers)
        case = next(
            c for c in queue_resp.json()["cases"] if c["journey_id"] == journey["journey_id"]
        )

        monkeypatch.setattr(settings, "SARVAM_CHAT_ENABLED", False)
        resp = await client.post(
            f"/api/v1/review/cases/{case['case_id']}/ai-summary", headers=session_headers
        )
        assert resp.status_code == 404
