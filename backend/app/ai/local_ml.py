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
)
from app.docai.extraction import extract_fields_for_doc_type
from app.docai.ocr import OcrLine
from app.packs.contract import ActionSpec, GoalFieldSpec, JourneyPackManifest
from app.schemas.enums import FieldType

logger = structlog.get_logger(__name__)

_UNTRUSTED_WRAPPER_RE = re.compile(
    r"^<untrusted_document>\n\[SYSTEM INSTRUCTION:.*?\]\n(.*)\n</untrusted_document>$",
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
    match = _UNTRUSTED_WRAPPER_RE.match(text)
    return match.group(1) if match else text


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
        # declared (e.g. declared SALARY_SLIP, real file is a
        # BANK_STATEMENT - both accepted for the same action). From here
        # on, treat the classifier's own real prediction as the document's
        # actual type - extraction dispatch and the target-field/
        # confidence-threshold mapping lookup (both here and in the
        # caller, app/evidence/reconcile.py) must reflect what the
        # document REALLY is, not what the client guessed when uploading.
        effective_doc_type = classification.predicted_doc_type

        state_schema_map = {f.key: f for f in manifest.state_schema}
        extracted = extract_fields_for_doc_type(text, effective_doc_type, lines=ocr_lines)

        detected_fields: list[AIDetectedField] = []
        raw_values: dict[str, Any] = {}
        conflicts: list[AIConflict] = []
        any_target_field_extracted = False
        all_target_fields_validated = True

        # BOOLEAN target fields (e.g. Insurance's `ped_declaration_submitted`,
        # satisfied by any one of 3 accepted evidence doc types) have no
        # money/text VALUE to extract - genuine classification of the
        # document as the expected type IS the fact being verified, not a
        # missing extraction. Without this, `any_target_field_extracted`
        # would stay False forever for every boolean-target journey and
        # every correctly-classified evidence document would be wrongly
        # reported as unverified - a real gap traced while auditing
        # Insurance's manifest (Lending has no boolean evidence_mappings
        # target, so this path was never exercised until now).
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

        if not any_target_field_extracted:
            return AIInterpretationResult(
                verified=False,
                confidence=confidence,
                detected=[],
                summary=(
                    f"Recognized this as a "
                    f"{effective_doc_type.replace('_', ' ').title()}, but could not "
                    "reliably extract the required value from it. Please try a clearer copy, "
                    "or enter the details manually."
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
