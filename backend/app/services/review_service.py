"""Human Review / Exception Resolution orchestration.

Reuses the SAME deterministic mutation chain every other journey write goes
through (SnapshotRepository.create -> compute_diff -> AuditWriter) via
JourneyService.submit_clarification - a review case never writes journey
state directly. The only new pure decision logic is the review-case
status state machine in app/core/review.py.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import AuditWriter
from app.core.models import CoreAmbiguity, CoreFieldStatus, CoreReadiness, CoreSnapshot
from app.core.review import (
    ReviewCaseStatus as CoreReviewCaseStatus,
)
from app.core.review import (
    ReviewTransitionError,
    check_lock,
    validate_transition,
)
from app.core.rules import derive_field_states
from app.db.models import JourneyModel, ReviewCaseModel
from app.db.repositories.evidence import EvidenceRepository
from app.db.repositories.journeys import JourneyRepository
from app.db.repositories.review_cases import ReviewCaseRepository
from app.db.repositories.sessions import SessionRepository
from app.db.repositories.snapshots import SnapshotRepository
from app.packs.registry import pack_registry
from app.schemas.enums import ErrorCode, ReviewCaseStatus, ReviewResolutionType
from app.schemas.errors import ErrorEnvelope, ErrorObject
from app.schemas.review import (
    ClaimCaseRequest,
    CustomerReviewStatus,
    EscalateCaseRequest,
    RequestInformationRequest,
    ResolveCaseRequest,
    ReviewCase,
    ReviewCaseAuditEntry,
    ReviewCaseDetail,
    ReviewDashboardMetrics,
    ReviewEvidenceSummary,
)

_LOCK_DURATION_MINUTES = 15


def _not_found(message: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=ErrorEnvelope(
            error=ErrorObject(code=ErrorCode.NOT_FOUND, message=message)
        ).model_dump(mode="json"),
    )


def _stale(message: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=ErrorEnvelope(
            error=ErrorObject(code=ErrorCode.REVIEW_CASE_STALE, message=message)
        ).model_dump(mode="json"),
    )


def _locked(message: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=ErrorEnvelope(
            error=ErrorObject(code=ErrorCode.REVIEW_CASE_LOCKED, message=message)
        ).model_dump(mode="json"),
    )


def _invalid_transition(exc: ReviewTransitionError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=ErrorEnvelope(
            error=ErrorObject(code=ErrorCode.REVIEW_CASE_INVALID_TRANSITION, message=str(exc))
        ).model_dump(mode="json"),
    )


def _validation_error(message: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail=ErrorEnvelope(
            error=ErrorObject(code=ErrorCode.VALIDATION_ERROR, message=message)
        ).model_dump(mode="json"),
    )


def _to_utc(dt: datetime) -> datetime:
    """Normalize a datetime to UTC-aware, treating naive datetimes as UTC.

    SQLite returns naive datetimes even for DateTime(timezone=True), while
    PostgreSQL returns timezone-aware datetimes. This helper provides ONE
    consistent UTC representation across both database drivers.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _is_locked_future(case: ReviewCaseModel, now: datetime) -> bool:
    if not case.review_lock_until:
        return False
    return _to_utc(case.review_lock_until) > _to_utc(now)


def _case_number(case: ReviewCaseModel) -> str:
    return f"PF-{case.case_seq:04d}"


class ReviewCaseService:
    @staticmethod
    async def _to_review_case(db: AsyncSession, case: ReviewCaseModel) -> ReviewCase:
        journey = await JourneyRepository(db).get_by_id(case.journey_id)
        manifest = pack_registry.get_pack(journey.journey_type) if journey else None
        now = datetime.now(UTC)
        return ReviewCase(
            case_id=case.id,
            case_number=_case_number(case),
            journey_id=case.journey_id,
            journey_type=journey.journey_type if journey else "LENDING",  # type: ignore[arg-type]
            journey_display_name=(
                manifest.metadata.display_name
                if manifest
                else (journey.journey_type if journey else "")
            ),
            field_key=case.field_key,
            reason_code=case.reason_code,
            reason_title=case.reason_title,
            reason_description=case.reason_description,
            priority=case.priority,  # type: ignore[arg-type]
            status=case.status,  # type: ignore[arg-type]
            case_version=case.case_version,
            assigned_reviewer=case.assigned_reviewer,
            is_locked=_is_locked_future(case, now),
            resolution_type=case.resolution_type,  # type: ignore[arg-type]
            resolution_reason=case.resolution_reason,
            resolution_notes=case.resolution_notes,
            requested_information=case.requested_information,
            escalation_reason=case.escalation_reason,
            created_at=case.created_at,
            updated_at=case.updated_at,
            resolved_at=case.resolved_at,
        )

    @classmethod
    async def create_or_get_open_case(
        cls,
        db: AsyncSession,
        journey: JourneyModel,
        ambiguity: CoreAmbiguity,
        context_snapshot_id: UUID | None,
    ) -> ReviewCaseModel:
        """Idempotent: reuses the existing OPEN case for this (journey,
        ambiguity) pair rather than creating a duplicate while one is still
        actionable. Once a case reaches a terminal status (RESOLVED/
        CANCELLED), a later genuinely-new occurrence of the same ambiguity
        (e.g. the customer edits and resubmits after resolution) gets its
        own fresh, attempt-numbered case rather than being silently
        swallowed by the dedupe key - `uq_review_case_journey_dedupe` still
        guarantees each exact dedupe_key is unique."""
        repo = ReviewCaseRepository(db)
        base_key = f"{ambiguity.ambiguity_id}:{ambiguity.field}"
        existing = await repo.find_open_by_base_key(journey.id, base_key)
        if existing:
            if existing.status == ReviewCaseStatus.ADDITIONAL_INFO_REQUIRED.value:
                new_status = (
                    ReviewCaseStatus.UNDER_REVIEW.value
                    if existing.assigned_reviewer
                    else ReviewCaseStatus.REVIEW_REQUIRED.value
                )
                existing = await repo.save(
                    existing,
                    status=new_status,
                    case_version=existing.case_version + 1,
                )
                await AuditWriter(db).record_review_case_reopened(
                    journey_id=journey.id,
                    session_id=journey.session_id,
                    case_id=existing.id,
                )
                await db.commit()
            return existing

        attempt = await repo.count_by_base_key(journey.id, base_key) + 1
        dedupe_key = f"{base_key}:{attempt}"
        case = await repo.create(
            journey_id=journey.id,
            session_id=journey.session_id,
            dedupe_key=dedupe_key,
            field_key=ambiguity.field,
            reason_code=ambiguity.ambiguity_id,
            reason_title=ambiguity.reason,
            reason_description=ambiguity.question,
            context_snapshot_id=context_snapshot_id,
            priority="MEDIUM",
        )
        await AuditWriter(db).record_review_case_created(
            journey_id=journey.id,
            session_id=journey.session_id,
            case_id=case.id,
            reason_code=ambiguity.ambiguity_id,
            field_key=ambiguity.field,
        )
        return case

    @classmethod
    async def list_queue(
        cls,
        db: AsyncSession,
        status: str | None = None,
        priority: str | None = None,
        journey_type: str | None = None,
        assigned_to_me: str | None = None,
    ) -> list[ReviewCase]:
        repo = ReviewCaseRepository(db)
        cases = await repo.list_queue(
            status=status,
            priority=priority,
            journey_type=journey_type,
            assigned_reviewer=assigned_to_me,
        )
        return [await cls._to_review_case(db, c) for c in cases]

    @classmethod
    async def get_dashboard_metrics(cls, db: AsyncSession) -> ReviewDashboardMetrics:
        repo = ReviewCaseRepository(db)
        counts = await repo.count_by_status()
        resolved_today = await repo.count_resolved_today()
        return ReviewDashboardMetrics(
            pending_review=counts.get("REVIEW_REQUIRED", 0),
            under_review=counts.get("UNDER_REVIEW", 0),
            waiting_customer=counts.get("ADDITIONAL_INFO_REQUIRED", 0),
            escalated=counts.get("ESCALATED", 0),
            resolved_today=resolved_today,
        )

    @classmethod
    async def get_case_detail(cls, db: AsyncSession, case_id: UUID) -> ReviewCaseDetail:
        case = await ReviewCaseRepository(db).get_by_id(case_id)
        if not case:
            raise _not_found(f"Review case '{case_id}' not found")

        journey = await JourneyRepository(db).get_by_id(case.journey_id)
        if not journey:
            raise _not_found(f"Journey for review case '{case_id}' not found")

        from app.services.journey_service import JourneyService

        journey_context = await JourneyService.get_journey_state(journey=journey, db=db)
        base = await cls._to_review_case(db, case)

        evidence_rows = await EvidenceRepository(db).list_by_journey_id(case.journey_id)
        manifest = pack_registry.get_pack(journey.journey_type)
        accepted_doc_types: set[str] = set()
        if manifest:
            for mapping in manifest.evidence_mappings or []:
                if mapping.target_field == case.field_key:
                    accepted_doc_types.add(mapping.doc_type.upper())
        relevant_evidence = [
            e
            for e in evidence_rows
            if not accepted_doc_types or e.doc_type.upper() in accepted_doc_types
        ]
        evidence_summaries = [
            ReviewEvidenceSummary(
                evidence_id=e.id,
                doc_type=e.doc_type,
                filename=e.filename,
                uploaded_at=e.created_at,
                verified=bool(e.verified),
                confidence=e.confidence,
                extracted_values=dict(e.raw_values or {}),
            )
            for e in relevant_evidence[:5]
        ]

        impact_preview = None
        if case.status in ("REVIEW_REQUIRED", "UNDER_REVIEW") and manifest:
            impact_preview = await cls._compute_impact_preview(
                db, journey, manifest, case.field_key, relevant_evidence
            )

        return ReviewCaseDetail(
            **base.model_dump(),
            journey_context=journey_context,
            evidence=evidence_summaries,
            impact_preview=impact_preview,
        )

    @staticmethod
    async def _compute_impact_preview(
        db: AsyncSession,
        journey: JourneyModel,
        manifest: Any,
        field_key: str,
        relevant_evidence: list[Any],
    ) -> Any | None:
        """Pure, non-persisting preview of what resolving EVIDENCE_SUFFICIENT
        would change - built from the SAME derive_field_states/evaluate_readiness/
        compute_diff functions the real mutation uses, just never written to a
        snapshot. Returns None when there's no evidence-derived value to preview."""
        candidate_value = None
        for e in relevant_evidence:
            if e.raw_values and field_key in e.raw_values:
                candidate_value = e.raw_values[field_key]
                break
        if candidate_value is None:
            return None

        from app.core.diff import compute_diff
        from app.core.readiness import evaluate_readiness
        from app.schemas.enums import FieldStatus, Readiness
        from app.schemas.journeys import (
            FieldChange,
            JourneyDiff,
            ProgressCounts,
            ProgressDiff,
            ReadinessDiff,
        )

        snapshot_repo = SnapshotRepository(db)
        curr_snap = (
            await snapshot_repo.get_by_id(journey.current_snapshot_id)
            if journey.current_snapshot_id
            else None
        )
        if not curr_snap:
            return None

        prev_values = {
            k: (v.get("value") if isinstance(v, dict) else None)
            for k, v in curr_snap.fields.items()
        }
        prev_statuses = {
            k: CoreFieldStatus((v.get("status") or "BLOCKED") if isinstance(v, dict) else "BLOCKED")
            for k, v in curr_snap.fields.items()
        }
        derived_a, _ = derive_field_states(
            manifest=manifest,
            current_values=prev_values,
            current_statuses=prev_statuses,
            goal=curr_snap.goal or journey.goal,
        )
        snap_a = CoreSnapshot(
            snapshot_id=curr_snap.id,
            journey_id=journey.id,
            journey_type=journey.journey_type,
            version_number=curr_snap.version_number,
            readiness=CoreReadiness(curr_snap.readiness),
            fields=derived_a,
            goal=curr_snap.goal or journey.goal,
        )

        new_values = {**prev_values, field_key: candidate_value}
        new_statuses = {**prev_statuses, field_key: CoreFieldStatus.SATISFIED}
        derived_b, _ = derive_field_states(
            manifest=manifest,
            current_values=new_values,
            current_statuses=new_statuses,
            goal=curr_snap.goal or journey.goal,
        )
        new_readiness = evaluate_readiness(
            manifest=manifest, field_states=derived_b, goal=curr_snap.goal or journey.goal
        )
        snap_b = CoreSnapshot(
            snapshot_id=curr_snap.id,
            journey_id=journey.id,
            journey_type=journey.journey_type,
            version_number=curr_snap.version_number + 1,
            readiness=new_readiness,
            fields=derived_b,
            goal=curr_snap.goal or journey.goal,
        )
        core_diff = compute_diff(
            snapshot_a=snap_a,
            snapshot_b=snap_b,
            manifest=manifest,
            direct_fields=[field_key],
            cause="REVIEW_PREVIEW",
        )

        def _fs(v: Any) -> FieldStatus:
            return FieldStatus(v.value if hasattr(v, "value") else str(v))

        return JourneyDiff(
            from_version=core_diff.from_version,
            to_version=core_diff.to_version,
            fields_changed=[
                FieldChange(
                    key=c.key,
                    label=c.label,
                    from_status=_fs(c.from_status),
                    to_status=_fs(c.to_status),
                    display_value=c.display_value,
                    cause=c.cause,
                    cascaded=c.cascaded,
                )
                for c in core_diff.fields_changed
            ],
            actions_unlocked=core_diff.actions_unlocked,
            actions_removed=core_diff.actions_removed,
            readiness=(
                ReadinessDiff(
                    from_=Readiness(core_diff.readiness.from_readiness.value)
                    if core_diff.readiness.from_readiness
                    else None,
                    to=Readiness(core_diff.readiness.to_readiness.value)
                    if core_diff.readiness.to_readiness
                    else None,
                )
                if core_diff.readiness
                else None
            ),
            progress=(
                ProgressDiff(
                    from_=ProgressCounts(**core_diff.progress.from_progress.__dict__)
                    if core_diff.progress.from_progress
                    else None,
                    to=ProgressCounts(**core_diff.progress.to_progress.__dict__)
                    if core_diff.progress.to_progress
                    else None,
                )
                if core_diff.progress
                else None
            ),
        )

    @classmethod
    async def claim_case(
        cls, db: AsyncSession, case_id: UUID, reviewer_name: str, _req: ClaimCaseRequest
    ) -> ReviewCase:
        repo = ReviewCaseRepository(db)
        case = await repo.get_by_id_for_update(case_id)
        if not case:
            raise _not_found(f"Review case '{case_id}' not found")

        now = datetime.now(UTC)
        lock = check_lock(_is_locked_future(case, now), case.assigned_reviewer, reviewer_name)
        if lock.locked_by_other:
            raise _locked("This case is currently being reviewed by another reviewer.")

        current = CoreReviewCaseStatus(case.status)
        if current == CoreReviewCaseStatus.UNDER_REVIEW and case.assigned_reviewer == reviewer_name:
            return await cls._to_review_case(db, case)

        try:
            validate_transition(current, CoreReviewCaseStatus.UNDER_REVIEW)
        except ReviewTransitionError as exc:
            raise _invalid_transition(exc) from exc

        updated = await repo.save(
            case,
            status=ReviewCaseStatus.UNDER_REVIEW.value,
            assigned_reviewer=reviewer_name,
            review_lock_until=now + timedelta(minutes=_LOCK_DURATION_MINUTES),
            case_version=case.case_version + 1,
        )
        await AuditWriter(db).record_review_case_claimed(
            journey_id=case.journey_id,
            session_id=case.session_id,
            case_id=case.id,
            reviewer=reviewer_name,
        )
        await db.commit()
        return await cls._to_review_case(db, updated)

    @classmethod
    async def resolve_case(
        cls, db: AsyncSession, case_id: UUID, reviewer_name: str, req: ResolveCaseRequest
    ) -> ReviewCaseDetail:
        repo = ReviewCaseRepository(db)
        case = await repo.get_by_id_for_update(case_id)
        if not case:
            raise _not_found(f"Review case '{case_id}' not found")
        if case.case_version != req.expected_case_version:
            raise _stale(
                "This case changed while you were reviewing it. Refresh before submitting."
            )

        now = datetime.now(UTC)
        lock = check_lock(_is_locked_future(case, now), case.assigned_reviewer, reviewer_name)
        if lock.locked_by_other:
            raise _locked("This case is currently being reviewed by another reviewer.")

        current = CoreReviewCaseStatus(case.status)
        try:
            validate_transition(current, CoreReviewCaseStatus.RESOLVED)
        except ReviewTransitionError as exc:
            raise _invalid_transition(exc) from exc

        if not req.resolution_reason.strip():
            raise _validation_error("resolution_reason is required")

        resulting_snapshot_id = None
        if req.resolution_type == ReviewResolutionType.EVIDENCE_SUFFICIENT:
            if req.resolution_value is None:
                raise _validation_error("resolution_value is required for EVIDENCE_SUFFICIENT")

            journey = await JourneyRepository(db).get_by_id(case.journey_id)
            if not journey:
                raise _not_found(f"Journey for review case '{case_id}' not found")
            session_obj = await SessionRepository(db).get_by_id(journey.session_id)
            if not session_obj:
                raise _not_found("Journey owner session not found")

            from app.services.journey_service import JourneyService

            # Re-enters the EXACT same single-field mutation chain a customer's
            # own clarification answer uses (deterministic_check-equivalent
            # stale check, row lock, SnapshotRepository.create, compute_diff,
            # audit) - the review case is never a shortcut around it.
            await JourneyService.submit_clarification(
                journey=journey,
                session=session_obj,
                ambiguity_id=case.reason_code,
                field=case.field_key,
                answer=req.resolution_value,
                expected_snapshot_id=journey.current_snapshot_id,  # type: ignore[arg-type]
                db=db,
            )
            journey = await JourneyRepository(db).get_by_id(case.journey_id)
            resulting_snapshot_id = journey.current_snapshot_id if journey else None

        updated = await repo.save(
            case,
            status=ReviewCaseStatus.RESOLVED.value,
            resolution_type=req.resolution_type.value,
            resolution_reason=req.resolution_reason,
            resolution_notes=req.resolution_notes,
            resolved_at=now,
            case_version=case.case_version + 1,
            resulting_snapshot_id=resulting_snapshot_id,
        )
        await AuditWriter(db).record_review_case_resolved(
            journey_id=case.journey_id,
            session_id=case.session_id,
            case_id=case.id,
            reviewer=reviewer_name,
            resolution_type=req.resolution_type.value,
            resolution_reason=req.resolution_reason,
        )
        await db.commit()
        return await cls.get_case_detail(db, updated.id)

    @classmethod
    async def request_information(
        cls, db: AsyncSession, case_id: UUID, reviewer_name: str, req: RequestInformationRequest
    ) -> ReviewCase:
        repo = ReviewCaseRepository(db)
        case = await repo.get_by_id_for_update(case_id)
        if not case:
            raise _not_found(f"Review case '{case_id}' not found")
        if case.case_version != req.expected_case_version:
            raise _stale(
                "This case changed while you were reviewing it. Refresh before submitting."
            )

        now = datetime.now(UTC)
        lock = check_lock(_is_locked_future(case, now), case.assigned_reviewer, reviewer_name)
        if lock.locked_by_other:
            raise _locked("This case is currently being reviewed by another reviewer.")

        current = CoreReviewCaseStatus(case.status)
        try:
            validate_transition(current, CoreReviewCaseStatus.ADDITIONAL_INFO_REQUIRED)
        except ReviewTransitionError as exc:
            raise _invalid_transition(exc) from exc

        if not req.requested_docs:
            raise _validation_error("requested_docs must not be empty")
        if not req.customer_message.strip():
            raise _validation_error("customer_message is required")

        updated = await repo.save(
            case,
            status=ReviewCaseStatus.ADDITIONAL_INFO_REQUIRED.value,
            requested_information={
                "requested_docs": req.requested_docs,
                "customer_message": req.customer_message,
            },
            case_version=case.case_version + 1,
        )
        await AuditWriter(db).record_review_case_info_requested(
            journey_id=case.journey_id,
            session_id=case.session_id,
            case_id=case.id,
            reviewer=reviewer_name,
            requested_docs=req.requested_docs,
            customer_message=req.customer_message,
        )
        await db.commit()
        return await cls._to_review_case(db, updated)

    @classmethod
    async def escalate_case(
        cls, db: AsyncSession, case_id: UUID, reviewer_name: str, req: EscalateCaseRequest
    ) -> ReviewCase:
        repo = ReviewCaseRepository(db)
        case = await repo.get_by_id_for_update(case_id)
        if not case:
            raise _not_found(f"Review case '{case_id}' not found")
        if case.case_version != req.expected_case_version:
            raise _stale(
                "This case changed while you were reviewing it. Refresh before submitting."
            )

        now = datetime.now(UTC)
        lock = check_lock(_is_locked_future(case, now), case.assigned_reviewer, reviewer_name)
        if lock.locked_by_other:
            raise _locked("This case is currently being reviewed by another reviewer.")

        current = CoreReviewCaseStatus(case.status)
        try:
            validate_transition(current, CoreReviewCaseStatus.ESCALATED)
        except ReviewTransitionError as exc:
            raise _invalid_transition(exc) from exc
        if not req.escalation_reason.strip():
            raise _validation_error("escalation_reason is required")

        updated = await repo.save(
            case,
            status=ReviewCaseStatus.ESCALATED.value,
            escalation_reason=req.escalation_reason,
            case_version=case.case_version + 1,
        )
        await AuditWriter(db).record_review_case_escalated(
            journey_id=case.journey_id,
            session_id=case.session_id,
            case_id=case.id,
            reviewer=reviewer_name,
            escalation_reason=req.escalation_reason,
        )
        await db.commit()
        return await cls._to_review_case(db, updated)

    @classmethod
    async def get_audit_trail(cls, db: AsyncSession, case_id: UUID) -> list[ReviewCaseAuditEntry]:
        from app.db.repositories.audit import AuditRepository

        case = await ReviewCaseRepository(db).get_by_id(case_id)
        if not case:
            raise _not_found(f"Review case '{case_id}' not found")
        events = await AuditRepository(db).list_by_journey_id(case.journey_id)
        return [
            ReviewCaseAuditEntry(
                event_type=e.event_type, payload=e.payload, created_at=e.created_at
            )
            for e in events
        ]

    @classmethod
    async def get_customer_review_status(
        cls, db: AsyncSession, journey_id: UUID
    ) -> CustomerReviewStatus:
        cases = await ReviewCaseRepository(db).list_by_journey(journey_id)
        open_cases = [c for c in cases if c.status not in ("RESOLVED", "CANCELLED")]
        if not open_cases:
            return CustomerReviewStatus(has_open_case=False)
        case = open_cases[0]
        return CustomerReviewStatus(
            has_open_case=True,
            case_number=_case_number(case),
            status=case.status,  # type: ignore[arg-type]
            title="Additional verification required",
            description=(
                "We found information that needs a quick manual review before you can continue."
            ),
            requested_information=case.requested_information,
            updated_at=case.updated_at,
        )
