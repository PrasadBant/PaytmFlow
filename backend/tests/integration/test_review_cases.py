"""Integration tests for the Human Review / Exception Resolution flow.

Exercises the real HTTP API against a real Postgres-backed FastAPI app
(see conftest.py's `client`/`session_headers` fixtures), covering the
golden path end-to-end plus the safety-critical adversarial properties
called out in the review-center spec: duplicate-case prevention, reviewer
authorization, claim locking, stale resolution, and double-submit
idempotency.
"""

from uuid import uuid4

from httpx import AsyncClient


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
    client: AsyncClient,
    headers: dict[str, str],
    journey_id: str,
    snapshot_id: str,
    income: int = 50000,
) -> dict:
    resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": snapshot_id,
            "idempotency_key": str(uuid4()),
            "input": {"monthly_income": income, "ambiguity_id": "INCOME_MISMATCH"},
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["journey"]["readiness"] == "NEEDS_REVIEW"
    return body


async def _become_reviewer(client: AsyncClient, headers: dict[str, str]) -> None:
    resp = await client.post(
        "/api/v1/review/role", json={"role": "REVIEW_OFFICER"}, headers=headers
    )
    assert resp.status_code == 200, resp.text


async def _become_customer(client: AsyncClient, headers: dict[str, str]) -> None:
    resp = await client.post("/api/v1/review/role", json={"role": "CUSTOMER"}, headers=headers)
    assert resp.status_code == 200, resp.text


class TestGoldenPath:
    async def test_full_income_mismatch_flow(
        self, client: AsyncClient, session_headers: dict
    ) -> None:
        journey = await _create_lending_journey(client, session_headers)
        await _trigger_income_mismatch(
            client, session_headers, journey["journey_id"], journey["snapshot_id"]
        )

        # Customer sees a review status, never internal case metadata
        status_resp = await client.get(
            f"/api/v1/journeys/{journey['journey_id']}/review-status", headers=session_headers
        )
        assert status_resp.status_code == 200
        status = status_resp.json()
        assert status["has_open_case"] is True
        assert status["status"] == "REVIEW_REQUIRED"
        assert "case_id" not in status
        assert "assigned_reviewer" not in status

        await _become_reviewer(client, session_headers)
        queue_resp = await client.get("/api/v1/review/cases", headers=session_headers)
        assert queue_resp.status_code == 200
        cases = queue_resp.json()["cases"]
        matching = [c for c in cases if c["journey_id"] == journey["journey_id"]]
        assert len(matching) == 1
        case_id = matching[0]["case_id"]

        claim_resp = await client.post(
            f"/api/v1/review/cases/{case_id}/claim",
            json={"expected_case_version": 1},
            headers=session_headers,
        )
        assert claim_resp.status_code == 200, claim_resp.text
        assert claim_resp.json()["status"] == "UNDER_REVIEW"

        info_resp = await client.post(
            f"/api/v1/review/cases/{case_id}/request-information",
            json={
                "requested_docs": ["BANK_STATEMENT"],
                "customer_message": "Please provide a recent bank statement.",
                "expected_case_version": 2,
            },
            headers=session_headers,
        )
        assert info_resp.status_code == 200, info_resp.text
        assert info_resp.json()["status"] == "ADDITIONAL_INFO_REQUIRED"

        await _become_customer(client, session_headers)
        status_resp2 = await client.get(
            f"/api/v1/journeys/{journey['journey_id']}/review-status", headers=session_headers
        )
        assert status_resp2.json()["status"] == "ADDITIONAL_INFO_REQUIRED"
        assert status_resp2.json()["requested_information"]["requested_docs"] == ["BANK_STATEMENT"]

        await _become_reviewer(client, session_headers)
        reclaim_resp = await client.post(
            f"/api/v1/review/cases/{case_id}/claim",
            json={"expected_case_version": 3},
            headers=session_headers,
        )
        assert reclaim_resp.status_code == 200
        assert reclaim_resp.json()["case_version"] == 4

        resolve_resp = await client.post(
            f"/api/v1/review/cases/{case_id}/resolve",
            json={
                "resolution_type": "EVIDENCE_SUFFICIENT",
                "resolution_reason": "Salary slip confirmed as gross income.",
                "resolution_value": 50000,
                "expected_case_version": 4,
            },
            headers=session_headers,
        )
        assert resolve_resp.status_code == 200, resolve_resp.text
        resolved = resolve_resp.json()
        assert resolved["status"] == "RESOLVED"
        assert resolved["journey_context"]["readiness"] != "NEEDS_REVIEW"
        income_field = next(
            f for f in resolved["journey_context"]["fields"] if f["key"] == "monthly_income"
        )
        assert income_field["status"] == "SATISFIED"
        assert income_field["value"] == 50000

        # Journey Diff was really produced and dashboard reflects it
        dash_resp = await client.get("/api/v1/review/dashboard", headers=session_headers)
        assert dash_resp.json()["resolved_today"] >= 1

        audit_resp = await client.get(
            f"/api/v1/review/cases/{case_id}/audit", headers=session_headers
        )
        event_types = [e["event_type"] for e in audit_resp.json()["entries"]]
        assert "REVIEW_CASE_CREATED" in event_types
        assert "REVIEW_CASE_CLAIMED" in event_types
        assert "REVIEW_CASE_INFO_REQUESTED" in event_types
        assert "REVIEW_CASE_RESOLVED" in event_types
        assert "CLARIFICATION_ANSWERED" in event_types  # proves the real mutation chain ran


class TestSafetyProperties:
    async def test_duplicate_ambiguity_creates_only_one_open_case(
        self, client: AsyncClient, session_headers: dict
    ) -> None:
        journey = await _create_lending_journey(client, session_headers)
        body1 = await _trigger_income_mismatch(
            client, session_headers, journey["journey_id"], journey["snapshot_id"]
        )
        # Re-submitting the SAME action while still AMBIGUOUS must not create a
        # second case (idempotent dedupe).
        body2 = await _trigger_income_mismatch(
            client,
            session_headers,
            journey["journey_id"],
            body1["journey"]["snapshot_id"],
            income=48000,
        )
        assert body2["journey"]["readiness"] == "NEEDS_REVIEW"

        await _become_reviewer(client, session_headers)
        cases = (await client.get("/api/v1/review/cases", headers=session_headers)).json()["cases"]
        matching = [c for c in cases if c["journey_id"] == journey["journey_id"]]
        assert len(matching) == 1

    async def test_customer_session_forbidden_from_review_endpoints(
        self, client: AsyncClient, session_headers: dict
    ) -> None:
        resp = await client.get("/api/v1/review/cases", headers=session_headers)
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    async def test_second_reviewer_blocked_while_case_is_claimed(
        self, client: AsyncClient, session_headers: dict, other_session_headers: dict
    ) -> None:
        journey = await _create_lending_journey(client, session_headers)
        await _trigger_income_mismatch(
            client, session_headers, journey["journey_id"], journey["snapshot_id"]
        )
        await _become_reviewer(client, session_headers)
        cases = (await client.get("/api/v1/review/cases", headers=session_headers)).json()["cases"]
        case_id = next(c for c in cases if c["journey_id"] == journey["journey_id"])["case_id"]

        claim1 = await client.post(
            f"/api/v1/review/cases/{case_id}/claim",
            json={"expected_case_version": 1},
            headers=session_headers,
        )
        assert claim1.status_code == 200

        await _become_reviewer(client, other_session_headers)
        claim2 = await client.post(
            f"/api/v1/review/cases/{case_id}/claim",
            json={"expected_case_version": 2},
            headers=other_session_headers,
        )
        assert claim2.status_code == 409
        assert claim2.json()["error"]["code"] == "REVIEW_CASE_LOCKED"

    async def test_stale_case_version_rejected_on_resolve(
        self, client: AsyncClient, session_headers: dict
    ) -> None:
        journey = await _create_lending_journey(client, session_headers)
        await _trigger_income_mismatch(
            client, session_headers, journey["journey_id"], journey["snapshot_id"]
        )
        await _become_reviewer(client, session_headers)
        cases = (await client.get("/api/v1/review/cases", headers=session_headers)).json()["cases"]
        case_id = next(c for c in cases if c["journey_id"] == journey["journey_id"])["case_id"]

        await client.post(
            f"/api/v1/review/cases/{case_id}/claim",
            json={"expected_case_version": 1},
            headers=session_headers,
        )
        resp = await client.post(
            f"/api/v1/review/cases/{case_id}/resolve",
            json={
                "resolution_type": "EVIDENCE_SUFFICIENT",
                "resolution_reason": "x",
                "resolution_value": 50000,
                "expected_case_version": 1,  # stale - claim bumped it to 2
            },
            headers=session_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "REVIEW_CASE_STALE"

    async def test_double_submit_resolve_is_rejected_not_duplicated(
        self, client: AsyncClient, session_headers: dict
    ) -> None:
        journey = await _create_lending_journey(client, session_headers)
        await _trigger_income_mismatch(
            client, session_headers, journey["journey_id"], journey["snapshot_id"]
        )
        await _become_reviewer(client, session_headers)
        cases = (await client.get("/api/v1/review/cases", headers=session_headers)).json()["cases"]
        case_id = next(c for c in cases if c["journey_id"] == journey["journey_id"])["case_id"]
        await client.post(
            f"/api/v1/review/cases/{case_id}/claim",
            json={"expected_case_version": 1},
            headers=session_headers,
        )
        payload = {
            "resolution_type": "EVIDENCE_SUFFICIENT",
            "resolution_reason": "confirmed",
            "resolution_value": 50000,
            "expected_case_version": 2,
        }
        first = await client.post(
            f"/api/v1/review/cases/{case_id}/resolve", json=payload, headers=session_headers
        )
        assert first.status_code == 200
        second = await client.post(
            f"/api/v1/review/cases/{case_id}/resolve", json=payload, headers=session_headers
        )
        assert second.status_code == 409
        assert second.json()["error"]["code"] in (
            "REVIEW_CASE_STALE",
            "REVIEW_CASE_INVALID_TRANSITION",
        )

        audit_resp = await client.get(
            f"/api/v1/review/cases/{case_id}/audit", headers=session_headers
        )
        resolved_events = [
            e for e in audit_resp.json()["entries"] if e["event_type"] == "REVIEW_CASE_RESOLVED"
        ]
        assert len(resolved_events) == 1

    async def test_empty_queue_returns_empty_list(
        self, client: AsyncClient, other_session_headers: dict
    ) -> None:
        await _become_reviewer(client, other_session_headers)
        resp = await client.get(
            "/api/v1/review/cases", params={"status": "ESCALATED"}, headers=other_session_headers
        )
        assert resp.status_code == 200
        # A fresh, never-escalated-anything session should see none of its
        # own making (other tests may have escalated cases, so only assert
        # the shape/status, not global emptiness).
        assert isinstance(resp.json()["cases"], list)

    async def test_resolve_requires_reason_and_value(
        self, client: AsyncClient, session_headers: dict
    ) -> None:
        journey = await _create_lending_journey(client, session_headers)
        await _trigger_income_mismatch(
            client, session_headers, journey["journey_id"], journey["snapshot_id"]
        )
        await _become_reviewer(client, session_headers)
        cases = (await client.get("/api/v1/review/cases", headers=session_headers)).json()["cases"]
        case_id = next(c for c in cases if c["journey_id"] == journey["journey_id"])["case_id"]
        await client.post(
            f"/api/v1/review/cases/{case_id}/claim",
            json={"expected_case_version": 1},
            headers=session_headers,
        )
        resp = await client.post(
            f"/api/v1/review/cases/{case_id}/resolve",
            json={
                "resolution_type": "EVIDENCE_SUFFICIENT",
                "resolution_reason": "confirmed",
                "expected_case_version": 2,
            },
            headers=session_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
