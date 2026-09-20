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


async def _create_lending_journey(
    client: AsyncClient, headers: dict[str, str], customer_email: str | None = None
) -> dict:
    body: dict = {
        "journey_type": "LENDING",
        "goal": {"loan_amount": 200000, "loan_purpose": "EDUCATION", "tenure_months": 24},
    }
    if customer_email:
        body["customer_email"] = customer_email
    resp = await client.post("/api/v1/journeys", json=body, headers=headers)
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


async def _drive_journey_to_ready(
    client: AsyncClient, headers: dict[str, str], journey: dict
) -> dict:
    """Runs the real LENDING golden path (verified against
    tests/integration/test_full_journey_flow.py) through to READY via four
    real apply_action calls - never a shortcut that writes journey state
    directly. Returns the final action response's `journey` dict."""
    snap_id = journey["snapshot_id"]

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey['journey_id']}/evidence",
        data={
            "doc_type": "SALARY_SLIP",
            "expected_snapshot_id": snap_id,
            "manual_fields": '{"monthly_income": 85000}',
        },
        headers=headers,
    )
    assert ev_resp.status_code == 200, ev_resp.text
    evidence_id = ev_resp.json()["evidence_id"]

    resp = await client.post(
        f"/api/v1/journeys/{journey['journey_id']}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": snap_id,
            "idempotency_key": str(uuid4()),
            "input": {"evidence_id": evidence_id},
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    snap_id = resp.json()["journey"]["snapshot_id"]

    resp = await client.post(
        f"/api/v1/journeys/{journey['journey_id']}/actions",
        json={
            "action_id": "SUBMIT_EMPLOYMENT_INFO",
            "expected_snapshot_id": snap_id,
            "idempotency_key": str(uuid4()),
            "input": {"employment_type": "SALARIED"},
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    snap_id = resp.json()["journey"]["snapshot_id"]

    resp = await client.post(
        f"/api/v1/journeys/{journey['journey_id']}/actions",
        json={
            "action_id": "VERIFY_EMPLOYER_RECORD",
            "expected_snapshot_id": snap_id,
            "idempotency_key": str(uuid4()),
            "input": {"employer_name": "Infosys Ltd"},
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    snap_id = resp.json()["journey"]["snapshot_id"]

    resp = await client.post(
        f"/api/v1/journeys/{journey['journey_id']}/actions",
        json={
            "action_id": "ACCEPT_LOAN_TERMS",
            "expected_snapshot_id": snap_id,
            "idempotency_key": str(uuid4()),
            "input": {"accept_terms": True},
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    final_journey = resp.json()["journey"]
    assert final_journey["readiness"] == "READY", final_journey
    return final_journey


def _event_types(mock_dispatch: AsyncMock) -> list[str]:
    return [call.args[0]["event"] for call in mock_dispatch.await_args_list]


def _assert_valid_payload(mock_dispatch: AsyncMock) -> None:
    """Regression guard for the real bug found and fixed while integrating
    with the live n8n workflow: its own "Valid Payload?" node requires
    event/case_id/journey_id/event_id/timestamp to ALL be non-empty, and
    rejects the request with a real 400 if any is missing - every event
    this dispatcher ever sends must satisfy that."""
    for call in mock_dispatch.await_args_list:
        payload = call.args[0]
        for required_key in ("event", "case_id", "journey_id", "event_id", "timestamp"):
            assert payload.get(required_key), f"{required_key} must be non-empty: {payload}"
        assert payload.get("message"), f"message must be non-empty: {payload}"


class TestN8nNotifications:
    async def test_income_mismatch_fires_review_required(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        _enable_n8n(monkeypatch)
        journey = await _create_lending_journey(client, session_headers)

        with patch("app.integrations.n8n_client._dispatch", new=AsyncMock()) as mock_dispatch:
            await _trigger_income_mismatch(client, session_headers, journey)

        assert "REVIEW_REQUIRED" in _event_types(mock_dispatch)
        _assert_valid_payload(mock_dispatch)

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
        _assert_valid_payload(mock_dispatch)

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
        _assert_valid_payload(mock_dispatch)

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
        _assert_valid_payload(mock_dispatch)

    async def test_resolve_case_includes_real_customer_email_when_provided(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        """JOURNEY_RESOLVED is the customer-facing event n8n's "Email
        Customer" node consumes - when the journey was created with a real
        email, it must reach the payload verbatim, not "" ."""
        _enable_n8n(monkeypatch)
        journey = await _create_lending_journey(
            client, session_headers, customer_email="customer@example.com"
        )
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
        resolved_payload = next(
            call.args[0]
            for call in mock_dispatch.await_args_list
            if call.args[0]["event"] == "JOURNEY_RESOLVED"
        )
        assert resolved_payload["customer_email"] == "customer@example.com"
        _assert_valid_payload(mock_dispatch)

    async def test_resolve_case_email_is_empty_when_never_provided(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        """Anonymous journeys (the overwhelming majority) must keep working
        exactly as before - an empty string, not a missing key or an error."""
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
        resolved_payload = next(
            call.args[0]
            for call in mock_dispatch.await_args_list
            if call.args[0]["event"] == "JOURNEY_RESOLVED"
        )
        assert resolved_payload["customer_email"] == ""

    async def test_request_information_includes_real_customer_email_when_provided(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        _enable_n8n(monkeypatch)
        journey = await _create_lending_journey(
            client, session_headers, customer_email="customer@example.com"
        )
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
        payload = next(
            call.args[0]
            for call in mock_dispatch.await_args_list
            if call.args[0]["event"] == "CUSTOMER_ACTION_REQUIRED"
        )
        assert payload["customer_email"] == "customer@example.com"
        _assert_valid_payload(mock_dispatch)

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
        _assert_valid_payload(mock_dispatch)

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

    # -- JOURNEY_COMPLETED: fires when the journey's OWN readiness reaches
    # READY, independent of whether it ever went through Review Center. --

    async def test_journey_reaching_ready_fires_journey_completed(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        _enable_n8n(monkeypatch)
        journey = await _create_lending_journey(client, session_headers)

        with patch("app.integrations.n8n_client._dispatch", new=AsyncMock()) as mock_dispatch:
            await _drive_journey_to_ready(client, session_headers, journey)

        assert "JOURNEY_COMPLETED" in _event_types(mock_dispatch)
        _assert_valid_payload(mock_dispatch)

    async def test_journey_completed_includes_real_customer_email_when_provided(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        _enable_n8n(monkeypatch)
        journey = await _create_lending_journey(
            client, session_headers, customer_email="customer@example.com"
        )

        with patch("app.integrations.n8n_client._dispatch", new=AsyncMock()) as mock_dispatch:
            await _drive_journey_to_ready(client, session_headers, journey)

        payload = next(
            call.args[0]
            for call in mock_dispatch.await_args_list
            if call.args[0]["event"] == "JOURNEY_COMPLETED"
        )
        assert payload["customer_email"] == "customer@example.com"

    async def test_journey_completed_email_is_empty_when_never_provided(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        """Missing email must never crash journey completion - it degrades
        to an empty string exactly like the five existing events."""
        _enable_n8n(monkeypatch)
        journey = await _create_lending_journey(client, session_headers)

        with patch("app.integrations.n8n_client._dispatch", new=AsyncMock()) as mock_dispatch:
            final_journey = await _drive_journey_to_ready(client, session_headers, journey)

        assert final_journey["readiness"] == "READY"
        payload = next(
            call.args[0]
            for call in mock_dispatch.await_args_list
            if call.args[0]["event"] == "JOURNEY_COMPLETED"
        )
        assert payload["customer_email"] == ""

    async def test_repeated_action_after_ready_does_not_duplicate_completion_event(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        """Idempotency: ACCEPT_LOAN_TERMS's own preconditions (monthly_income
        and employer_name SATISFIED) remain met even after the journey is
        already READY, so it can genuinely be re-submitted with a fresh
        idempotency_key (see app/core/deterministic_check.py - preconditions
        are checked, not whether the action's own target is already
        satisfied). Readiness is recomputed and stays READY. This must NOT
        re-fire JOURNEY_COMPLETED - only the actual NOT_READY -> READY edge
        does, per journey_service.py's previous_readiness guard."""
        _enable_n8n(monkeypatch)
        journey = await _create_lending_journey(client, session_headers)

        with patch("app.integrations.n8n_client._dispatch", new=AsyncMock()) as mock_dispatch:
            final_journey = await _drive_journey_to_ready(client, session_headers, journey)
        assert _event_types(mock_dispatch).count("JOURNEY_COMPLETED") == 1

        with patch("app.integrations.n8n_client._dispatch", new=AsyncMock()) as mock_dispatch_2:
            resp = await client.post(
                f"/api/v1/journeys/{journey['journey_id']}/actions",
                json={
                    "action_id": "ACCEPT_LOAN_TERMS",
                    "expected_snapshot_id": final_journey["snapshot_id"],
                    "idempotency_key": str(uuid4()),
                    "input": {"accept_terms": True},
                },
                headers=session_headers,
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["journey"]["readiness"] == "READY"
        assert "JOURNEY_COMPLETED" not in _event_types(mock_dispatch_2)

    async def test_journey_completed_never_fires_for_the_five_existing_events(
        self, client: AsyncClient, session_headers: dict, monkeypatch
    ) -> None:
        """Regression guard: the review-lifecycle flow (mismatch -> claim ->
        resolve) must keep firing exactly the events it fired before this
        change - JOURNEY_COMPLETED is a distinct event, never a relabeling
        of JOURNEY_RESOLVED."""
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
        events = _event_types(mock_dispatch)
        assert "JOURNEY_RESOLVED" in events
        assert "JOURNEY_COMPLETED" not in events
        _assert_valid_payload(mock_dispatch)
