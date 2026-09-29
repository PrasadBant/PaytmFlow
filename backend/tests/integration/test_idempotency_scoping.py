"""Regression tests: an idempotency key replays only for the same session,
journey, and request payload - never another session's cached response."""

from uuid import uuid4

from httpx import AsyncClient


async def _create_lending(client: AsyncClient, headers: dict[str, str]) -> dict:
    resp = await client.post(
        "/api/v1/journeys",
        json={
            "journey_type": "LENDING",
            "goal": {"loan_amount": 250000, "loan_purpose": "EDUCATION", "tenure_months": 36},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _apply(client, headers, journey, key, income=60000):
    return await client.post(
        f"/api/v1/journeys/{journey['journey_id']}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": journey["snapshot_id"],
            "idempotency_key": key,
            "input": {"monthly_income": income},
        },
        headers=headers,
    )


async def test_same_request_same_key_still_replays(client: AsyncClient) -> None:
    headers = {"X-Session-Id": str(uuid4())}
    journey = await _create_lending(client, headers)
    key = str(uuid4())
    first = await _apply(client, headers, journey, key)
    assert first.status_code == 200, first.text
    second = await _apply(client, headers, journey, key)
    assert second.status_code == 200
    assert second.json() == first.json()


async def test_other_session_cannot_replay_foreign_key(client: AsyncClient) -> None:
    victim = {"X-Session-Id": str(uuid4())}
    attacker = {"X-Session-Id": str(uuid4())}
    v_journey = await _create_lending(client, victim)
    a_journey = await _create_lending(client, attacker)
    key = str(uuid4())
    assert (await _apply(client, victim, v_journey, key, income=123456)).status_code == 200

    stolen = await _apply(client, attacker, a_journey, key, income=123456)
    assert stolen.status_code == 400, stolen.text
    assert str(v_journey["journey_id"]) not in stolen.text
    assert "123456" not in stolen.text


async def test_same_key_different_payload_rejected(client: AsyncClient) -> None:
    headers = {"X-Session-Id": str(uuid4())}
    journey = await _create_lending(client, headers)
    key = str(uuid4())
    assert (await _apply(client, headers, journey, key, income=60000)).status_code == 200
    reused = await _apply(client, headers, journey, key, income=90000)
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_same_session_key_reused_on_other_journey_rejected(client: AsyncClient) -> None:
    headers = {"X-Session-Id": str(uuid4())}
    first_journey = await _create_lending(client, headers)
    second_journey = await _create_lending(client, headers)
    key = str(uuid4())
    assert (await _apply(client, headers, first_journey, key)).status_code == 200
    reused = await _apply(client, headers, second_journey, key)
    assert reused.status_code == 400
    assert str(first_journey["journey_id"]) not in reused.text
