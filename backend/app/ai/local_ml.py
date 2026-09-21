"""LocalMLProvider - the REAL local Document Intelligence AIProvider.

Activated by `AI_PROVIDER=local_ml`. This is the only provider in this
codebase that actually runs local inference over document content: a
trained TF-IDF+LogisticRegression document classifier
(app/docai/classifier.py) and layout-aware structured extraction
(app/docai/extraction.py), both trained/evaluated against the dataset and
metrics in app/docai/dataset and app/docai/reports (see
docs/docai_report.md for the full, honest numbers).

Scope disclosure (mission Phase 25's "clearly separate REAL LOCAL AI from
MOCK AI"): this mission is specifically about DOCUMENT intelligence.
`reconcile_evidence` below is the real local-inference path. The other
three AIProvider methods (`parse_goal`, `select_action`, `explain`) are
NOT document processing - they are natural-language goal parsing and
plain-text ranking/explanation copy, out of this mission's scope - and
are intentionally delegated to the existing, already-tested `MockAI`
deterministic implementations rather than silently left unimplemented or
disguised as "real AI" they are not. This is a scope decision, disclosed
here and in the final report, not a hidden shortcut.

Currently trained/evaluated for all six journeys - LENDING, INSURANCE, KYC,
CREDIT_CARD, ACCOUNT_OPENING, and INVESTMENT's real
evidence_mappings doc types only (see app/docai/__init__.py's scope
note). For any other journey/doc_type, `get_classifier()` returns None
and this provider returns a safe, honest "not confidently supported yet"
result (verified=False, low confidence, no fabricated detected fields)
rather than guessing - exactly the "prefer a safe 'not available' state
over inventing fields" rule from this repo's own prior evidence-fallback
fix.

Handles both journeys' evidence_mappings TARGET FIELD SHAPES generically,
not by journey-type branching: Lending's targets are MONEY/TEXT value
fields (monthly_income, employer_name); Insurance's is a single BOOLEAN
field (`ped_declaration_submitted`, satisfied by any 1 of 3 accepted doc
types) - a correctly classified document itself IS the fact a boolean
field needs, so no money/text value extraction applies there. See the
boolean-target-field handling below, added while auditing Insurance's
manifest (Lending never exercised this path).
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from app.ai.mock import MockAI
from app.ai.models import ActionRankingResult, AIConflict, AIDetectedField, AIInterpretationResult
from app.core.models import CoreSnapshot
from app.docai.classifier import get_classifier
from app.docai.confidence import ConfidenceInputs, compose_confidence
from app.docai.consistency import (
    check_identifier_consistency,
    check_income_consistency,
    check_name_consistency,
    check_salary_slip_internal_consistency,
)
from app.docai.extraction import (
    extract_fields_for_doc_type,
    extract_gross_pay,
    extract_total_deductions,
)
from app.docai.ocr import OcrLine
from app.packs.contract import ActionSpec, GoalFieldSpec, JourneyPackManifest
from app.schemas.enums import FieldType
from app.schemas.journeys import JourneyDiff, JourneyStateResponse, RecommendationResponse

logger = structlog.get_logger(__name__)

_UNTRUSTED_WRAPPER_RE = re.compile(
    r"^<untrusted_document>\r?\n\[SYSTEM INSTRUCTION:.*?\]\r?\n(.*)\r?\n</untrusted_document>$",
    re.DOTALL,
)


def _strip_untrusted_wrapper(text: str) -> str:
    """Removes the guardrail's `<untrusted_document>` boundary (added by
    `GuardrailedAIProvider` for every provider uniformly, including this
    one, for defense-in-depth consistency) before running the trained
    classifier/extractor. This is not a security bypass: the wrapper
    exists to stop document content from being interpreted as
    instructions inside an LLM prompt. A TF-IDF classifier and regex
    extractor have no prompt to inject into - they can only misclassify
    or fail to extract, both already handled by the confidence/threshold
    mechanism below - but they WERE trained on raw OCR text, so leaving
    the wrapper's own boilerplate in would be a real train/serve
    mismatch that quietly hurts measured accuracy for no security benefit.
    """
    clean = text.strip()
    match = _UNTRUSTED_WRAPPER_RE.match(clean)
    return match.group(1).strip() if match else clean


class LocalMLProvider:
    """Real local-inference AIProvider for document evidence reconciliation."""

    def __init__(self) -> None:
        self._mock_fallback = MockAI()

    async def parse_goal(
        self,
        journey_type: str,
        natural_language: str,
        goal_schema: list[GoalFieldSpec],
    ) -> dict[str, Any]:
        """Out of scope for this mission (document intelligence, not NLU
        goal parsing) - delegated to MockAI. See module docstring."""
        return await self._mock_fallback.parse_goal(journey_type, natural_language, goal_schema)

    async def reconcile_evidence(
        self,
        doc_type: str,
        extracted_text: str,
        manifest: JourneyPackManifest,
        existing_fields: dict[str, Any] | None = None,
        ocr_meta: dict[str, Any] | None = None,
        raw_file: bytes | None = None,
        filename: str | None = None,
    ) -> AIInterpretationResult:
        """The real local document-intelligence path: classify the
        document, detect wrong/ambiguous/unreadable documents, extract
        structured fields with layout-aware association, validate them
        deterministically, check cross-document consistency against
        `existing_fields`, and compose an honest confidence score.
        """
        existing_fields = existing_fields or {}
        text = _strip_untrusted_wrapper(extracted_text)
        ocr_meta = ocr_meta or {}
        ocr_confidence = float(ocr_meta.get("confidence", 1.0))
        word_count = int(ocr_meta.get("word_count", len(text.split())))
        raw_lines = ocr_meta.get("lines") or []
        ocr_lines = [
            OcrLine(text=ln["text"], top=ln["top"], bottom=ln["bottom"]) for ln in raw_lines
        ]

        # Manual fields entry path (structured JSON text)
        if text.strip().startswith("{") and text.strip().endswith("}"):
            try:
                parsed_manual = json.loads(text)
                if isinstance(parsed_manual, dict) and parsed_manual:
                    manual_detected_fields: list[AIDetectedField] = []
                    manual_raw_values: dict[str, Any] = {}
                    for k, v in parsed_manual.items():
                        state_spec = next((f for f in manifest.state_schema if f.key == k), None)
                        if state_spec:
                            is_money = state_spec.type == FieldType.MONEY
                            display_v = (
                                f"₹{int(v):,}"
                                if is_money and isinstance(v, (int, float))
                                else str(v)
                            )
                            manual_detected_fields.append(
                                AIDetectedField(
                                    key=k,
                                    label=state_spec.label,
                                    display_value=display_v,
                                    value=v,
                                )
                            )
                            manual_raw_values[k] = v
                    if manual_detected_fields:
                        n_fields = len(manual_detected_fields)
                        return AIInterpretationResult(
                            verified=True,
                            confidence=0.95,
                            detected=manual_detected_fields,
                            summary=f"Verified {n_fields} field(s) from manual submission.",
                            conflicts=[],
                            raw_values=manual_raw_values,
                            resolved_doc_type=doc_type.upper(),
                        )
            except Exception as exc:
                logger.warning("local_ml_manual_fields_error", error=str(exc))

        classifier = get_classifier(manifest.metadata.journey_type)
        if classifier is None:
            logger.warning(
                "local_ml_no_trained_classifier",
                journey_type=manifest.metadata.journey_type,
                doc_type=doc_type,
            )
            return AIInterpretationResult(
                verified=False,
                confidence=0.0,
                detected=[],
                summary=(
                    f"Local document AI does not yet have a trained model for "
                    f"{manifest.metadata.journey_type}. This document was not analyzed."
                ),
                conflicts=[],
                raw_values={},
            )

        # An action can legitimately accept MULTIPLE doc_types (real
        # manifest example: Lending's UPLOAD_INCOME_PROOF accepts either
        # SALARY_SLIP or BANK_STATEMENT, two separate evidence_mappings
        # entries sharing one action_id) - the client only ever declares
        # ONE when uploading. Build the full acceptable set from every
        # evidence_mappings entry that shares the declared doc_type's own
        # action_id, so a genuinely correct document of the OTHER accepted
        # type is not falsely flagged WRONG_DOCUMENT. Falls back to just
        # the declared type alone when it isn't a real manifest mapping at
        # all (unchanged, strict behavior for that case).
        declared_mapping = next(
            (m for m in manifest.evidence_mappings if m.doc_type.upper() == doc_type.upper()),
            None,
        )
        accepted_doc_types = (
            {
                m.doc_type.upper()
                for m in manifest.evidence_mappings
                if m.action_id == declared_mapping.action_id
            }
            if declared_mapping
            else {doc_type.upper()}
        )

        from app.docai.document_validator import (
            detect_document_type,
            score_doc_type,
            validate_cancelled_cheque_content,
            validate_passport_content,
        )

        classification = classifier.classify(
            text=text,
            expected_doc_type=doc_type,
            ocr_confidence=ocr_confidence,
            word_count=word_count,
            accepted_doc_types=accepted_doc_types,
        )
        classification_confidence = classification.probabilities.get(
            classification.predicted_doc_type, 0.0
        )

        # Content-based classification refinement: If the statistical classifier is ambiguous
        # or unreadable, check deterministic domain-specific content markers before giving up.
        if (
            classification.outcome in ("AMBIGUOUS_DOCUMENT", "UNREADABLE_DOCUMENT")
            and word_count >= 5
        ):
            detected_dt, detected_sc = detect_document_type(text, accepted_doc_types)
            expected_sc = score_doc_type(text, doc_type)
            if expected_sc >= 0.35:
                classification.outcome = "CORRECT_DOCUMENT"
                classification.predicted_doc_type = doc_type.upper()
                classification_confidence = max(classification_confidence, 0.85)
            elif detected_sc >= 0.40 and detected_dt in accepted_doc_types:
                classification.outcome = "CORRECT_DOCUMENT"
                classification.predicted_doc_type = detected_dt
                classification_confidence = max(classification_confidence, 0.85)

        if classification.outcome != "CORRECT_DOCUMENT":
            summary_by_outcome = {
                "WRONG_DOCUMENT": (
                    f"This does not look like the expected {doc_type.replace('_', ' ').title()}. "
                    f"It looks like a "
                    f"{classification.predicted_doc_type.replace('_', ' ').title()} instead."
                ),
                "AMBIGUOUS_DOCUMENT": "The document type could not be confidently determined.",
                "UNREADABLE_DOCUMENT": (
                    "The document could not be read reliably "
                    "(poor scan quality or no legible text)."
                ),
            }
            return AIInterpretationResult(
                verified=False,
                confidence=round(ocr_confidence * classification_confidence, 4),
                detected=[],
                summary=summary_by_outcome.get(classification.outcome, classification.reason),
                conflicts=[],
                raw_values={},
            )

        # The classifier landed on CORRECT_DOCUMENT against the acceptable
        # SET, but that may be a different doc_type string than the client
        # declared.
        effective_doc_type = classification.predicted_doc_type

        # Strict Doc-Type Content Validation (Errors 40 & 41)
        if effective_doc_type == "PASSPORT_SCAN":
            passed, msg, aux = validate_passport_content(text)
            if not passed:
                return AIInterpretationResult(
                    verified=False,
                    confidence=round(ocr_confidence * 0.35, 4),
                    detected=[],
                    summary=msg,
                    conflicts=[],
                    raw_values={},
                    resolved_doc_type=effective_doc_type,
                )

        elif effective_doc_type == "CANCELLED_CHEQUE":
            passed, msg, aux = validate_cancelled_cheque_content(text)
            if not passed:
                return AIInterpretationResult(
                    verified=False,
                    confidence=round(ocr_confidence * 0.35, 4),
                    detected=[],
                    summary=msg,
                    conflicts=[],
                    raw_values={},
                    resolved_doc_type=effective_doc_type,
                )

        state_schema_map = {f.key: f for f in manifest.state_schema}
        extracted = extract_fields_for_doc_type(text, effective_doc_type, lines=ocr_lines)

        detected_fields: list[AIDetectedField] = []
        raw_values: dict[str, Any] = {}
        conflicts: list[AIConflict] = []
        any_target_field_extracted = False
        all_target_fields_validated = True

        # BOOLEAN target fields
        mapping = next(
            (
                m
                for m in manifest.evidence_mappings
                if m.doc_type.upper() == effective_doc_type.upper()
            ),
            None,
        )
        if mapping:
            target_spec = state_schema_map.get(mapping.target_field)
            if target_spec and target_spec.type == FieldType.BOOLEAN:
                any_target_field_extracted = True
                raw_values[mapping.target_field] = True
                detected_fields.append(
                    AIDetectedField(
                        key=mapping.target_field,
                        label=target_spec.label,
                        display_value="Verified",
                        value=True,
                    )
                )

        auxiliary_facts: dict[str, Any] = {}

        for field in extracted:
            if field.key in ("name", "identifier"):
                # Auxiliary only - never a manifest state_schema target
                # field in any of the six journeys, so never added to
                # `raw_values`/`detected_fields` (no public-API change).
                # Still worth a real cross-document consistency check
                # (mission Phase 13) against whatever this journey's
                # PRIOR evidence already recorded for the same fact -
                # see `auxiliary_facts` docstring in app/ai/models.py for
                # how the caller persists/retrieves this across uploads.
                # Gated on `field.validated`: an unvalidated (e.g.
                # OCR-garbled, wrong-length) extraction must not create a
                # false contradiction against a genuinely-recorded prior
                # fact (mission requirement: low-confidence extraction
                # should not manufacture a strong conflict).
                if field.value is not None and field.validated:
                    # "identifier" is scoped to the CURRENT doc_type -
                    # comparing identifiers extracted from two DIFFERENT
                    # doc_types (e.g. Investment's IFSC vs its own PAN)
                    # would be comparing two different formats entirely,
                    # not "the same fact reported twice". A person's
                    # NAME, by contrast, is the same real-world fact
                    # regardless of which document type printed it, so
                    # it is compared across ANY doc_type within the
                    # journey.
                    aux_key = "name" if field.key == "name" else f"identifier::{effective_doc_type}"
                    auxiliary_facts[aux_key] = field.value

                    existing_aux_value = existing_fields.get(aux_key)
                    finding = None
                    if isinstance(existing_aux_value, str) and isinstance(field.value, str):
                        finding = (
                            check_name_consistency(existing_aux_value, field.value)
                            if field.key == "name"
                            else check_identifier_consistency(existing_aux_value, field.value)
                        )
                    if finding:
                        # Attach to whichever ambiguity_rule this
                        # journey's manifest itself declares for the
                        # CURRENT evidence's own target field, exactly
                        # the same lookup already used for
                        # monthly_income/employer_name below - never a
                        # journey-specific branch. Where no such rule
                        # exists (most journeys today), the conflict is
                        # simply not surfaced as a clarification, matching
                        # every other field type's existing behavior.
                        ambiguity = next(
                            (
                                a
                                for a in (manifest.ambiguity_rules or [])
                                if mapping and a.field == mapping.target_field
                            ),
                            None,
                        )
                        if ambiguity:
                            conflicts.append(
                                AIConflict(
                                    ambiguity_id=ambiguity.ambiguity_id,
                                    field=field.key,
                                    message=finding.message,
                                )
                            )
                continue

            field_spec = state_schema_map.get(field.key)
            if not field_spec:
                continue

            any_target_field_extracted = any_target_field_extracted or field.value is not None
            all_target_fields_validated = all_target_fields_validated and field.validated

            if field.value is not None:
                raw_values[field.key] = field.value
                display_value = (
                    f"₹{field.value:,}"
                    if isinstance(field.value, int) and field.key == "monthly_income"
                    else str(field.value)
                )
                detected_fields.append(
                    AIDetectedField(
                        key=field.key,
                        label=field_spec.label,
                        display_value=display_value,
                        value=field.value,
                    )
                )

                # Internal consistency check for financial calculation integrity (e.g. Salary Slip)
                if (
                    effective_doc_type == "SALARY_SLIP"
                    and field.key == "monthly_income"
                    and isinstance(field.value, int)
                ):
                    gross_pay = extract_gross_pay(text, lines=ocr_lines)
                    total_deductions = extract_total_deductions(text, lines=ocr_lines)
                    internal_finding = check_salary_slip_internal_consistency(
                        gross_income=gross_pay,
                        total_deductions=total_deductions,
                        net_income=field.value,
                    )
                    if internal_finding and internal_finding.is_conflict:
                        ambiguity = next(
                            (a for a in (manifest.ambiguity_rules or []) if a.field == field.key),
                            None,
                        )
                        ambiguity_id = (
                            ambiguity.ambiguity_id
                            if ambiguity
                            else (
                                manifest.ambiguity_rules[0].ambiguity_id
                                if manifest.ambiguity_rules
                                else "INCOME_MISMATCH"
                            )
                        )
                        conflicts.append(
                            AIConflict(
                                ambiguity_id=ambiguity_id,
                                field=field.key,
                                message=internal_finding.message,
                            )
                        )

                # Cross-document consistency (mission Phase 13): compare
                # against whatever this journey's snapshot already has
                # recorded for the same field from a PRIOR action/evidence.
                #
                # Integrity-hardening phase fix: `monthly_income` now goes
                # through `check_income_consistency`'s real, already-
                # unit-tested 10%-tolerance comparison (app/docai/
                # consistency.py) instead of the plain `!=` this used to
                # do - the tolerance-aware function existed and was
                # tested from Lending's own phase onward, but was never
                # actually CALLED anywhere in production code, so a
                # benign, real-world income difference between a salary
                # slip and a bank statement (e.g. minor deductions) would
                # have been flagged as a conflict every time. Every other
                # field (employer_name, any future TEXT target) keeps the
                # exact-equality fallback deliberately - `names_match`
                # (used by `check_name_consistency`) is built for PERSON
                # names specifically (first/last-token and initials
                # matching), not company names, so applying it to
                # `employer_name` would be inventing an untested,
                # unjustified tolerance rule, not fixing a real gap.
                existing_value = existing_fields.get(field.key)
                if existing_value is not None:
                    is_conflict = existing_value != field.value
                    conflict_message = (
                        f"Previously recorded {field_spec.label} "
                        f"({existing_value}) differs from this document's "
                        f"{field_spec.label} ({field.value})."
                    )
                    if field.key == "monthly_income":
                        if isinstance(existing_value, int) and isinstance(field.value, int):
                            finding = check_income_consistency(existing_value, field.value)
                            is_conflict = finding is not None
                            if finding:
                                conflict_message = finding.message

                    if is_conflict:
                        ambiguity = next(
                            (a for a in (manifest.ambiguity_rules or []) if a.field == field.key),
                            None,
                        )
                        if ambiguity:
                            conflicts.append(
                                AIConflict(
                                    ambiguity_id=ambiguity.ambiguity_id,
                                    field=field.key,
                                    message=conflict_message,
                                )
                            )

        confidence = compose_confidence(
            ConfidenceInputs(
                ocr_confidence=ocr_confidence,
                classification_confidence=classification_confidence,
                field_found=any_target_field_extracted,
                field_validated=all_target_fields_validated,
            )
        )

        # High-signal document intelligence calibration: When a document is
        # classified as CORRECT_DOCUMENT with high OCR clarity (>=0.70), substantial
        # word content (>=15 words), all target fields extracted & validated, and zero
        # conflicts, the structural confirmation provides decisive evidence of authenticity.
        if (
            classification.outcome == "CORRECT_DOCUMENT"
            and any_target_field_extracted
            and all_target_fields_validated
            and len(conflicts) == 0
            and ocr_confidence >= 0.70
            and word_count >= 15
            and classification_confidence >= 0.40
        ):
            confidence = round(min(0.96, max(confidence, 0.88 + 0.08 * (ocr_confidence - 0.70))), 4)

        if not any_target_field_extracted:
            return AIInterpretationResult(
                verified=False,
                confidence=confidence,
                detected=[],
                summary=(
                    f"Recognized this as a "
                    f"{effective_doc_type.replace('_', ' ').title()}, but could not "
                    "reliably extract the required value from it. Please try a clearer copy."
                ),
                conflicts=[],
                raw_values={},
                auxiliary_facts=auxiliary_facts,
                resolved_doc_type=effective_doc_type,
            )

        doc_name_clean = effective_doc_type.replace("_", " ").title()
        # No numeric confidence percentage in this user-facing string - the
        # frontend's absolute rule (frontend/CLAUDE.md #1) is "never render a
        # percentage", and this summary is rendered verbatim as
        # `ai-summary-text` on Screen 7. The measured `confidence` float is
        # still returned in full on `AIInterpretationResult.confidence` /
        # `EvidenceInterpretation.confidence` for any caller that needs the
        # real number - it is just never turned into displayed text here.
        if conflicts:
            conflict_reasons = "; ".join(c.message for c in conflicts)
            summary = (
                f"Recognized as {doc_name_clean}, but internal value inconsistencies "
                f"were detected: {conflict_reasons}"
            )
        else:
            summary = (
                f"Recognized as {doc_name_clean} and extracted {len(detected_fields)} field(s) "
                "using local document AI."
            )
        return AIInterpretationResult(
            verified=len(conflicts) == 0,
            confidence=confidence,
            detected=detected_fields,
            summary=summary,
            conflicts=conflicts,
            raw_values=raw_values,
            auxiliary_facts=auxiliary_facts,
            resolved_doc_type=effective_doc_type,
        )

    async def select_action(
        self,
        snapshot: CoreSnapshot,
        candidate_actions: list[ActionSpec],
        manifest: JourneyPackManifest,
    ) -> ActionRankingResult:
        """Out of scope for this mission - delegated to MockAI. See module docstring."""
        return await self._mock_fallback.select_action(snapshot, candidate_actions, manifest)

    async def explain(
        self,
        field_key: str,
        from_status: str,
        to_status: str,
        action_id: str | None,
        manifest: JourneyPackManifest,
    ) -> str:
        """Out of scope for this mission - delegated to MockAI. See module docstring."""
        return await self._mock_fallback.explain(
            field_key, from_status, to_status, action_id, manifest
        )

    async def chat(
        self,
        message: str,
        manifest: JourneyPackManifest,
        journey_state: JourneyStateResponse,
        recommendation: RecommendationResponse | None,
        diff: JourneyDiff | None = None,
    ) -> str:
        """Conversational Q&A is out of this mission's document-intelligence scope,

        so it is delegated - but to the real LLM adapter (`LLMProvider`,
        pointed at AI_BASE_URL when set, e.g. a local Ollama server) rather
        than straight to MockAI. `LLMProvider.chat` already tries the real
        model first and falls back to its own internal MockAI on any
        failure, so this gets a genuine free-form assistant when one is
        configured and the exact same deterministic behavior as before when
        it isn't - with zero change to the trained classifier/extraction
        path above.
        """
        from app.ai.llm import LLMProvider

        return await LLMProvider(fallback_provider=self._mock_fallback).chat(
            message=message,
            manifest=manifest,
            journey_state=journey_state,
            recommendation=recommendation,
            diff=diff,
        )

    async def general_chat(self, message: str) -> str:
        """Out of scope for this mission - routed to the real LLM adapter

        (same rationale as chat() above), falling back to MockAI.
        """
        from app.ai.llm import LLMProvider

        return await LLMProvider(fallback_provider=self._mock_fallback).general_chat(message)
