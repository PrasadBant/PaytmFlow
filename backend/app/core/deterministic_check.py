from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.core.models import (
    CheckToken,
    CoreFieldStatus,
    CoreSnapshot,
)
from app.packs.contract import JourneyPackManifest
from app.schemas.enums import ActionKind, ErrorCode, FieldType


@dataclass(frozen=True)
class ResolvedEvidence:
    """The SERVER-SIDE-VALIDATED result of a real evidence upload,
    resolved by the impure caller (app/services/journey_service.py, which
    does the actual DB lookup) and handed to this pure function as plain
    data - `app/core` itself never touches the database (CLAUDE.md rule
    1), so the lookup cannot happen here, but the CONSUMPTION of its
    result must.

    Document AI integration integrity fix: this is what makes an EVIDENCE
    action consume the REAL, already-computed verification decision
    (`app/evidence/reconcile.py`'s `is_verified` and the AI's own
    `raw_values`) instead of ever falling back to `simulation_defaults`
    or a bare `True`, and instead of ever trusting whatever the client
    put directly in `action_input`.
    """

    doc_type: str
    verified: bool
    values: dict[str, Any]


class DeterministicCheckError(Exception):
    """Raised when an action mutation fails deterministic validation."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def deterministic_check(
    snapshot: CoreSnapshot,
    expected_snapshot_id: UUID | str,
    action_id: str,
    action_input: dict[str, Any] | None,
    manifest: JourneyPackManifest,
    now: datetime | None = None,
    resolved_evidence: ResolvedEvidence | None = None,
) -> CheckToken:
    """The single mutation choke point for PaytmFlow.

    Verifies:
    1. Stale-action protection: expected_snapshot_id == snapshot.snapshot_id (409 ACTION_STALE)
    2. Known action: action_id exists in manifest.actions (422 ACTION_INVALID)
    3. Preconditions: All action preconditions are satisfied (422 ACTION_INVALID)
    4. Input schema: All required inputs are present, type-checked, bounded (400 VALIDATION_ERROR)
    5. Evidence/action compatibility (only when `resolved_evidence` is given - i.e. the caller
       resolved a real `evidence_id` from `action_input`): the evidence's own doc_type must be
       accepted by THIS action, and the evidence must have been genuinely verified
       (422 EVIDENCE_CONFLICT otherwise).

    `resolved_evidence`, when provided, is the caller's already-looked-up, server-side-validated
    evidence result (`app/services/journey_service.py` resolves `action_input["evidence_id"]`
    against the `evidence` table before calling this function - this function itself never
    touches the database). When an EVIDENCE-kind action is executed with `resolved_evidence`
    present, its `values` become the ONLY source for that action's `satisfies` fields - never
    `action_input` (so a client cannot forge `{"evidence_id": ..., "monthly_income": 999999}`),
    never `manifest.simulation_defaults`, never a bare `True`. `simulation_defaults`/`action_input`
    remain the source for FORM/CLARIFICATION actions and for any EVIDENCE action executed with NO
    `evidence_id` at all (a deliberate test/demo fixture path, not a real evidence submission).

    Returns unforgeable CheckToken on success.
    """
    # 1. Stale snapshot check
    if str(snapshot.snapshot_id) != str(expected_snapshot_id):
        raise DeterministicCheckError(
            code=ErrorCode.ACTION_STALE,
            message="The journey state has changed since this action was requested",
            details={
                "current_snapshot_id": str(snapshot.snapshot_id),
                "expected_snapshot_id": str(expected_snapshot_id),
            },
        )

    # 2. Known action check
    action_spec = next((a for a in manifest.actions if a.action_id == action_id), None)
    if not action_spec:
        raise DeterministicCheckError(
            code=ErrorCode.ACTION_INVALID,
            message=(
                f"Action '{action_id}' is not valid for journey '{manifest.metadata.journey_type}'"
            ),
            details={"action_id": action_id},
        )

    # 2b. Evidence/action compatibility (Document AI integration integrity
    # fix) - only runs when the caller resolved a real evidence_id. An
    # EVIDENCE action executed with evidence for a doc_type it doesn't
    # even accept, or with evidence that was never verified, must fail
    # here rather than silently proceed to the simulation-default
    # fallback further below.
    if resolved_evidence is not None and action_spec.kind == ActionKind.EVIDENCE:
        accepts_upper = {a.upper() for a in (action_spec.accepts or [])}
        if resolved_evidence.doc_type.upper() not in accepts_upper:
            raise DeterministicCheckError(
                code=ErrorCode.EVIDENCE_CONFLICT,
                message=(
                    f"Evidence of doc_type '{resolved_evidence.doc_type}' is not accepted "
                    f"by action '{action_id}'."
                ),
                details={
                    "action_id": action_id,
                    "evidence_doc_type": resolved_evidence.doc_type,
                    "accepted_doc_types": sorted(accepts_upper),
                },
            )
        if not resolved_evidence.verified:
            raise DeterministicCheckError(
                code=ErrorCode.EVIDENCE_CONFLICT,
                message=(
                    "The submitted evidence was not verified (wrong document, low "
                    "confidence, or a detected conflict) and cannot satisfy this action."
                ),
                details={"action_id": action_id, "evidence_doc_type": resolved_evidence.doc_type},
            )

    # 3. Preconditions check
    for p in action_spec.preconditions:
        field_state = snapshot.fields.get(p)
        if not field_state or field_state.status not in [
            CoreFieldStatus.SATISFIED,
            CoreFieldStatus.NOT_APPLICABLE,
        ]:
            curr_status = field_state.status.value if field_state else "MISSING"
            raise DeterministicCheckError(
                code=ErrorCode.ACTION_INVALID,
                message=(
                    f"Action precondition '{p}' is not satisfied (current status: {curr_status})"
                ),
                details={
                    "failed_precondition": p,
                    "current_status": curr_status,
                },
            )

    # 4. Input schema validation
    action_input = action_input or {}
    if action_spec.input_schema:
        for f_spec in action_spec.input_schema:
            val = action_input.get(f_spec.key)

            if f_spec.required and val is None:
                raise DeterministicCheckError(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"Required input field '{f_spec.key}' is missing",
                    details={"missing_field": f_spec.key},
                )

            if val is not None:
                if f_spec.type in [FieldType.NUMBER, FieldType.MONEY]:
                    if isinstance(val, bool) or not isinstance(val, (int, float)):
                        raise DeterministicCheckError(
                            code=ErrorCode.VALIDATION_ERROR,
                            message=f"Field '{f_spec.key}' must be a number",
                            details={"field": f_spec.key, "value": val},
                        )
                    if f_spec.min is not None and val < f_spec.min:
                        raise DeterministicCheckError(
                            code=ErrorCode.VALIDATION_ERROR,
                            message=f"Field '{f_spec.key}' must be at least {f_spec.min}",
                            details={"field": f_spec.key, "min": f_spec.min, "value": val},
                        )
                    if f_spec.max is not None and val > f_spec.max:
                        raise DeterministicCheckError(
                            code=ErrorCode.VALIDATION_ERROR,
                            message=f"Field '{f_spec.key}' must be at most {f_spec.max}",
                            details={"field": f_spec.key, "max": f_spec.max, "value": val},
                        )
                elif f_spec.type == FieldType.BOOLEAN:
                    if not isinstance(val, bool):
                        raise DeterministicCheckError(
                            code=ErrorCode.VALIDATION_ERROR,
                            message=f"Field '{f_spec.key}' must be a boolean",
                            details={"field": f_spec.key, "value": val},
                        )
                elif f_spec.type == FieldType.TEXT:
                    if not isinstance(val, str) or not val.strip():
                        raise DeterministicCheckError(
                            code=ErrorCode.VALIDATION_ERROR,
                            message=f"Field '{f_spec.key}' must be a non-empty text string",
                            details={"field": f_spec.key, "value": val},
                        )
                elif f_spec.type == FieldType.ENUM and f_spec.options:
                    valid_options = [opt.value for opt in f_spec.options]
                    if val not in valid_options:
                        raise DeterministicCheckError(
                            code=ErrorCode.VALIDATION_ERROR,
                            message=(
                                f"Field '{f_spec.key}' value '{val}' is not in valid options: "
                                f"{valid_options}"
                            ),
                            details={
                                "field": f_spec.key,
                                "allowed_values": valid_options,
                                "value": val,
                            },
                        )

    # 5. Compute new values for satisfied fields
    #
    # Document AI integration integrity fix: for a real EVIDENCE action
    # (`resolved_evidence` present - by this point already confirmed
    # accepted and verified in step 2b above), the field values come
    # EXCLUSIVELY from the server-validated `resolved_evidence.values` -
    # never from `action_input` (a client could otherwise forge
    # `{"evidence_id": ..., "monthly_income": 999999}`), never from
    # `manifest.simulation_defaults`, never a bare `True`. FORM/
    # CLARIFICATION actions, and any EVIDENCE action executed with no
    # `evidence_id` at all (existing test/demo fixture paths untouched),
    # keep the original `action_input` / simulation_defaults / bare-True
    # fallback chain exactly as before.
    new_values: dict[str, Any] = {}
    use_resolved_evidence = (
        resolved_evidence is not None and action_spec.kind == ActionKind.EVIDENCE
    )
    for s in action_spec.satisfies:
        if use_resolved_evidence:
            assert resolved_evidence is not None  # narrowed by use_resolved_evidence above
            if s not in resolved_evidence.values:
                raise DeterministicCheckError(
                    code=ErrorCode.EVIDENCE_CONFLICT,
                    message=(
                        f"Verified evidence did not produce a value for required field '{s}'."
                    ),
                    details={"action_id": action_id, "field": s},
                )
            new_values[s] = resolved_evidence.values[s]
        elif s in action_input:
            new_values[s] = action_input[s]
        else:
            matching_val = next(
                (v for k, v in action_input.items() if k == s or k in s or s in k),
                None,
            )
            if matching_val is not None:
                new_values[s] = matching_val
            elif s in manifest.simulation_defaults:
                new_values[s] = manifest.simulation_defaults[s]
            else:
                new_values[s] = True

    return CheckToken(
        token_id=uuid4(),
        journey_id=snapshot.journey_id,
        journey_type=snapshot.journey_type,
        action_id=action_id,
        previous_snapshot_id=snapshot.snapshot_id,
        action_input=dict(action_input),
        new_values=new_values,
        direct_fields=list(action_spec.satisfies),
        created_at=now or datetime.now(UTC),
    )
