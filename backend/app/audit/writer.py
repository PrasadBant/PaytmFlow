from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.events import AuditEventType
from app.db.models import AuditEventModel
from app.db.repositories.audit import AuditRepository


class AuditWriter:
    """Helper service to write typed, immutable audit events into the database."""

    def __init__(self, session_or_repo: AsyncSession | AuditRepository):
        if isinstance(session_or_repo, AuditRepository):
            self.repo = session_or_repo
        else:
            self.repo = AuditRepository(session_or_repo)

    async def record_journey_created(
        self,
        journey_id: UUID,
        session_id: UUID,
        journey_type: str,
        goal: dict[str, Any],
        initial_snapshot_id: UUID,
        initial_values: dict[str, Any] | None = None,
    ) -> AuditEventModel:
        return await self.repo.create(
            journey_id=journey_id,
            session_id=session_id,
            event_type=AuditEventType.JOURNEY_CREATED,
            payload={
                "journey_type": journey_type,
                "goal": goal,
                "initial_snapshot_id": str(initial_snapshot_id),
                "initial_values": initial_values or {},
            },
        )

    async def record_action_executed(
        self,
        journey_id: UUID,
        session_id: UUID,
        action_id: str,
        token_id: UUID,
        snapshot_id: UUID,
        version_number: int,
        action_input: dict[str, Any],
        new_values: dict[str, Any],
    ) -> AuditEventModel:
        return await self.repo.create(
            journey_id=journey_id,
            session_id=session_id,
            event_type=AuditEventType.ACTION_EXECUTED,
            payload={
                "action_id": action_id,
                "token_id": str(token_id),
                "snapshot_id": str(snapshot_id),
                "version_number": version_number,
                "action_input": action_input,
                "new_values": new_values,
            },
        )

    async def record_action_rejected(
        self,
        journey_id: UUID,
        session_id: UUID | None,
        action_id: str,
        reason: str,
        error_code: str,
        details: dict[str, Any] | None = None,
    ) -> AuditEventModel:
        return await self.repo.create(
            journey_id=journey_id,
            session_id=session_id,
            event_type=AuditEventType.ACTION_REJECTED,
            payload={
                "action_id": action_id,
                "reason": reason,
                "error_code": error_code,
                "details": details or {},
            },
        )

    async def record_evidence_uploaded(
        self,
        journey_id: UUID,
        session_id: UUID,
        evidence_id: UUID,
        doc_type: str,
        filename: str,
        sha256: str,
        confidence: float | None = None,
        extracted_data: dict[str, Any] | None = None,
    ) -> AuditEventModel:
        return await self.repo.create(
            journey_id=journey_id,
            session_id=session_id,
            event_type=AuditEventType.EVIDENCE_UPLOADED,
            payload={
                "evidence_id": str(evidence_id),
                "doc_type": doc_type,
                "filename": filename,
                "sha256": sha256,
                "confidence": confidence,
                "extracted_data": extracted_data or {},
            },
        )

    async def record_clarification_requested(
        self,
        journey_id: UUID,
        session_id: UUID,
        ambiguity_id: str,
        field_key: str,
        question: str,
    ) -> AuditEventModel:
        return await self.repo.create(
            journey_id=journey_id,
            session_id=session_id,
            event_type=AuditEventType.CLARIFICATION_REQUESTED,
            payload={
                "ambiguity_id": ambiguity_id,
                "field_key": field_key,
                "question": question,
            },
        )

    async def record_clarification_answered(
        self,
        journey_id: UUID,
        session_id: UUID,
        clarification_id: UUID,
        ambiguity_id: str,
        field_key: str,
        user_response: dict[str, Any],
        snapshot_id: UUID,
    ) -> AuditEventModel:
        return await self.repo.create(
            journey_id=journey_id,
            session_id=session_id,
            event_type=AuditEventType.CLARIFICATION_ANSWERED,
            payload={
                "clarification_id": str(clarification_id),
                "ambiguity_id": ambiguity_id,
                "field_key": field_key,
                "user_response": user_response,
                "snapshot_id": str(snapshot_id),
            },
        )

    async def record_state_transition(
        self,
        journey_id: UUID,
        session_id: UUID,
        from_readiness: str,
        to_readiness: str,
        from_status: str,
        to_status: str,
        snapshot_id: UUID,
    ) -> AuditEventModel:
        return await self.repo.create(
            journey_id=journey_id,
            session_id=session_id,
            event_type=AuditEventType.STATE_TRANSITION,
            payload={
                "from_readiness": from_readiness,
                "to_readiness": to_readiness,
                "from_status": from_status,
                "to_status": to_status,
                "snapshot_id": str(snapshot_id),
            },
        )
