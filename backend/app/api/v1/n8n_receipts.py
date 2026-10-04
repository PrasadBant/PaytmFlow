"""Receiver-side idempotency endpoints, called only by the n8n workflow.

Authenticated with the same shared header the backend sends to n8n
(N8N_WEBHOOK_HEADER_NAME / N8N_WEBHOOK_SECRET), compared in constant time.
Fails closed: with no secret configured every call is refused.
See app/integrations/n8n_receipts.py for the claim semantics."""

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.integrations import n8n_receipts
from app.schemas.n8n_receipts import (
    EVENT_ID_PATTERN,
    ReceiptClaimRequest,
    ReceiptClaimResponse,
    ReceiptCompleteResponse,
    ReceiptReleaseResponse,
)

router = APIRouter()
_UNAUTHORIZED: dict[int | str, dict[str, Any]] = {401: {"description": "Bad or missing n8n secret"}}


def require_n8n_secret(request: Request) -> None:
    configured = settings.N8N_WEBHOOK_SECRET
    supplied = request.headers.get(settings.N8N_WEBHOOK_HEADER_NAME, "")
    if (
        not configured
        or not supplied
        or not secrets.compare_digest(supplied.encode(), configured.encode())
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad or missing n8n secret"
        )


_EventIdPath = Path(pattern=EVENT_ID_PATTERN)


@router.post(
    "/n8n/receipts/claim",
    response_model=ReceiptClaimResponse,
    responses=_UNAUTHORIZED,
    tags=["n8n"],
    operation_id="claimN8nReceipt",
    dependencies=[Depends(require_n8n_secret)],
)
async def claim_receipt(body: ReceiptClaimRequest, db: AsyncSession = Depends(get_db)):
    claimed, state = await n8n_receipts.claim(db, body.event_id, body.event_type)
    return ReceiptClaimResponse(event_id=body.event_id, claimed=claimed, status=state)


@router.post(
    "/n8n/receipts/{event_id}/complete",
    response_model=ReceiptCompleteResponse,
    responses={**_UNAUTHORIZED, 404: {"description": "No claim for this event"}},
    tags=["n8n"],
    operation_id="completeN8nReceipt",
    dependencies=[Depends(require_n8n_secret)],
)
async def complete_receipt(event_id: str = _EventIdPath, db: AsyncSession = Depends(get_db)):
    state = await n8n_receipts.complete(db, event_id)
    if state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No claim for this event")
    return ReceiptCompleteResponse(event_id=event_id, status=state)


@router.post(
    "/n8n/receipts/{event_id}/release",
    response_model=ReceiptReleaseResponse,
    responses=_UNAUTHORIZED,
    tags=["n8n"],
    operation_id="releaseN8nReceipt",
    dependencies=[Depends(require_n8n_secret)],
)
async def release_receipt(event_id: str = _EventIdPath, db: AsyncSession = Depends(get_db)):
    released = await n8n_receipts.release(db, event_id)
    return ReceiptReleaseResponse(event_id=event_id, released=released)
