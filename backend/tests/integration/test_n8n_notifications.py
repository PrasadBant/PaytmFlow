"""Integration tests confirming the n8n dispatcher actually fires at each
of the five real Review Center / evidence lifecycle points, through the
real HTTP API - not just the unit-level queue/flush mechanics already
covered by tests/unit/test_n8n_client.py.

Patches `app.integrations.n8n_client._dispatch` (the function that actually
performs the outbound POST) rather than `httpx.AsyncClient.post` directly:
the test `client` fixture is ITSELF an httpx.AsyncClient hitting the app
over ASGI, so a global httpx.AsyncClient.post patch would also intercept
the test's own request to the app. `_dispatch` is the correct, narrower
boundary for these tests - httpx-level behavior (headers, error handling)
is already covered by tests/unit/test_n8n_client.py.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from httpx import AsyncClient

from app.config import settings


def _enable_n8n(monkeypatch) -> None:
    monkeypatch.setattr(settings, "N8N_ENABLED", True)
    monkeypatch.setattr(
        settings, "N8N_WEBHOOK_URL", "https://example.n8n.cloud/webhook/paytmflow-events"
    )


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
    client: AsyncClient, headers: dict[str, str], journey: dict
) -> None:
    resp = await client.post(
        f"/api/v1/journeys/{journey['journey_id']}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": journey["snapshot_id"],
            "idempotency_key": str(uuid4()),
            "input": {"monthly_income": 30000, "ambiguity_id": "INCOME_MISMATCH"},
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


async def _become_reviewer(client: AsyncClient, headers: dict[str, str]) -> None:
    resp = await client.post(
        "/api/v1/review/role", json={"role": "REVIEW_OFFICER"}, headers=headers
    )
    assert resp.status_code == 200, resp.text


async def _claim_case_for_journey(
    client: AsyncClient, headers: dict[str, str], journey_id: str
) -> dict:
    await _become_reviewer(client, headers)
    queue_resp = await client.get("/api/v1/review/cases", headers=headers)
    case = next(c for c in queue_resp.json()["cases"] if c["journey_id"] == journey_id)
    claim_resp = await client.post(
        f"/api/v1/review/cases/{case['case_id']}/claim",
        json={"expected_case_version": case["case_version"]},
        headers=headers,
    )
    assert claim_resp.status_code == 200, claim_resp.text
    return claim_resp.json()


def _event_types(mock_dispatch: AsyncMock) -> list[str]:
    return [call.args[0]["event_type"] for call in mock_dispatch.await_args_list]


class TestN8nNotifications:
    async def test_income_mismatch_fires_review_required(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        _enable_n8n(monkeypatch)
        journey = await _create_lending_journey(client, session_headers)

        with patch("app.integrations.n8n_client._dispatch", new=AsyncMock()) as mock_dispatch:
            await _trigger_income_mismatch(client, session_headers, journey)

        assert "REVIEW_REQUIRED" in _event_types(mock_dispatch)

    async def test_evidence_upload_fires_evidence_uploaded(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        _enable_n8n(monkeypatch)
        journey = await _create_lending_journey(client, session_headers)

        with patch("app.integrations.n8n_client._dispatch", new=AsyncMock()) as mock_dispatch:
            resp = await client.post(
                f"/api/v1/journeys/{journey['journey_id']}/evidence",
                data={
                    "doc_type": "SALARY_SLIP",
                    "expected_snapshot_id": journey["snapshot_id"],
                    "manual_fields": '{"monthly_income": 66500}',
                },
                headers=session_headers,
            )
        assert resp.status_code == 200, resp.text
        assert "EVIDENCE_UPLOADED" in _event_types(mock_dispatch)

    async def test_request_information_fires_customer_action_required(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        _enable_n8n(monkeypatch)
        journey = await _create_lending_journey(client, session_headers)
        with patch("app.integrations.n8n_client._dispatch", new=AsyncMock()):
            await _trigger_income_mismatch(client, session_headers, journey)
        claimed = await _claim_case_for_journey(client, session_headers, journey["journey_id"])

        with patch("app.integrations.n8n_client._dispatch", new=AsyncMock()) as mock_dispatch:
            resp = await client.post(
                f"/api/v1/review/cases/{claimed['case_id']}/request-information",
                json={
                    "requested_docs": ["Bank Statement"],
                    "customer_message": "Please upload your latest bank statement.",
                    "expected_case_version": claimed["case_version"],
                },
                headers=session_headers,
            )
        assert resp.status_code == 200, resp.text
        assert "CUSTOMER_ACTION_REQUIRED" in _event_types(mock_dispatch)

    async def test_resolve_case_fires_journey_resolved(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        _enable_n8n(monkeypatch)
        journey = await _create_lending_journey(client, session_headers)
        with patch("app.integrations.n8n_client._dispatch", new=AsyncMock()):
            await _trigger_income_mismatch(client, session_headers, journey)
        claimed = await _claim_case_for_journey(client, session_headers, journey["journey_id"])

        with patch("app.integrations.n8n_client._dispatch", new=AsyncMock()) as mock_dispatch:
            resp = await client.post(
                f"/api/v1/review/cases/{claimed['case_id']}/resolve",
                json={
                    "resolution_type": "EVIDENCE_SUFFICIENT",
                    "resolution_reason": "Bank statement confirms declared income.",
                    "resolution_value": 30000,
                    "expected_case_version": claimed["case_version"],
                },
                headers=session_headers,
            )
        assert resp.status_code == 200, resp.text
        assert "JOURNEY_RESOLVED" in _event_types(mock_dispatch)

    async def test_escalate_case_fires_escalated(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        _enable_n8n(monkeypatch)
        journey = await _create_lending_journey(client, session_headers)
        with patch("app.integrations.n8n_client._dispatch", new=AsyncMock()):
            await _trigger_income_mismatch(client, session_headers, journey)
        claimed = await _claim_case_for_journey(client, session_headers, journey["journey_id"])

        with patch("app.integrations.n8n_client._dispatch", new=AsyncMock()) as mock_dispatch:
            resp = await client.post(
                f"/api/v1/review/cases/{claimed['case_id']}/escalate",
                json={
                    "escalation_reason": "Needs policy exception review.",
                    "expected_case_version": claimed["case_version"],
                },
                headers=session_headers,
            )
        assert resp.status_code == 200, resp.text
        assert "ESCALATED" in _event_types(mock_dispatch)

    async def test_n8n_disabled_never_dispatches(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "N8N_ENABLED", False)
        journey = await _create_lending_journey(client, session_headers)

        with patch(
            "app.integrations.n8n_client._dispatch",
            new=AsyncMock(side_effect=AssertionError("must not be called")),
        ):
            await _trigger_income_mismatch(client, session_headers, journey)

    async def test_n8n_dispatch_failure_does_not_break_the_request(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        """n8n being unreachable (or _dispatch itself misbehaving) must
        never surface as a failure of the actual journey/review-case
        mutation it's attached to - see flush_n8n_events's defense-in-depth
        try/except around each dispatch."""
        _enable_n8n(monkeypatch)
        journey = await _create_lending_journey(client, session_headers)

        with patch(
            "app.integrations.n8n_client._dispatch",
            new=AsyncMock(side_effect=RuntimeError("simulated dispatch bug")),
        ):
            resp = await client.post(
                f"/api/v1/journeys/{journey['journey_id']}/actions",
                json={
                    "action_id": "UPLOAD_INCOME_PROOF",
                    "expected_snapshot_id": journey["snapshot_id"],
                    "idempotency_key": str(uuid4()),
                    "input": {"monthly_income": 30000, "ambiguity_id": "INCOME_MISMATCH"},
                },
                headers=session_headers,
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["journey"]["readiness"] == "NEEDS_REVIEW"
