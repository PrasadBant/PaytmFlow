import hashlib
import json
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import get_ai_provider
from app.audit.writer import AuditWriter
from app.core.diff import compute_diff
from app.core.models import (
    CoreFieldStatus,
    CoreReadiness,
    CoreSnapshot,
)
from app.core.rules import derive_field_states
from app.core.simulate import simulate
from app.db.models import JourneyModel, SessionModel
from app.db.repositories.evidence import EvidenceRepository
from app.db.repositories.journeys import JourneyRepository
from app.db.repositories.snapshots import SnapshotRepository
from app.docai.ocr import extract_text as docai_extract_text
from app.evidence.extract import parse_financial_patterns
from app.evidence.storage import (
    FileTooLargeError,
    InvalidFileFormatError,
    store_evidence_file,
)
from app.packs.registry import pack_registry
from app.schemas.enums import ErrorCode, FieldStatus, Readiness
from app.schemas.errors import ErrorEnvelope, ErrorObject
from app.schemas.evidence import (
    EvidenceConflict,
    EvidenceDetectedField,
    EvidenceInterpretation,
    EvidenceResponse,
)
from app.schemas.journeys import (
    FieldChange,
    JourneyDiff,
    NewlySatisfied,
    NewlyUnlocked,
    ProgressCounts,
    ProgressDiff,
    ReadinessDiff,
    SimulationPreview,
    StillBlocked,
)


class EvidenceReconciliationService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.journey_repo = JourneyRepository(session)
        self.snapshot_repo = SnapshotRepository(session)
        self.evidence_repo = EvidenceRepository(session)
        self.audit_writer = AuditWriter(session)
        self.ai_provider = get_ai_provider()

    async def submit_evidence(
        self,
        journey: JourneyModel,
        doc_type: str,
        expected_snapshot_id: UUID,
        current_session: SessionModel,
        file_bytes: bytes | None = None,
        filename: str | None = None,
        manual_fields_json: str | None = None,
    ) -> EvidenceResponse:
        """Processes an evidence submission (file upload or manual details entry),

        runs AI interpretation, detects conflicts, and computes deterministic preview.
        CRITICAL INVARIANT: Creates NO snapshot.
        """
        journey_id = journey.id

        # 1. Verify journey existence and session ownership (404 if not found or unowned)
        # NOTE: "NOT_FOUND" is intentionally not a member of the ErrorCode enum (see
        # contract/openapi.yaml's ErrorCode schema and app.schemas.enums.ErrorCode) -
        # 404s use a plain string code, exactly like security.session.verify_journey_ownership
        # already does, bypassing the strict ErrorObject(code: ErrorCode) model.
        if journey.session_id != current_session.id:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Journey '{journey_id}' not found",
                    }
                },
            )

        # 2. Check for stale action
        if journey.current_snapshot_id != expected_snapshot_id:
            raise HTTPException(
                status_code=409,
                detail=ErrorEnvelope(
                    error=ErrorObject(
                        code=ErrorCode.ACTION_STALE,
                        message=(
                            "The journey state has changed since this action was requested. "
                            "Please refresh."
                        ),
                        details={"current_snapshot_id": str(journey.current_snapshot_id)},
                    )
                ).model_dump(mode="json"),
            )

        # 3. Load snapshot model and convert to CoreSnapshot
        snapshot_model = await self.snapshot_repo.get_by_id(expected_snapshot_id)
        if not snapshot_model:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "NOT_FOUND", "message": "Snapshot not found"}},
            )

        manifest = pack_registry.get_pack(journey.journey_type)
        if not manifest:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"Journey pack '{journey.journey_type}' not found",
                    }
                },
            )

        current_values = {
            k: (v.get("value") if isinstance(v, dict) else getattr(v, "value", None))
            for k, v in snapshot_model.fields.items()
        }
        current_statuses = {
            k: CoreFieldStatus(
                (v.get("status") or "BLOCKED")
                if isinstance(v, dict)
                else getattr(v, "status", "BLOCKED")
            )
            for k, v in snapshot_model.fields.items()
        }
        derived_states, _ = derive_field_states(
            manifest=manifest,
            current_values=current_values,
            current_statuses=current_statuses,
            goal=snapshot_model.goal or journey.goal,
        )
        core_snapshot = CoreSnapshot(
            snapshot_id=snapshot_model.id,
            journey_id=journey.id,
            journey_type=journey.journey_type,
            version_number=snapshot_model.version_number,
            readiness=CoreReadiness(snapshot_model.readiness),
            fields=derived_states,
            goal=snapshot_model.goal or journey.goal,
        )

        # 4. Ingest and extract content
        extracted_text = ""
        extracted_data: dict[str, Any] = {}
        stored_file_path = ""
        sha256_hash = ""
        file_size = 0
        mime_type = ""
        final_filename = filename or "evidence_document"
        ocr_meta: dict[str, Any] | None = None

        if file_bytes is not None:
            try:
                # Validate and store file to disk
                stored_file_path, sha256_hash, file_size, mime_type = store_evidence_file(
                    journey_id=journey_id,
                    filename=final_filename,
                    content=file_bytes,
                )
            except FileTooLargeError as exc:
                raise HTTPException(
                    status_code=413,
                    detail=ErrorEnvelope(
                        error=ErrorObject(
                            code=ErrorCode.VALIDATION_ERROR,
                            message=str(exc),
                        )
                    ).model_dump(mode="json"),
                ) from exc
            except InvalidFileFormatError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=ErrorEnvelope(
                        error=ErrorObject(
                            code=ErrorCode.VALIDATION_ERROR,
                            message=str(exc),
                        )
                    ).model_dump(mode="json"),
                ) from exc

            # Real local extraction (app/docai/ocr.py): PyMuPDF's genuine
            # text layer for native-text PDFs, real Tesseract OCR for
            # images or scanned PDFs with no text layer - replaces the
            # previous placeholder ("Image document binary record
            # uploaded.") that images used to get. `ocr_meta` carries the
            # real, measured OCR confidence/line-layout signals through to
            # whichever AIProvider is configured (only LocalMLProvider
            # currently uses it; Mock/LLM accept and ignore it).
            ocr_result = docai_extract_text(file_bytes, mime_type)
            extracted_text = ocr_result.text
            extracted_data = parse_financial_patterns(extracted_text)
            ocr_meta = {
                "confidence": ocr_result.mean_word_confidence,
                "word_count": ocr_result.word_count,
                "engine": ocr_result.engine,
                "lines": [
                    {"text": ln.text, "top": ln.top, "bottom": ln.bottom} for ln in ocr_result.lines
                ],
            }

        elif manual_fields_json:
            try:
                manual_dict = json.loads(manual_fields_json)
                if not isinstance(manual_dict, dict):
                    raise ValueError("manual_fields must be a JSON object")
            except Exception as exc:
                raise HTTPException(
                    status_code=400,
                    detail=ErrorEnvelope(
                        error=ErrorObject(
                            code=ErrorCode.VALIDATION_ERROR,
                            message=f"Invalid manual_fields JSON payload: {exc}",
                        )
                    ).model_dump(mode="json"),
                ) from exc

            raw_bytes = manual_fields_json.encode("utf-8")
            sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
            file_size = len(raw_bytes)
            mime_type = "application/json"
            final_filename = "manual_entry.json"
            stored_file_path = f"manual://{journey_id}/{sha256_hash}.json"
            extracted_text = manual_fields_json
            extracted_data = manual_dict
        else:
            raise HTTPException(
                status_code=400,
                detail=ErrorEnvelope(
                    error=ErrorObject(
                        code=ErrorCode.VALIDATION_ERROR,
                        message="Either a file upload or manual_fields must be provided.",
                    )
                ).model_dump(mode="json"),
            )

        # 5. AI interpretation and reconciliation
        existing_values = {
            k: f.value for k, f in core_snapshot.fields.items() if f.value is not None
        }
        # Cross-document-consistency phase: also surface auxiliary facts
        # (name, and a doc_type-scoped identifier) recorded from this
        # journey's OWN prior evidence uploads - these are never
        # snapshot/state_schema fields (see app/ai/models.py's
        # `auxiliary_facts` docstring for why), so they live only in the
        # append-only `evidence.extracted_data` column, never in
        # immutable snapshot state. `list_by_journey_id` orders newest
        # first, so the first non-null value found per key is the most
        # recently recorded one.
        prior_evidence = await self.evidence_repo.list_by_journey_id(journey_id)
        for prior in prior_evidence:
            prior_data = prior.extracted_data or {}
            for key in ("name", f"identifier::{doc_type}"):
                if key not in existing_values and prior_data.get(key) is not None:
                    existing_values[key] = prior_data[key]

        ai_res = await self.ai_provider.reconcile_evidence(
            doc_type=doc_type,
            extracted_text=extracted_text,
            manifest=manifest,
            existing_fields=existing_values,
            ocr_meta=ocr_meta,
        )

        # 6. Verification & confidence threshold check against manifest mapping
        #
        # Human-first real-browser QA finding: an action can accept
        # MULTIPLE doc_types (e.g. Lending's UPLOAD_INCOME_PROOF: SALARY_
        # SLIP or BANK_STATEMENT, independently thresholded). The client
        # only ever declares ONE when uploading, so a genuinely correct
        # document of the OTHER accepted type was being scored against the
        # WRONG mapping's threshold (or, before the local_ml.py-side fix,
        # never even reached here at all - flagged WRONG_DOCUMENT first).
        # `ai_res.resolved_doc_type` (set only by LocalMLProvider, only on
        # a genuine CORRECT_DOCUMENT classification) is the document's
        # real, classifier-verified type; fall back to the client-declared
        # `doc_type` for MockAI/LLM (which never set it) - unchanged
        # behavior for both.
        effective_doc_type = ai_res.resolved_doc_type or doc_type
        # 6. Find proposed action matching this evidence doc_type
        proposed_action = next(
            (
                a
                for a in manifest.actions
                if a.accepts
                and any(acc.upper() == doc_type.upper() or acc == doc_type for acc in a.accepts)
            ),
            None,
        )
        proposed_action_id = proposed_action.action_id if proposed_action else None

        # 6b. Verification & confidence threshold check against manifest mapping
        mapping = next(
            (
                m
                for m in manifest.evidence_mappings
                if m.doc_type.upper() == effective_doc_type.upper()
                or m.doc_type == effective_doc_type
            ),
            None,
        )
        min_confidence = mapping.confidence_threshold if mapping else 0.80

        has_conflicts = len(ai_res.conflicts) > 0
        is_confidence_sufficient = ai_res.confidence >= min_confidence
        is_verified = ai_res.verified and is_confidence_sufficient and not has_conflicts
        
        # OVD OCR distinction (Error 15): OCR extracts identity/address data from
        # officially valid documents (Passport, Voter ID, Driving Licence), but OCR
        # recognition alone does NOT establish authenticity verification.
        # Authenticity requires manual review / official validation.
        is_ovd_doc = effective_doc_type in ["PASSPORT_SCAN", "VOTER_ID_CARD", "DRIVING_LICENCE"]
        if is_ovd_doc:
            is_verified = False

        requires_review = not is_verified or has_conflicts or is_ovd_doc
        evidence_is_genuine = ai_res.verified and not has_conflicts

        display_summary = ai_res.summary
        needs_confidence_review = (
            evidence_is_genuine
            and ai_res.detected
            and not is_confidence_sufficient
            and not has_conflicts
        )
        if is_ovd_doc and evidence_is_genuine and ai_res.detected:
            doc_name_clean = effective_doc_type.replace("_", " ").title()
            field_list = ", ".join(d.label for d in ai_res.detected)
            display_summary = (
                f"{doc_name_clean} recognized and {field_list} extracted. "
                "Document recognition alone does not establish official authenticity; "
                "this document will be forwarded for identity verification."
            )
        elif needs_confidence_review:
            doc_name_clean = effective_doc_type.replace("_", " ").title()
            field_list = ", ".join(d.label for d in ai_res.detected)
            display_summary = (
                f"{doc_name_clean} recognized and {field_list} extracted successfully. "
                "This document doesn't meet the confidence needed for automatic "
                "verification, so it will be sent for manual review instead of applied "
                "immediately - the extracted value itself is not in question."
            )
        elif not evidence_is_genuine or not ai_res.detected:
            # Recovery messaging (Error 3): truthful guidance based on actual action capabilities
            has_manual_schema = bool(
                proposed_action
                and proposed_action.input_schema
                and len(proposed_action.input_schema) > 0
            )
            other_accepted = (
                [
                    acc.replace("_", " ").title()
                    for acc in (proposed_action.accepts or [])
                    if acc.upper() != doc_type.upper()
                ]
                if proposed_action
                else []
            )

            if has_manual_schema:
                recovery_hint = (
                    "Please upload a clearer copy or use the Enter Details tab "
                    "to enter the information directly."
                )
            elif other_accepted:
                alt_docs = " or ".join(other_accepted)
                recovery_hint = (
                    f"Please upload a clearer copy, or provide an alternative "
                    f"accepted document such as {alt_docs}."
                )
            else:
                recovery_hint = (
                    "Please ensure the document is clear, uncropped, "
                    "and matches the requested document type."
                )

            display_summary = f"{ai_res.summary} {recovery_hint}".strip()

        # 7. Persist evidence record in database
        if ai_res.auxiliary_facts:
            extracted_data = {**extracted_data, **ai_res.auxiliary_facts}

        evidence_record = await self.evidence_repo.create(
            journey_id=journey_id,
            doc_type=doc_type,
            filename=final_filename,
            file_path=stored_file_path,
            sha256=sha256_hash,
            file_size_bytes=file_size,
            mime_type=mime_type,
            extracted_text=extracted_text[:4000] if extracted_text else None,
            extracted_data=extracted_data,
            confidence=ai_res.confidence,
            verified=evidence_is_genuine,
            raw_values=ai_res.raw_values,
        )

        # 8. Write EVIDENCE_UPLOADED audit event
        await self.audit_writer.record_evidence_uploaded(
            journey_id=journey_id,
            session_id=current_session.id,
            evidence_id=evidence_record.id,
            doc_type=doc_type,
            filename=final_filename,
            sha256=sha256_hash,
            confidence=ai_res.confidence,
            extracted_data=extracted_data,
        )
        await self.session.commit()

        # 10. Compute deterministic simulation preview and diff preview
        #
        # Real-user QA finding: this block used to run for ANY evidence whose
        # CLIENT-DECLARED doc_type matched some action's `accepts`, regardless
        # of whether the AI actually verified the uploaded document as that
        # doc_type. For a genuinely wrong document (verified=False,
        # raw_values={}), `simulate()` had no real extracted values to work
        # with and silently fell back to `manifest.simulation_defaults` -
        # producing a confident "this will satisfy monthly_income -> Rs.
        # 85,000, progress 5/7" preview directly alongside an AI summary
        # correctly saying the document was rejected. That preview is never
        # actually applied (only `deterministic_check()`, gated on the real
        # persisted `verified` result, can do that - see
        # app/core/deterministic_check.py), so no state was ever corrupted,
        # but it is a real, confirmed, misleading-preview defect: it must
        # only ever be computed for evidence the AI genuinely verified.
        # `proposed_action_id` itself is left untouched below - it is
        # correctly-scoped informational routing metadata ("this doc_type
        # would route to this action"), not a prediction of what will happen.
        consequence_preview: SimulationPreview | None = None
        diff_preview: JourneyDiff | None = None

        if proposed_action and is_verified:
            action_input: dict[str, Any] = {
                "evidence_id": str(evidence_record.id),
            }
            if ai_res.raw_values:
                action_input.update(ai_res.raw_values)
            for det in ai_res.detected:
                if det.value is not None:
                    action_input[det.key] = det.value

            try:
                sim_res = simulate(
                    action_id=proposed_action.action_id,
                    action_input=action_input,
                    snapshot=core_snapshot,
                    manifest=manifest,
                )

                consequence_preview = SimulationPreview(
                    newly_satisfied=[
                        NewlySatisfied(key=f.key, label=f.label) for f in sim_res.newly_satisfied
                    ],
                    newly_unlocked=[
                        NewlyUnlocked(action_id=a.action_id, title=a.title)
                        for a in sim_res.newly_unlocked
                    ],
                    still_blocked=[
                        StillBlocked(key=f.key, label=f.label) for f in sim_res.still_blocked
                    ],
                    predicted_readiness=Readiness(sim_res.predicted_readiness.value),
                    progress_before=ProgressCounts(
                        completed=sim_res.progress_before.completed,
                        pending=sim_res.progress_before.pending,
                        blockers=sim_res.progress_before.blockers,
                        total=sim_res.progress_before.total,
                    ),
                    progress_after=ProgressCounts(
                        completed=sim_res.progress_after.completed,
                        pending=sim_res.progress_after.pending,
                        blockers=sim_res.progress_after.blockers,
                        total=sim_res.progress_after.total,
                    ),
                )

                simulated_snapshot = CoreSnapshot(
                    snapshot_id=core_snapshot.snapshot_id,
                    journey_id=core_snapshot.journey_id,
                    journey_type=core_snapshot.journey_type,
                    version_number=core_snapshot.version_number + 1,
                    readiness=sim_res.predicted_readiness,
                    fields=sim_res.simulated_fields,
                    goal=core_snapshot.goal,
                )

                core_diff = compute_diff(
                    snapshot_a=core_snapshot,
                    snapshot_b=simulated_snapshot,
                    manifest=manifest,
                    direct_fields=proposed_action.satisfies,
                    cause=f"ACTION:{proposed_action.action_id}",
                )

                diff_preview = JourneyDiff(
                    from_version=core_diff.from_version,
                    to_version=core_diff.to_version,
                    fields_changed=[
                        FieldChange(
                            key=fc.key,
                            label=fc.label,
                            from_status=FieldStatus(fc.from_status.value),
                            to_status=FieldStatus(fc.to_status.value),
                            display_value=fc.display_value,
                            cause=fc.cause,
                            cascaded=fc.cascaded,
                        )
                        for fc in core_diff.fields_changed
                    ],
                    actions_unlocked=core_diff.actions_unlocked,
                    actions_removed=core_diff.actions_removed,
                    readiness=(
                        ReadinessDiff(
                            from_=(
                                Readiness(core_diff.readiness.from_readiness.value)
                                if core_diff.readiness.from_readiness
                                else None
                            ),
                            to=(
                                Readiness(core_diff.readiness.to_readiness.value)
                                if core_diff.readiness.to_readiness
                                else None
                            ),
                        )
                        if core_diff.readiness
                        else None
                    ),
                    progress=(
                        ProgressDiff(
                            from_=(
                                ProgressCounts(
                                    completed=core_diff.progress.from_progress.completed,
                                    pending=core_diff.progress.from_progress.pending,
                                    blockers=core_diff.progress.from_progress.blockers,
                                    total=core_diff.progress.from_progress.total,
                                )
                                if core_diff.progress and core_diff.progress.from_progress
                                else None
                            ),
                            to=(
                                ProgressCounts(
                                    completed=core_diff.progress.to_progress.completed,
                                    pending=core_diff.progress.to_progress.pending,
                                    blockers=core_diff.progress.to_progress.blockers,
                                    total=core_diff.progress.to_progress.total,
                                )
                                if core_diff.progress and core_diff.progress.to_progress
                                else None
                            ),
                        )
                        if core_diff.progress
                        else None
                    ),
                )
            except Exception:
                consequence_preview = None
                diff_preview = None

        # 11. Construct and return final EvidenceResponse
        return EvidenceResponse(
            evidence_id=evidence_record.id,
            filename=final_filename,
            uploaded_at=evidence_record.created_at,
            size_bytes=file_size,
            interpretation=EvidenceInterpretation(
                verified=is_verified,
                confidence=ai_res.confidence,
                detected=[
                    EvidenceDetectedField(
                        key=d.key,
                        label=d.label,
                        display_value=d.display_value,
                    )
                    for d in ai_res.detected
                ],
                summary=display_summary,
                conflicts=[
                    EvidenceConflict(
                        ambiguity_id=c.ambiguity_id,
                        field=c.field,
                        message=c.message,
                    )
                    for c in ai_res.conflicts
                ],
            ),
            proposed_action_id=proposed_action_id,
            consequence_preview=consequence_preview,
            diff_preview=diff_preview,
            requires_review=requires_review,
        )
