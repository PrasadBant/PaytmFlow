import pytest
from httpx import AsyncClient

from app.schemas.enums import JourneyType


@pytest.mark.asyncio
async def test_list_journey_packs(client: AsyncClient):
    resp = await client.get("/api/v1/journey-packs")
    assert resp.status_code == 200
    data = resp.json()
    assert "packs" in data
    packs = data["packs"]
    assert len(packs) == 6

    pack_types = {p["journey_type"] for p in packs}
    expected_types = {jt.value for jt in JourneyType}
    assert pack_types == expected_types

    for p in packs:
        assert "display_name" in p
        assert "description" in p
        assert "icon" in p
        assert "flagship_demo" in p
        assert "lifecycle_status" in p


@pytest.mark.asyncio
@pytest.mark.parametrize("journey_type", list(JourneyType))
async def test_get_journey_pack_detail_all_six(client: AsyncClient, journey_type: JourneyType):
    resp = await client.get(f"/api/v1/journey-packs/{journey_type.value}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["journey_type"] == journey_type.value
    assert "goal_schema" in data
    assert len(data["goal_schema"]) > 0
    assert "ui_labels" in data
    assert "schema_version" in data


@pytest.mark.asyncio
async def test_get_journey_pack_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/journey-packs/NON_EXISTENT_PACK")
    assert resp.status_code in [400, 404, 422]
    data = resp.json()
    assert "error" in data
