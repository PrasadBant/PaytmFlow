from fastapi import APIRouter, HTTPException

from app.packs.registry import pack_registry
from app.schemas.enums import ErrorCode, JourneyType
from app.schemas.errors import ErrorEnvelope, ErrorObject
from app.schemas.packs import (
    JourneyPackDetail,
    JourneyPacksListResponse,
    JourneyPackSummary,
)

router = APIRouter()


@router.get(
    "/journey-packs",
    response_model=JourneyPacksListResponse,
    tags=["packs"],
    operation_id="listJourneyPacks",
)
async def list_journey_packs() -> JourneyPacksListResponse:
    summaries = [
        JourneyPackSummary(
            journey_type=manifest.metadata.journey_type,
            display_name=manifest.metadata.display_name,
            description=manifest.metadata.description,
            icon=manifest.metadata.icon,
            flagship_demo=manifest.metadata.flagship_demo,
            lifecycle_status=manifest.metadata.lifecycle_status,
        )
        for manifest in pack_registry.list_packs()
    ]
    return JourneyPacksListResponse(packs=summaries)


@router.get(
    "/journey-packs/{journey_type}",
    response_model=JourneyPackDetail,
    responses={404: {"model": ErrorEnvelope, "description": "Not found"}},
    tags=["packs"],
    operation_id="getJourneyPack",
)
async def get_journey_pack(journey_type: JourneyType) -> JourneyPackDetail:
    manifest = pack_registry.get_pack(journey_type)
    if not manifest:
        raise HTTPException(
            status_code=404,
            detail=ErrorEnvelope(
                error=ErrorObject(
                    code=ErrorCode.INVALID_JOURNEY_TYPE,
                    message=f"Journey pack '{journey_type.value}' not found",
                )
            ).model_dump(mode="json"),
        )

    return JourneyPackDetail(
        journey_type=manifest.metadata.journey_type,
        display_name=manifest.metadata.display_name,
        description=manifest.metadata.description,
        icon=manifest.metadata.icon,
        flagship_demo=manifest.metadata.flagship_demo,
        lifecycle_status=manifest.metadata.lifecycle_status,
        schema_version=manifest.metadata.schema_version,
        goal_schema=manifest.goal_schema,
        supports_natural_language=manifest.metadata.supports_natural_language,
        ui_labels=manifest.ui_labels,
    )
