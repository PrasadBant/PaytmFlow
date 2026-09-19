from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EvidenceModel


class EvidenceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, evidence_id: UUID) -> EvidenceModel | None:
        stmt = select(EvidenceModel).where(EvidenceModel.id == evidence_id)
        return await self.session.scalar(stmt)

    async def get_by_sha256(self, sha256: str) -> EvidenceModel | None:
        stmt = select(EvidenceModel).where(EvidenceModel.sha256 == sha256).limit(1)
        return await self.session.scalar(stmt)

    async def list_by_journey_id(self, journey_id: UUID) -> list[EvidenceModel]:
        stmt = (
            select(EvidenceModel)
            .where(EvidenceModel.journey_id == journey_id)
            .order_by(EvidenceModel.created_at.desc())
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def create(
        self,
        journey_id: UUID,
        doc_type: str,
        filename: str,
        file_path: str,
        sha256: str,
        file_size_bytes: int,
        mime_type: str,
        extracted_text: str | None = None,
        extracted_data: dict[str, Any] | None = None,
        confidence: float | None = None,
        evidence_id: UUID | None = None,
        verified: bool = False,
        raw_values: dict[str, Any] | None = None,
        provider: str | None = None,
    ) -> EvidenceModel:
        evidence = EvidenceModel(
            id=evidence_id or uuid4(),
            journey_id=journey_id,
            doc_type=doc_type,
            filename=filename,
            file_path=file_path,
            sha256=sha256,
            file_size_bytes=file_size_bytes,
            mime_type=mime_type,
            extracted_text=extracted_text,
            extracted_data=extracted_data,
            confidence=confidence,
            verified=verified,
            raw_values=raw_values,
            provider=provider,
            created_at=datetime.now(UTC),
        )
        self.session.add(evidence)
        await self.session.flush()
        return evidence
