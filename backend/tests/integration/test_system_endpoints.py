import pytest
from httpx import AsyncClient

from app.config import settings


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ["ok", "degraded"]
    assert "db" in data
    assert data["packs_loaded"] == 6
    assert data["packs_supported"] == 6
    assert data["ai_provider"] in ["mock", "llm", "local_ml"]
    assert "git_sha" in data


@pytest.mark.asyncio
async def test_session_endpoint_new_and_existing(client: AsyncClient):
    # Call without session cookie/header -> creates new session
    resp1 = await client.get("/api/v1/session")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert "session_id" in data1
    assert data1["created"] is True

    # Call with existing session header -> returns existing session with created=False
    session_id = data1["session_id"]
    resp2 = await client.get("/api/v1/session", headers={"X-Session-Id": session_id})
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["session_id"] == session_id
    assert data2["created"] is False


@pytest.mark.asyncio
async def test_demo_reset_endpoint(client: AsyncClient):
    # Without secret header -> 401
    resp_unauth = await client.post("/api/v1/demo/reset")
    assert resp_unauth.status_code == 401

    # With wrong secret -> 401
    resp_wrong = await client.post(
        "/api/v1/demo/reset",
        headers={"X-Demo-Secret": "wrong-secret"},
    )
    assert resp_wrong.status_code == 401

    # With valid secret -> 200
    resp_ok = await client.post(
        "/api/v1/demo/reset",
        headers={"X-Demo-Secret": settings.DEMO_RESET_SECRET},
    )
    print("DEBUG RESP_OK:", resp_ok.status_code, resp_ok.text)
    assert resp_ok.status_code == 200
    data = resp_ok.json()
    assert data["reset"] is True
    assert isinstance(data["elapsed_ms"], int)
