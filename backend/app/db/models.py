from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    journeys: Mapped[list["JourneyModel"]] = relationship(back_populates="session")


class JourneyModel(Base):
    __tablename__ = "journeys"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    journey_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    status: Mapped[str] = mapped_column(String(50), default="IN_PROGRESS", index=True)
    readiness: Mapped[str] = mapped_column(String(50), default="NOT_READY")
    current_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("journey_snapshots.id", use_alter=True, name="fk_journey_current_snapshot"),
        nullable=True,
    )
    goal: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    natural_language: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_title: Mapped[str] = mapped_column(String(200), default="")
    display_summary: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        index=True,
    )

    session: Mapped["SessionModel"] = relationship(back_populates="journeys")
    snapshots: Mapped[list["JourneySnapshotModel"]] = relationship(
        back_populates="journey",
        foreign_keys="JourneySnapshotModel.journey_id",
        order_by="JourneySnapshotModel.version_number",
    )
    evidence: Mapped[list["EvidenceModel"]] = relationship(back_populates="journey")
    audit_events: Mapped[list["AuditEventModel"]] = relationship(back_populates="journey")
    clarifications: Mapped[list["ClarificationModel"]] = relationship(back_populates="journey")

    __table_args__ = (
        Index("idx_journeys_session_updated", "session_id", "updated_at"),
        Index("idx_journeys_type_updated", "journey_type", "updated_at"),
        Index("idx_journeys_status_updated", "status", "updated_at"),
    )


class JourneySnapshotModel(Base):
    __tablename__ = "journey_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    journey_id: Mapped[UUID] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("journey_snapshots.id"), nullable=True
    )
    readiness: Mapped[str] = mapped_column(String(50), nullable=False)
    fields: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    goal: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    pending_clarification: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    journey: Mapped["JourneyModel"] = relationship(
        back_populates="snapshots", foreign_keys=[journey_id]
    )

    __table_args__ = (
        UniqueConstraint("journey_id", "version_number", name="uq_snapshots_journey_version"),
        UniqueConstraint(
            "journey_id", "previous_snapshot_id", name="uq_snapshots_journey_prev_snapshot"
        ),
        Index("idx_snapshots_journey_created", "journey_id", "created_at"),
    )


class EvidenceModel(Base):
    __tablename__ = "evidence"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    journey_id: Mapped[UUID] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(100), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Document AI integration integrity fix: whether the AI genuinely
    # recognized this as the expected document (correct classification)
    # with no detected conflict - `EvidenceReconciliationService.
    # submit_evidence`'s `evidence_is_genuine`, deliberately NOT the same
    # as that method's fuller `is_verified` (which also requires
    # confidence >= the manifest threshold - a separate, deliberately
    # unaddressed calibration concern; see reconcile.py's own comment).
    # Persisted so a LATER action-execution request can consume the real,
    # server-validated result instead of ever falling back to a
    # simulated/default value or trusting a client-supplied one. `False`
    # by default so a row somehow missing it never reads as verified.
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # The AI's real `raw_values` (manifest target-field key -> validated
    # value) at upload time - e.g. {"monthly_income": 92000} or
    # {"income_verified": True}. Never client-supplied; only ever written
    # from `AIInterpretationResult.raw_values`.
    raw_values: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    journey: Mapped["JourneyModel"] = relationship(back_populates="evidence")

    __table_args__ = (Index("idx_evidence_journey_created", "journey_id", "created_at"),)


class ClarificationModel(Base):
    __tablename__ = "clarifications"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    journey_id: Mapped[UUID] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ambiguity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    field_key: Mapped[str] = mapped_column(String(100), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_type: Mapped[str] = mapped_column(String(50), nullable=False)
    user_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    journey: Mapped["JourneyModel"] = relationship(back_populates="clarifications")


class IdempotencyKeyModel(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    journey_id: Mapped[UUID] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_id: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    journey_id: Mapped[UUID] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    journey: Mapped["JourneyModel"] = relationship(back_populates="audit_events")

    __table_args__ = (Index("idx_audit_events_journey_created", "journey_id", "created_at"),)


class ReviewCaseModel(Base):
    """A durable, queryable Human Review / Exception Resolution case.

    Created idempotently (unique on journey_id+dedupe_key) whenever the
    existing ambiguity mechanism forces a field AMBIGUOUS and the journey
    reaches NEEDS_REVIEW - see JourneyService.apply_action. Resolution
    re-enters the SAME deterministic mutation chain every other journey
    write uses (see ReviewCaseService), never a shortcut that writes
    journey state directly.
    """

    __tablename__ = "review_cases"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # Human-facing "PF-xxxx" sequence number. Assigned by the repository at
    # creation time via MAX(case_seq)+1 under the same row-lock discipline
    # used elsewhere in this module - NOT a DB-native sequence/identity, so
    # it is not distributed-safe under heavy concurrent case creation (an
    # acceptable, documented limitation for this prototype's scale).
    case_seq: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    journey_id: Mapped[UUID] = mapped_column(
        ForeignKey("journeys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    context_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("journey_snapshots.id"), nullable=True
    )
    field_key: Mapped[str] = mapped_column(String(100), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    reason_title: Mapped[str] = mapped_column(String(300), nullable=False)
    reason_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    priority: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    status: Mapped[str] = mapped_column(String(50), default="REVIEW_REQUIRED", index=True)
    case_version: Mapped[int] = mapped_column(Integer, default=1)
    assigned_reviewer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    review_lock_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_information: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    escalation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resulting_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("journey_snapshots.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        index=True,
    )

    journey: Mapped["JourneyModel"] = relationship()

    __table_args__ = (
        UniqueConstraint("journey_id", "dedupe_key", name="uq_review_case_journey_dedupe"),
        Index("idx_review_cases_status_created", "status", "created_at"),
        Index("idx_review_cases_journey", "journey_id"),
    )


class PackMetadataModel(Base):
    __tablename__ = "packs_metadata"

    journey_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str] = mapped_column(String(50), nullable=False)
    flagship_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    manifest_yaml: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
