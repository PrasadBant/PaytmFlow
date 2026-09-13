from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import JourneyModel, SessionModel
from app.db.session import get_db
from app.evidence.reconcile import EvidenceReconciliationService
from app.schemas.errors import ErrorEnvelope
from app.schemas.evidence import EvidenceResponse
from app.security.session import get_current_session, verify_journey_ownership

router = APIRouter()


@router.post(
    "/journeys/{journey_id}/evidence",
    response_model=EvidenceResponse,
    responses={
        400: {"model": ErrorEnvelope, "description": "Validation error"},
        409: {"model": ErrorEnvelope, "description": "Action stale"},
        413: {"model": ErrorEnvelope, "description": "File too large"},
    },
    tags=["evidence"],
    operation_id="uploadEvidence",
)
async def upload_evidence(
    journey_id: UUID,
    doc_type: str = Form(...),
    expected_snapshot_id: UUID = Form(...),
    manual_fields: str | None = Form(None),
    file: UploadFile | None = File(None),
    journey: JourneyModel = Depends(verify_journey_ownership),
    current_session: SessionModel = Depends(get_current_session),
    db_session: AsyncSession = Depends(get_db),
) -> EvidenceResponse:
    file_bytes: bytes | None = None
    filename: str | None = None
    if file is not None:
        file_bytes = await file.read()
        filename = file.filename

    service = EvidenceReconciliationService(db_session)
    return await service.submit_evidence(
        journey=journey,
        doc_type=doc_type,
        expected_snapshot_id=expected_snapshot_id,
        current_session=current_session,
        file_bytes=file_bytes,
        filename=filename,
        manual_fields_json=manual_fields,
    )
