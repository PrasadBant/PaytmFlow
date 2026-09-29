"""Regression tests: a customer session must not be able to self-promote to
REVIEW_OFFICER (and thereby read/mutate every other session's review cases)
outside local/ci without the server-held REVIEWER_ACCESS_CODE."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.config import settings


@pytest.fixture
def production_like(monkeypatch: pytest.MonkeyPatch):
    def _apply(code: str) -> None:
        monkeypatch.setattr(settings, "APP_ENV", "ci")
        monkeypatch.setattr(settings, "REVIEWER_ACCESS_CODE", code)

    return _apply


async def _switch(client: AsyncClient, headers: dict, role: str, code: str | None = None):
    body: dict = {"role": role}
    if code is not None:
        body["access_code"] = code
    return await client.post("/api/v1/review/role", json=body, headers=headers)


def _headers() -> dict[str, str]:
    return {"X-Session-Id": str(uuid4())}


async def test_promotion_refused_without_code_when_code_configured(
    client: AsyncClient, production_like
) -> None:
    production_like("correct-horse")
    headers = _headers()
    r = await _switch(client, headers, "REVIEW_OFFICER")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"
    assert (await client.get("/api/v1/review/cases", headers=headers)).status_code == 403


async def test_promotion_refused_with_wrong_code(client: AsyncClient, production_like) -> None:
    production_like("correct-horse")
    headers = _headers()
    r = await _switch(client, headers, "REVIEW_OFFICER", "wrong")
    assert r.status_code == 403
    assert (await client.get("/api/v1/review/dashboard", headers=headers)).status_code == 403


async def test_promotion_allowed_with_correct_code(client: AsyncClient, production_like) -> None:
    production_like("correct-horse")
    headers = _headers()
    r = await _switch(client, headers, "REVIEW_OFFICER", "correct-horse")
    assert r.status_code == 200
    assert r.json()["role"] == "REVIEW_OFFICER"
    assert (await client.get("/api/v1/review/cases", headers=headers)).status_code == 200


async def test_promotion_fails_closed_outside_local_ci_when_no_code_configured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # APP_ENV must be local/ci for the X-Session-Id test header, so exercise the
    # production branch directly through the authorization function.
    from fastapi import HTTPException

    from app.schemas.enums import ReviewerRole
    from app.security.reviewer import authorize_role_switch

    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "REVIEWER_ACCESS_CODE", "")
    with pytest.raises(HTTPException) as exc:
        authorize_role_switch(ReviewerRole.REVIEW_OFFICER, "anything")
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException):
        authorize_role_switch(ReviewerRole.REVIEW_OFFICER, None)
    authorize_role_switch(ReviewerRole.CUSTOMER, None)


async def test_downgrade_to_customer_never_requires_code(
    client: AsyncClient, production_like
) -> None:
    production_like("correct-horse")
    headers = _headers()
    assert (await _switch(client, headers, "REVIEW_OFFICER", "correct-horse")).status_code == 200
    r = await _switch(client, headers, "CUSTOMER")
    assert r.status_code == 200
    assert r.json()["role"] == "CUSTOMER"
    assert (await client.get("/api/v1/review/cases", headers=headers)).status_code == 403


async def test_unrelated_session_not_promoted_by_another_sessions_switch(
    client: AsyncClient, production_like
) -> None:
    production_like("correct-horse")
    reviewer, customer = _headers(), _headers()
    assert (await _switch(client, reviewer, "REVIEW_OFFICER", "correct-horse")).status_code == 200
    assert (await client.get("/api/v1/review/cases", headers=customer)).status_code == 403


async def test_client_supplied_role_header_is_ignored(client: AsyncClient, production_like) -> None:
    production_like("correct-horse")
    headers = {**_headers(), "X-Role": "REVIEW_OFFICER", "X-Reviewer": "true"}
    assert (await client.get("/api/v1/review/cases", headers=headers)).status_code == 403


async def test_role_granted_before_gate_is_not_honoured(
    client: AsyncClient, production_like, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Simulates a session that self-promoted before the access code existed.
    monkeypatch.setattr(settings, "APP_ENV", "ci")
    monkeypatch.setattr(settings, "REVIEWER_ACCESS_CODE", "")
    headers = _headers()
    assert (await _switch(client, headers, "REVIEW_OFFICER")).status_code == 200
    assert (await client.get("/api/v1/review/cases", headers=headers)).status_code == 200

    production_like("correct-horse")
    assert (await client.get("/api/v1/review/cases", headers=headers)).status_code == 403


async def test_rotating_code_revokes_existing_reviewers(
    client: AsyncClient, production_like
) -> None:
    production_like("old-code")
    headers = _headers()
    assert (await _switch(client, headers, "REVIEW_OFFICER", "old-code")).status_code == 200
    assert (await client.get("/api/v1/review/cases", headers=headers)).status_code == 200

    production_like("new-code")
    assert (await client.get("/api/v1/review/cases", headers=headers)).status_code == 403


@pytest.mark.parametrize("bad_code", [12345, ["correct-horse"], {"c": 1}, "x" * 257])
async def test_malformed_access_code_rejected(
    client: AsyncClient, production_like, bad_code
) -> None:
    production_like("correct-horse")
    headers = _headers()
    r = await client.post(
        "/api/v1/review/role",
        json={"role": "REVIEW_OFFICER", "access_code": bad_code},
        headers=headers,
    )
    assert r.status_code in (400, 422), r.text
    assert (await client.get("/api/v1/review/cases", headers=headers)).status_code == 403


async def test_every_reviewer_endpoint_rejects_ungranted_session(
    client: AsyncClient, production_like
) -> None:
    production_like("correct-horse")
    headers = _headers()
    await _switch(client, headers, "REVIEW_OFFICER", "wrong")
    case_id = str(uuid4())
    gets = [
        "/api/v1/review/dashboard",
        "/api/v1/review/cases",
        f"/api/v1/review/cases/{case_id}",
        f"/api/v1/review/cases/{case_id}/customer-view",
        f"/api/v1/review/cases/{case_id}/audit",
    ]
    posts = [
        f"/api/v1/review/cases/{case_id}/claim",
        f"/api/v1/review/cases/{case_id}/resolve",
        f"/api/v1/review/cases/{case_id}/request-information",
        f"/api/v1/review/cases/{case_id}/escalate",
        f"/api/v1/review/cases/{case_id}/ai-summary",
    ]
    for path in gets:
        assert (await client.get(path, headers=headers)).status_code == 403, path
    for path in posts:
        assert (await client.post(path, json={}, headers=headers)).status_code in (403, 422), path
