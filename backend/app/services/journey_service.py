import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import get_ai_provider
from app.audit.writer import AuditWriter
from app.core.dependencies import DependencyGraph
from app.core.deterministic_check import (
    DeterministicCheckError,
    ResolvedEvidence,
    deterministic_check,
)
from app.core.diff import compute_diff
from app.core.models import (
    CheckToken,
    CoreAmbiguity,
    CoreFieldStatus,
    CoreReadiness,
    CoreSnapshot,
)
from app.core.planner import plan
from app.core.readiness import evaluate_readiness
from app.core.rules import derive_field_states
from app.db.models import JourneyModel, SessionModel
from app.db.repositories.clarifications import ClarificationRepository
from app.db.repositories.evidence import EvidenceRepository
from app.db.repositories.idempotency import IdempotencyRepository
from app.db.repositories.journeys import JourneyRepository
from app.db.repositories.snapshots import SnapshotRepository
from app.packs.contract import ActionSpec, JourneyPackManifest
from app.packs.registry import pack_registry
from app.schemas.enums import (
    ActionKind,
    AnswerType,
    ErrorCode,
    FieldStatus,
    FieldType,
    JourneyStatus,
    JourneyType,
    Readiness,
    RecommendationSource,
    ResumeScreen,
)
from app.schemas.errors import ErrorEnvelope, ErrorObject
from app.schemas.journeys import (
    ActionOption,
    ActionResponse,
    AmbiguityChoice,
    AmbiguityInfo,
    DisplayInfo,
    FieldChange,
    FieldState,
    JourneyDiff,
    JourneyListItem,
    JourneyStateResponse,
    ProgressCounts,
    ProgressDiff,
    ReadinessDiff,
    RecommendationResponse,
)


def format_inr(amount: int | float | None) -> str:
    if amount is None:
        return "₹0"
    val = int(amount)
    s = str(val)
    if len(s) <= 3:
        return f"₹{s}"
    last_three = s[-3:]
    other_digits = s[:-3]
    res = ""
    while len(other_digits) > 2:
        res = "," + other_digits[-2:] + res
        other_digits = other_digits[:-2]
    if other_digits:
        res = other_digits + res
    return f"₹{res},{last_three}"


def validate_goal(manifest: JourneyPackManifest, goal: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(goal, dict):
        raise HTTPException(
            status_code=400,
            detail=ErrorEnvelope(
                error=ErrorObject(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="Goal must be a JSON object",
                )
            ).model_dump(mode="json"),
        )

    spec_map = {f.key: f for f in manifest.goal_schema}
    errors = {}

    # 1. Check for unknown fields
    for k in goal.keys():
        if k not in spec_map:
            errors[k] = f"Unknown goal field '{k}'"

    # 2. Check each spec field
    for key, spec in spec_map.items():
        if spec.required and key not in goal:
            errors[key] = f"Field '{key}' is required"
            continue

        if key in goal:
            val = goal[key]
            if spec.type in [FieldType.MONEY, FieldType.NUMBER]:
                if not isinstance(val, (int, float)) or isinstance(val, bool):
                    errors[key] = f"Field '{key}' must be numeric"
                else:
                    if spec.min is not None and val < spec.min:
                        errors[key] = f"Field '{key}' must be at least {spec.min}"
                    if spec.max is not None and val > spec.max:
                        errors[key] = f"Field '{key}' must be at most {spec.max}"
            elif spec.type == FieldType.ENUM:
                allowed = [opt.value for opt in (spec.options or [])]
                if val not in allowed:
                    errors[key] = f"Value '{val}' is not a valid option for '{key}'"
            elif spec.type == FieldType.BOOLEAN:
                if not isinstance(val, bool):
                    errors[key] = f"Field '{key}' must be boolean"
            elif spec.type == FieldType.TEXT:
                if not isinstance(val, str):
                    errors[key] = f"Field '{key}' must be a string"

    if errors:
        raise HTTPException(
            status_code=400,
            detail=ErrorEnvelope(
                error=ErrorObject(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="Goal validation failed",
                    details=errors,
                )
            ).model_dump(mode="json"),
        )

    return goal


def format_journey_display(manifest: JourneyPackManifest, goal: dict[str, Any]) -> DisplayInfo:
    title = manifest.metadata.display_name
    jtype = manifest.metadata.journey_type

    summary = ""
    if jtype == JourneyType.LENDING:
        amount = goal.get("loan_amount")
        purpose_code = goal.get("loan_purpose")
        purpose_label = purpose_code
        purpose_spec = next((f for f in manifest.goal_schema if f.key == "loan_purpose"), None)
        if purpose_spec and purpose_spec.options:
            for opt in purpose_spec.options:
                if opt.value == purpose_code:
                    purpose_label = opt.label
                    break
        summary = f"{format_inr(amount)} · {purpose_label}"
    elif jtype == JourneyType.INSURANCE:
        amount = goal.get("sum_insured")
        ptype_code = goal.get("policy_type")
        ptype_label = ptype_code
        ptype_spec = next((f for f in manifest.goal_schema if f.key == "policy_type"), None)
        if ptype_spec and ptype_spec.options:
            for opt in ptype_spec.options:
                if opt.value == ptype_code:
                    ptype_label = opt.label
                    break
        summary = f"{format_inr(amount)} · {ptype_label}"
    elif jtype == JourneyType.CREDIT_CARD:
        cvariant = goal.get("card_variant")
        cvariant_label = cvariant
        vspec = next((f for f in manifest.goal_schema if f.key == "card_variant"), None)
        if vspec and vspec.options:
            for opt in vspec.options:
                if opt.value == cvariant:
                    cvariant_label = opt.label
                    break
        summary = str(cvariant_label)
    elif jtype == JourneyType.KYC:
        kpurpose = goal.get("kyc_purpose")
        klabel = kpurpose
        kspec = next((f for f in manifest.goal_schema if f.key == "kyc_purpose"), None)
        if kspec and kspec.options:
            for opt in kspec.options:
                if opt.value == kpurpose:
                    klabel = opt.label
                    break
        summary = str(klabel)
    elif jtype == JourneyType.ACCOUNT_OPENING:
        atype = goal.get("account_type")
        alabel = atype
        aspec = next((f for f in manifest.goal_schema if f.key == "account_type"), None)
        if aspec and aspec.options:
            for opt in aspec.options:
                if opt.value == atype:
                    alabel = opt.label
                    break
        summary = str(alabel)
    elif jtype == JourneyType.INVESTMENT:
        imode = goal.get("investment_mode")
        target = goal.get("target_amount")
        imode_label = imode
        ispec = next((f for f in manifest.goal_schema if f.key == "investment_mode"), None)
        if ispec and ispec.options:
            for opt in ispec.options:
                if opt.value == imode:
                    imode_label = "Monthly SIP" if imode == "MONTHLY_SIP" else opt.label
                    break
        summary = f"{imode_label} · {format_inr(target)}"
    else:
        summary = f"{title} Application"

    return DisplayInfo(title=title, summary=summary)


def get_resolve_action_id(
    field_key: str,
    derived_states: dict[str, Any],
    manifest: JourneyPackManifest,
) -> str | None:
    action_groups = manifest.action_groups or {}
    satisfier_actions = [a for a in manifest.actions if field_key in a.satisfies]
    if not satisfier_actions:
        return None

    # Pick primary if grouped
    selected_action = satisfier_actions[0]
    if selected_action.action_group and selected_action.action_group in action_groups:
        group_spec = action_groups[selected_action.action_group]
        primary_act = next(
            (a for a in manifest.actions if a.action_id == group_spec.primary),
            selected_action,
        )
        selected_action = primary_act

    field_prereqs = [dep.source for dep in manifest.dependencies if dep.target == field_key]
    if field_prereqs:
        current_statuses: dict[str, Any] = {}
        for k, v in derived_states.items():
            if hasattr(v, "status"):
                current_statuses[k] = v.status
            elif isinstance(v, dict):
                current_statuses[k] = v.get("status", "BLOCKED")
            else:
                current_statuses[k] = "BLOCKED"

        unsatisfied_pre = [
            p
            for p in field_prereqs
            if current_statuses.get(p) != CoreFieldStatus.SATISFIED
            and current_statuses.get(p) != "SATISFIED"
        ]
        if len(unsatisfied_pre) == 1:
            pre_field = unsatisfied_pre[0]
            pre_satisfiers = [a for a in manifest.actions if pre_field in a.satisfies]
            if pre_satisfiers and (
                not selected_action.preconditions or pre_field in selected_action.preconditions
            ):
                next_action = pre_satisfiers[0]
                if next_action.action_group and next_action.action_group in action_groups:
                    group_spec = action_groups[next_action.action_group]
                    next_action = next(
                        (a for a in manifest.actions if a.action_id == group_spec.primary),
                        next_action,
                    )
                selected_action = next_action

    return selected_action.action_id


def format_field_display_value(
    field_spec: Any,
    status: FieldStatus | str,
    value: Any,
) -> str:
    status_str = status.value if isinstance(status, FieldStatus) else str(status)

    if status_str == "BLOCKED":
        return "Pending"
    if status_str == "AMBIGUOUS":
        return "Needs Review"
    if status_str == "NOT_APPLICABLE":
        return "Not Applicable"

    if value is True:
        return "Verified"
    if value is False:
        return "Unverified"
    if value is None:
        return "Pending"

    if field_spec.key == "bank_account_linked":
        if str(value).startswith("HDFC"):
            return "HDFC Bank ··· 1234"
        return f"Bank ··· {str(value)[-4:]}"

    if getattr(field_spec, "type", None) == FieldType.MONEY and isinstance(value, (int, float)):
        return format_inr(value)

    return str(value)


def build_field_states_response(
    manifest: JourneyPackManifest,
    snapshot_fields: dict[str, Any],
    derived_states: dict[str, Any],
) -> list[FieldState]:
    fields_response = []

    for spec in manifest.state_schema:
        if not spec.display:
            continue

        raw = snapshot_fields.get(spec.key, {})
        status_str = raw.get("status", "BLOCKED")
        if status_str == "NOT_APPLICABLE":
            continue

        field_status = FieldStatus(status_str)
        val = raw.get("value")
        display_val = format_field_display_value(spec, field_status, val)
        resolve_act = get_resolve_action_id(spec.key, derived_states, manifest)

        amb_info = None
        if field_status == FieldStatus.AMBIGUOUS and "ambiguity" in raw and raw["ambiguity"]:
            amb_data = raw["ambiguity"]
            amb_info = AmbiguityInfo(
                ambiguity_id=amb_data["ambiguity_id"],
                reason=amb_data["reason"],
                question=amb_data["question"],
                answer_type=AnswerType(amb_data["answer_type"]),
                choices=[
                    AmbiguityChoice(value=c["value"], label=c["label"])
                    for c in amb_data.get("choices", [])
                ]
                if amb_data.get("choices")
                else None,
            )

        fields_response.append(
            FieldState(
                key=spec.key,
                label=spec.label,
                status=field_status,
                value=val,
                display_value=display_val,
                explanation=spec.explanation if field_status == FieldStatus.BLOCKED else None,
                resolve_action_id=resolve_act if field_status != FieldStatus.SATISFIED else None,
                mandatory=spec.mandatory,
                ambiguity=amb_info,
            )
        )

    return fields_response


def determine_resume_screen(
    status: JourneyStatus | str,
    readiness: Readiness | str,
    version_number: int,
) -> ResumeScreen:
    status_str = status.value if isinstance(status, JourneyStatus) else str(status)
    readiness_str = readiness.value if isinstance(readiness, Readiness) else str(readiness)

    if status_str == "COMPLETED" or readiness_str == "READY":
        return ResumeScreen.COMPLETE
    if status_str == "NEEDS_REVIEW" or readiness_str == "NEEDS_REVIEW":
        return ResumeScreen.NEEDS_REVIEW
    if readiness_str == "NOT_READY":
        if version_number == 1:
            return ResumeScreen.STATUS
        return ResumeScreen.RECOMMENDATION
    return ResumeScreen.STATUS


class JourneyService:
    @staticmethod
    async def create_journey(
        session: SessionModel,
        journey_type: JourneyType,
        goal: dict[str, Any],
        natural_language: str | None,
        db: AsyncSession,
    ) -> JourneyStateResponse:
        manifest = pack_registry.get_pack(journey_type)
        if not manifest:
            raise HTTPException(
                status_code=404,
                detail=ErrorEnvelope(
                    error=ErrorObject(
                        code=ErrorCode.INVALID_JOURNEY_TYPE,
                        message=f"Journey pack '{journey_type.value}' not found",
                    )
                ).model_dump(mode="json"),
            )

        parsed_nl_goal: dict[str, Any] = {}
        if (
            natural_language
            and natural_language.strip()
            and manifest.metadata.supports_natural_language
        ):
            ai_provider = get_ai_provider()
            parsed_nl_goal = await ai_provider.parse_goal(
                journey_type=manifest.metadata.journey_type.value,
                natural_language=natural_language.strip(),
                goal_schema=manifest.goal_schema,
            )

        merged_goal = {**goal, **parsed_nl_goal}
        validated_goal = validate_goal(manifest, merged_goal)
        display_info = format_journey_display(manifest, validated_goal)

        # 1. Setup initial fields
        current_values: dict[str, Any] = {}
        current_statuses: dict[str, CoreFieldStatus] = {}

        for f in manifest.state_schema:
            if f.default_status == FieldStatus.SATISFIED:
                current_statuses[f.key] = CoreFieldStatus.SATISFIED
                if f.key in [
                    "kyc_verified",
                    "aadhaar_authenticated",
                    "identity_verified",
                    "pan_verified",
                ]:
                    current_values[f.key] = True
                elif f.key == "pan_validated":
                    current_values[f.key] = "ABCDE1234F"
                elif f.key == "bank_account_linked":
                    current_values[f.key] = "HDFC0001234"
                else:
                    current_values[f.key] = True
            else:
                current_statuses[f.key] = CoreFieldStatus.BLOCKED
                if f.type == FieldType.BOOLEAN and f.key.endswith("_accepted"):
                    current_values[f.key] = False
                else:
                    current_values[f.key] = None

        # 2. Derive field states and compute progress
        derived_states, progress_counts = derive_field_states(
            manifest=manifest,
            current_values=current_values,
            current_statuses=current_statuses,
            goal=validated_goal,
        )

        readiness_res = evaluate_readiness(
            manifest=manifest,
            field_states=derived_states,
            goal=validated_goal,
        )
        readiness_enum = Readiness(readiness_res.value)
        journey_status = JourneyStatus.IN_PROGRESS

        journey_id = uuid4()
        snapshot_id = uuid4()
        now = datetime.now(UTC)

        # 3. Create snapshot & journey records
        journey_repo = JourneyRepository(db)
        snapshot_repo = SnapshotRepository(db)

        snapshot_fields_dict = {
            k: {
                "key": f.key,
                "label": f.label,
                "status": (
                    f.status.value if isinstance(f.status, CoreFieldStatus) else str(f.status)
                ),
                "value": f.value,
                "display_value": f.display_value,
                "explanation": f.explanation,
                "resolve_action_id": f.resolve_action_id,
                "mandatory": f.mandatory,
                "derived": f.derived,
                "display": f.display,
                "ambiguity": asdict(f.ambiguity) if f.ambiguity else None,
            }
            for k, f in derived_states.items()
        }

        # The journey row must exist (and be flushed to PostgreSQL) before the
        # initial snapshot is inserted, because journey_snapshots.journey_id is a
        # foreign key to journeys.id. journeys.current_snapshot_id is itself a
        # (nullable, use_alter) foreign key to journey_snapshots.id, so it is left
        # unset here and back-filled once the snapshot exists.
        await journey_repo.create(
            session_id=session.id,
            journey_type=manifest.metadata.journey_type.value,
            schema_version=manifest.metadata.schema_version,
            status=journey_status.value,
            readiness=readiness_enum.value,
            goal=validated_goal,
            display_title=display_info.title,
            display_summary=display_info.summary,
            current_snapshot_id=None,
            journey_id=journey_id,
        )

        await snapshot_repo.create_initial(
            journey_id=journey_id,
            readiness=readiness_enum.value,
            fields=snapshot_fields_dict,
            goal=validated_goal,
            pending_clarification=None,
            snapshot_id=snapshot_id,
        )

        await journey_repo.update_state(
            journey_id=journey_id,
            current_snapshot_id=snapshot_id,
            readiness=readiness_enum.value,
            status=journey_status.value,
        )

        # 5. Record audit event
        audit_writer = AuditWriter(db)
        await audit_writer.record_journey_created(
            journey_id=journey_id,
            session_id=session.id,
            journey_type=manifest.metadata.journey_type.value,
            goal=validated_goal,
            initial_snapshot_id=snapshot_id,
            initial_values=current_values,
        )

        fields_response = build_field_states_response(
            manifest=manifest,
            snapshot_fields=snapshot_fields_dict,
            derived_states=derived_states,
        )

        return JourneyStateResponse(
            journey_id=journey_id,
            journey_type=manifest.metadata.journey_type,
            schema_version=manifest.metadata.schema_version,
            snapshot_id=snapshot_id,
            version_number=1,
            readiness=readiness_enum,
            status=journey_status,
            fields=fields_response,
            progress=ProgressCounts(
                completed=progress_counts.completed,
                pending=progress_counts.pending,
                blockers=progress_counts.blockers,
                total=progress_counts.total,
            ),
            pending_clarification=None,
            display=display_info,
            updated_at=now,
        )

    @staticmethod
    async def get_journey_state(
        journey: JourneyModel,
        db: AsyncSession,
    ) -> JourneyStateResponse:
        manifest = pack_registry.get_pack(journey.journey_type)
        if not manifest:
            raise HTTPException(
                status_code=404,
                detail=ErrorEnvelope(
                    error=ErrorObject(
                        code=ErrorCode.INVALID_JOURNEY_TYPE,
                        message=f"Journey pack '{journey.journey_type}' not found",
                    )
                ).model_dump(mode="json"),
            )

        snapshot_repo = SnapshotRepository(db)
        snapshot = None
        if journey.current_snapshot_id:
            snapshot = await snapshot_repo.get_by_id(journey.current_snapshot_id)
        if not snapshot:
            snapshot = await snapshot_repo.get_latest_by_journey_id(journey.id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="Snapshot not found")

        # Derive live fields for resolve action lookups
        current_values = {
            k: (v.get("value") if isinstance(v, dict) else getattr(v, "value", None))
            for k, v in snapshot.fields.items()
        }
        current_statuses = {
            k: CoreFieldStatus(
                (v.get("status") or "BLOCKED")
                if isinstance(v, dict)
                else getattr(v, "status", "BLOCKED")
            )
            for k, v in snapshot.fields.items()
        }
        ambiguities = {}
        if snapshot.pending_clarification:
            pc = snapshot.pending_clarification
            raw_atype = pc.get("answer_type", "TEXT")
            str_atype = raw_atype.value if hasattr(raw_atype, "value") else str(raw_atype)
            ambiguities[pc["field"]] = CoreAmbiguity(
                ambiguity_id=pc["ambiguity_id"],
                field=pc["field"],
                reason=pc.get("reason", ""),
                question=pc.get("question", ""),
                answer_type=str_atype,
                choices=pc.get("choices"),
            )

        derived_states, progress_counts = derive_field_states(
            manifest=manifest,
            current_values=current_values,
            current_statuses=current_statuses,
            ambiguities=ambiguities,
            goal=snapshot.goal or journey.goal,
        )

        display_info = format_journey_display(manifest, snapshot.goal or journey.goal)
        fields_response = build_field_states_response(
            manifest=manifest,
            snapshot_fields=snapshot.fields,
            derived_states=derived_states,
        )

        pending_clarification_state = None
        if snapshot.pending_clarification:
            pc = snapshot.pending_clarification
            target_field = pc["field"]
            spec = next((f for f in manifest.state_schema if f.key == target_field), None)
            if spec:
                pending_clarification_state = FieldState(
                    key=spec.key,
                    label=spec.label,
                    status=FieldStatus.AMBIGUOUS,
                    value=current_values.get(spec.key),
                    display_value="Needs Review",
                    explanation=pc.get("reason"),
                    mandatory=spec.mandatory,
                    ambiguity=AmbiguityInfo(
                        ambiguity_id=pc["ambiguity_id"],
                        reason=pc["reason"],
                        question=pc["question"],
                        answer_type=AnswerType(pc["answer_type"]),
                        choices=[
                            AmbiguityChoice(value=c["value"], label=c["label"])
                            for c in pc.get("choices", [])
                        ]
                        if pc.get("choices")
                        else None,
                    ),
                )

        return JourneyStateResponse(
            journey_id=journey.id,
            journey_type=manifest.metadata.journey_type,
            schema_version=journey.schema_version,
            snapshot_id=snapshot.id,
            version_number=snapshot.version_number,
            readiness=Readiness(snapshot.readiness),
            status=JourneyStatus(journey.status),
            fields=fields_response,
            progress=ProgressCounts(
                completed=progress_counts.completed,
                pending=progress_counts.pending,
                blockers=progress_counts.blockers,
                total=progress_counts.total,
            ),
            pending_clarification=pending_clarification_state,
            display=display_info,
            natural_language=journey.natural_language,
            updated_at=journey.updated_at,
        )

    @staticmethod
    async def list_journeys(
        session: SessionModel,
        status_filter: JourneyStatus | None,
        journey_type: JourneyType | None,
        limit: int,
        db: AsyncSession,
    ) -> list[JourneyListItem]:
        journey_repo = JourneyRepository(db)
        snapshot_repo = SnapshotRepository(db)

        status_val = status_filter.value if status_filter else None
        jtype_val = journey_type.value if journey_type else None

        journeys = await journey_repo.list_by_session(
            session_id=session.id,
            status=status_val,
            journey_type=jtype_val,
            limit=limit,
        )

        items: list[JourneyListItem] = []
        for j in journeys:
            manifest = pack_registry.get_pack(j.journey_type)
            if not manifest:
                continue

            snapshot = (
                await snapshot_repo.get_by_id(j.current_snapshot_id)
                if j.current_snapshot_id
                else None
            )
            if not snapshot:
                snapshot = await snapshot_repo.get_latest_by_journey_id(j.id)

            display_info = format_journey_display(manifest, j.goal or {})
            progress = None
            version_num = 1
            if snapshot:
                version_num = snapshot.version_number
                current_values = {
                    k: (v.get("value") if isinstance(v, dict) else getattr(v, "value", None))
                    for k, v in snapshot.fields.items()
                }
                current_statuses = {
                    k: CoreFieldStatus(
                        (v.get("status") or "BLOCKED")
                        if isinstance(v, dict)
                        else getattr(v, "status", "BLOCKED")
                    )
                    for k, v in snapshot.fields.items()
                }
                _, p_counts = derive_field_states(
                    manifest=manifest,
                    current_values=current_values,
                    current_statuses=current_statuses,
                    goal=j.goal,
                )
                progress = ProgressCounts(
                    completed=p_counts.completed,
                    pending=p_counts.pending,
                    blockers=p_counts.blockers,
                    total=p_counts.total,
                )

            resume_screen = determine_resume_screen(
                status=j.status,
                readiness=j.readiness,
                version_number=version_num,
            )

            items.append(
                JourneyListItem(
                    journey_id=j.id,
                    journey_type=manifest.metadata.journey_type,
                    display_name=manifest.metadata.display_name,
                    icon=manifest.metadata.icon.value,
                    title=display_info.title,
                    summary=display_info.summary,
                    status=JourneyStatus(j.status),
                    readiness=Readiness(j.readiness),
                    progress=progress,
                    updated_at=j.updated_at,
                    resume_screen=resume_screen,
                )
            )

        return items

    @staticmethod
    async def get_recommendation(
        journey: JourneyModel,
        db: AsyncSession,
    ) -> RecommendationResponse:
        manifest = pack_registry.get_pack(journey.journey_type)
        if not manifest:
            raise HTTPException(
                status_code=404,
                detail=ErrorEnvelope(
                    error=ErrorObject(
                        code=ErrorCode.INVALID_JOURNEY_TYPE,
                        message=f"Journey pack '{journey.journey_type}' not found",
                    )
                ).model_dump(mode="json"),
            )

        snapshot_repo = SnapshotRepository(db)
        snapshot = None
        if journey.current_snapshot_id:
            snapshot = await snapshot_repo.get_by_id(journey.current_snapshot_id)
        if not snapshot:
            snapshot = await snapshot_repo.get_latest_by_journey_id(journey.id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="Snapshot not found")

        readiness_str = snapshot.readiness
        readiness_enum = Readiness(readiness_str)

        if readiness_enum in [Readiness.READY, Readiness.DEAD_END]:
            return RecommendationResponse(
                snapshot_id=snapshot.id,
                readiness=readiness_enum,
                recommendation=None,
                alternatives=[],
                minimum_path_length=0,
                source=None,
            )

        if readiness_enum == Readiness.NEEDS_REVIEW:
            pc = snapshot.pending_clarification or {}
            target_field = pc.get("field", "clarification")
            recommendation = ActionOption(
                action_id=f"CLARIFY_{target_field.upper()}",
                title="Provide Clarification",
                kind=ActionKind.CLARIFICATION,
                why=pc.get("reason", "Clarification required to unblock journey"),
                unlocks=[target_field],
                accepts=None,
                input_schema=None,
            )
            return RecommendationResponse(
                snapshot_id=snapshot.id,
                readiness=readiness_enum,
                recommendation=recommendation,
                alternatives=[],
                minimum_path_length=1,
                # Deterministically constructed from the pending clarification record,
                # not AI-ranked - no AI call happens on this path.
                source=RecommendationSource.PLANNER_FALLBACK,
            )

        # Build CoreSnapshot for planner
        current_values = {
            k: (v.get("value") if isinstance(v, dict) else getattr(v, "value", None))
            for k, v in snapshot.fields.items()
        }
        current_statuses = {
            k: CoreFieldStatus(
                (v.get("status") or "BLOCKED")
                if isinstance(v, dict)
                else getattr(v, "status", "BLOCKED")
            )
            for k, v in snapshot.fields.items()
        }

        derived_states, _ = derive_field_states(
            manifest=manifest,
            current_values=current_values,
            current_statuses=current_statuses,
            goal=snapshot.goal or journey.goal,
        )

        core_snapshot = CoreSnapshot(
            snapshot_id=snapshot.id,
            journey_id=journey.id,
            journey_type=journey.journey_type,
            version_number=snapshot.version_number,
            readiness=CoreReadiness(readiness_str),
            fields=derived_states,
            goal=snapshot.goal or journey.goal,
        )

        graph = DependencyGraph(manifest, core_snapshot.goal)
        plan_res = plan(core_snapshot, manifest)

        # Find executable actions in manifest
        executable_actions: list[ActionSpec] = []
        for act in manifest.actions:
            pre_satisfied = all(
                derived_states.get(p) and derived_states[p].status == CoreFieldStatus.SATISFIED
                for p in act.preconditions
            )
            not_all_satisfied = any(
                derived_states.get(s) and derived_states[s].status != CoreFieldStatus.SATISFIED
                for s in act.satisfies
            )
            if pre_satisfied and not_all_satisfied:
                executable_actions.append(act)

        def to_option(spec: ActionSpec) -> ActionOption:
            unlocks = list(spec.satisfies)
            for s in spec.satisfies:
                for dep in graph.get_direct_dependents(s):
                    if dep not in unlocks:
                        unlocks.append(dep)
            return ActionOption(
                action_id=spec.action_id,
                title=spec.title,
                kind=spec.kind,
                why=spec.why,
                unlocks=unlocks,
                accepts=spec.accepts,
                input_schema=spec.input_schema,
            )

        rec_spec: ActionSpec | None = None
        if plan_res.actions:
            primary_id = plan_res.actions[0].action_id
            rec_spec = next((a for a in manifest.actions if a.action_id == primary_id), None)

        if not rec_spec and executable_actions:
            rec_spec = executable_actions[0]

        # Ask the AI layer to rank the server-computed candidate set. The planner's
        # own pick is placed first so a well-behaved provider (including MockAI,
        # the default) naturally confirms it; the guardrail enforces that the AI
        # can only choose an action_id already in this list (CLAUDE.md rule 2) and
        # reports whether it genuinely ranked or had to fall back, which is the
        # truthful `source` we return - never hardcoded.
        ordered_candidates: list[ActionSpec] = []
        if rec_spec:
            ordered_candidates.append(rec_spec)
        ordered_candidates.extend(
            a for a in executable_actions if not rec_spec or a.action_id != rec_spec.action_id
        )

        recommendation_source = RecommendationSource.PLANNER_FALLBACK
        if ordered_candidates:
            ai_provider = get_ai_provider()
            ranking_result = await ai_provider.select_action(
                snapshot=core_snapshot,
                candidate_actions=ordered_candidates,
                manifest=manifest,
            )
            candidates_by_id = {a.action_id: a for a in ordered_candidates}
            chosen_spec = candidates_by_id.get(ranking_result.recommended_action_id)
            if chosen_spec:
                rec_spec = chosen_spec
            if ranking_result.ranking_order:
                ranked = [
                    candidates_by_id[aid]
                    for aid in ranking_result.ranking_order
                    if aid in candidates_by_id
                ]
                if ranked:
                    for c in ordered_candidates:
                        if c not in ranked:
                            ranked.append(c)
                    ordered_candidates = ranked
            recommendation_source = (
                RecommendationSource.AI_RANKED
                if ranking_result.source == "AI_RANKED"
                else RecommendationSource.PLANNER_FALLBACK
            )

        recommendation_option = to_option(rec_spec) if rec_spec else None

        alt_options = [
            to_option(a)
            for a in ordered_candidates
            if rec_spec and a.action_id != rec_spec.action_id
        ]

        return RecommendationResponse(
            snapshot_id=snapshot.id,
            readiness=readiness_enum,
            recommendation=recommendation_option,
            alternatives=alt_options,
            minimum_path_length=plan_res.minimum_path_length or 1,
            source=recommendation_source,
        )

    @classmethod
    async def apply_action(
        cls,
        journey: JourneyModel,
        session: SessionModel,
        action_id: str,
        expected_snapshot_id: UUID,
        idempotency_key: UUID,
        action_input: dict[str, Any] | None,
        db: AsyncSession,
    ) -> ActionResponse:
        """The single mutation execution method for PaytmFlow journeys.

        Enforces:
        1. Row lock on journey
        2. Idempotency deduplication
        3. Deterministic Check choke point (minting CheckToken or raising 409/422/400)
        4. Pure state mutation and fixpoint rule derivation
        5. Atomic snapshot creation + audit events
        6. Pure diff generation
        7. Next recommendation computation
        8. Idempotency storage
        """
        # 1. Idempotency Check
        idempotency_repo = IdempotencyRepository(db)
        existing = await idempotency_repo.get(str(idempotency_key))
        if existing:
            return ActionResponse.model_validate(existing.response_body)

        # 2. Acquire row lock on journey (Postgres FOR UPDATE / SQLite no-op)
        journey_repo = JourneyRepository(db)
        locked_journey = await journey_repo.get_by_id_for_update(journey.id)
        if locked_journey:
            journey = locked_journey

        # 3. Get pack manifest
        manifest = pack_registry.get_pack(journey.journey_type)
        if not manifest:
            raise HTTPException(
                status_code=404,
                detail=ErrorEnvelope(
                    error=ErrorObject(
                        code=ErrorCode.INVALID_JOURNEY_TYPE,
                        message=f"Journey pack '{journey.journey_type}' not found",
                    )
                ).model_dump(mode="json"),
            )

        # 4. Get current snapshot
        snapshot_repo = SnapshotRepository(db)
        curr_snap = (
            await snapshot_repo.get_by_id(journey.current_snapshot_id)
            if journey.current_snapshot_id
            else None
        )
        if not curr_snap:
            curr_snap = await snapshot_repo.get_latest_by_journey_id(journey.id)
        if not curr_snap:
            raise HTTPException(status_code=404, detail="Snapshot not found")

        # 5. Build CoreSnapshot for previous state
        current_values = {
            k: (v.get("value") if isinstance(v, dict) else getattr(v, "value", None))
            for k, v in curr_snap.fields.items()
        }
        current_statuses = {
            k: CoreFieldStatus(
                (v.get("status") or "BLOCKED")
                if isinstance(v, dict)
                else getattr(v, "status", "BLOCKED")
            )
            for k, v in curr_snap.fields.items()
        }
        derived_states_a, _ = derive_field_states(
            manifest=manifest,
            current_values=current_values,
            current_statuses=current_statuses,
            goal=curr_snap.goal or journey.goal,
        )
        prev_core_snapshot = CoreSnapshot(
            snapshot_id=curr_snap.id,
            journey_id=journey.id,
            journey_type=journey.journey_type,
            version_number=curr_snap.version_number,
            readiness=CoreReadiness(curr_snap.readiness),
            fields=derived_states_a,
            goal=curr_snap.goal or journey.goal,
        )

        # 5b. Resolve a real evidence_id (Document AI integration integrity
        # fix) - the ONLY place a client-supplied evidence reference is
        # ever turned into trusted field values. Looks up the actual,
        # server-persisted evidence row and its ALREADY-COMPUTED
        # verification result (`app/evidence/reconcile.py`'s
        # `is_verified` + the AI's real `raw_values`) - never the
        # client's own claims about what the evidence contains.
        # `app/core` cannot do this DB lookup itself (CLAUDE.md rule 1),
        # so it happens here, in the impure service layer, and is handed
        # to `deterministic_check` as plain, already-validated data.
        resolved_evidence: ResolvedEvidence | None = None
        raw_evidence_id = (action_input or {}).get("evidence_id")
        if raw_evidence_id:
            try:
                evidence_uuid = UUID(str(raw_evidence_id))
            except (ValueError, TypeError, AttributeError) as exc:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": {
                            "code": "NOT_FOUND",
                            "message": f"Evidence '{raw_evidence_id}' not found",
                        }
                    },
                ) from exc
            evidence_repo = EvidenceRepository(db)
            evidence_row = await evidence_repo.get_by_id(evidence_uuid)
            # Cross-journey AND cross-session safety: evidence rows belong
            # to exactly one journey, and journeys were already confirmed
            # to belong to the CURRENT session before `apply_action` is
            # ever called (`verify_journey_ownership` at the API layer) -
            # so requiring `evidence_row.journey_id == journey.id` also
            # transitively rules out another session's evidence, without
            # needing a second, separate session check here.
            if not evidence_row or evidence_row.journey_id != journey.id:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": {
                            "code": "NOT_FOUND",
                            "message": f"Evidence '{raw_evidence_id}' not found",
                        }
                    },
                )
            resolved_evidence = ResolvedEvidence(
                doc_type=evidence_row.doc_type,
                verified=bool(evidence_row.verified),
                values=dict(evidence_row.raw_values or {}),
            )

        # 6. Deterministic Check (choke point)
        audit_writer = AuditWriter(db)
        try:
            token = deterministic_check(
                snapshot=prev_core_snapshot,
                expected_snapshot_id=expected_snapshot_id,
                action_id=action_id,
                action_input=action_input,
                manifest=manifest,
                resolved_evidence=resolved_evidence,
            )
        except DeterministicCheckError as err:
            await audit_writer.record_action_rejected(
                journey_id=journey.id,
                session_id=session.id,
                action_id=action_id,
                reason=err.message,
                error_code=err.code.value,
                details=err.details,
            )
            await db.commit()

            status_code = 400
            if err.code == ErrorCode.ACTION_STALE:
                status_code = 409
            elif err.code in (ErrorCode.ACTION_INVALID, ErrorCode.EVIDENCE_CONFLICT):
                status_code = 422

            cur_snap_id = None
            if "current_snapshot_id" in err.details:
                try:
                    cur_snap_id = UUID(err.details["current_snapshot_id"])
                except Exception:
                    pass

            error_obj = ErrorObject(
                code=err.code,
                message=err.message,
                details=err.details,
                current_snapshot_id=cur_snap_id,
            )
            raise HTTPException(
                status_code=status_code,
                detail=ErrorEnvelope(error=error_obj).model_dump(mode="json"),
            ) from err

        # 6b. Recognize a real, AI-surfaced evidence conflict, if the caller forwards
        # one. Screen07 sends the evidence response's own EvidenceConflict.ambiguity_id
        # back in this action's `input` (a free-form object per the contract - no
        # schema change) after a real POST /evidence detected it. Validated against
        # manifest.ambiguity_rules exactly the way submit_clarification already
        # validates ambiguity_id/field below - deterministic_check above is untouched
        # and stays pure; this only decides SATISFIED vs AMBIGUOUS for the mutation
        # apply_action was already going to make.
        pending_ambiguity: CoreAmbiguity | None = None
        raw_ambiguity_id = (action_input or {}).get("ambiguity_id")
        if raw_ambiguity_id:
            amb_rule = next(
                (a for a in (manifest.ambiguity_rules or []) if a.ambiguity_id == raw_ambiguity_id),
                None,
            )
            if amb_rule and amb_rule.field in token.direct_fields:
                pending_ambiguity = CoreAmbiguity(
                    ambiguity_id=amb_rule.ambiguity_id,
                    field=amb_rule.field,
                    reason=amb_rule.reason,
                    question=amb_rule.question,
                    answer_type=(
                        amb_rule.answer_type.value
                        if hasattr(amb_rule.answer_type, "value")
                        else str(amb_rule.answer_type)
                    ),
                    choices=(
                        [c.model_dump() for c in (amb_rule.choices or [])]
                        if amb_rule.choices
                        else None
                    ),
                )

        # 7. Apply state mutation
        updated_values = dict(current_values)
        updated_values.update(token.new_values)
        updated_statuses = dict(current_statuses)
        for f_key in token.direct_fields:
            updated_statuses[f_key] = CoreFieldStatus.SATISFIED
        if pending_ambiguity:
            updated_statuses[pending_ambiguity.field] = CoreFieldStatus.AMBIGUOUS

        derived_states_b, _ = derive_field_states(
            manifest=manifest,
            current_values=updated_values,
            current_statuses=updated_statuses,
            ambiguities={pending_ambiguity.field: pending_ambiguity} if pending_ambiguity else None,
            goal=journey.goal,
        )
        new_readiness = evaluate_readiness(
            manifest=manifest,
            field_states=derived_states_b,
            goal=journey.goal,
        )

        # 8. Create new immutable snapshot
        fields_to_save = {
            k: {
                "status": f.status.value,
                "value": f.value,
                "ambiguity": asdict(f.ambiguity) if f.ambiguity else None,
            }
            for k, f in derived_states_b.items()
        }
        new_snap = await snapshot_repo.create(
            token=token,
            readiness=new_readiness.value,
            fields=fields_to_save,
            goal=journey.goal,
            pending_clarification=asdict(pending_ambiguity) if pending_ambiguity else None,
        )

        # 9. Update journey state
        new_journey_status = (
            JourneyStatus.COMPLETED
            if new_readiness == CoreReadiness.READY
            else (
                JourneyStatus.NEEDS_REVIEW
                if new_readiness == CoreReadiness.NEEDS_REVIEW
                else JourneyStatus.IN_PROGRESS
            )
        )
        updated_journey = await journey_repo.update_state(
            journey_id=journey.id,
            current_snapshot_id=new_snap.id,
            readiness=new_readiness.value,
            status=new_journey_status.value,
        )
        if not updated_journey:
            updated_journey = journey
            updated_journey.current_snapshot_id = new_snap.id
            updated_journey.readiness = new_readiness.value
            updated_journey.status = new_journey_status.value

        # 10. Record audit events
        await audit_writer.record_action_executed(
            journey_id=journey.id,
            session_id=session.id,
            action_id=action_id,
            token_id=token.token_id,
            snapshot_id=new_snap.id,
            version_number=new_snap.version_number,
            action_input=token.action_input,
            new_values=token.new_values,
        )
        if (
            prev_core_snapshot.readiness.value != new_readiness.value
            or journey.status != new_journey_status.value
        ):
            await audit_writer.record_state_transition(
                journey_id=journey.id,
                session_id=session.id,
                from_readiness=prev_core_snapshot.readiness.value,
                to_readiness=new_readiness.value,
                from_status=journey.status,
                to_status=new_journey_status.value,
                snapshot_id=new_snap.id,
            )

        # 10b. Human Review / Exception Resolution: any field forced AMBIGUOUS
        # by this mutation gets a durable, queryable review case (idempotent -
        # reuses the SAME manifest ambiguity_rules mechanism above, never a
        # separate conflict detector). Local import breaks the circular
        # dependency (review_service imports JourneyService for resolution).
        if pending_ambiguity:
            from app.services.review_service import ReviewCaseService

            await ReviewCaseService.create_or_get_open_case(
                db=db,
                journey=updated_journey,
                ambiguity=pending_ambiguity,
                context_snapshot_id=new_snap.id,
            )

        # 11. Compute Diff
        next_core_snapshot = CoreSnapshot(
            snapshot_id=new_snap.id,
            journey_id=journey.id,
            journey_type=journey.journey_type,
            version_number=new_snap.version_number,
            readiness=new_readiness,
            fields=derived_states_b,
            goal=journey.goal,
        )
        core_diff = compute_diff(
            snapshot_a=prev_core_snapshot,
            snapshot_b=next_core_snapshot,
            manifest=manifest,
            direct_fields=token.direct_fields,
            cause=f"ACTION:{action_id}",
        )

        def _to_field_status(status_val: Any) -> FieldStatus:
            raw = status_val.value if hasattr(status_val, "value") else str(status_val)
            return FieldStatus(raw)

        journey_diff = JourneyDiff(
            from_version=core_diff.from_version,
            to_version=core_diff.to_version,
            fields_changed=[
                FieldChange(
                    key=c.key,
                    label=c.label,
                    from_status=_to_field_status(c.from_status),
                    to_status=_to_field_status(c.to_status),
                    display_value=c.display_value,
                    cause=c.cause,
                    cascaded=c.cascaded,
                )
                for c in core_diff.fields_changed
            ],
            actions_unlocked=core_diff.actions_unlocked,
            actions_removed=core_diff.actions_removed,
            readiness=ReadinessDiff(
                from_=Readiness(core_diff.readiness.from_readiness.value)
                if core_diff.readiness.from_readiness
                else None,
                to=Readiness(core_diff.readiness.to_readiness.value)
                if core_diff.readiness.to_readiness
                else None,
            )
            if core_diff.readiness
            else None,
            progress=ProgressDiff(
                from_=ProgressCounts(
                    completed=core_diff.progress.from_progress.completed,
                    pending=core_diff.progress.from_progress.pending,
                    blockers=core_diff.progress.from_progress.blockers,
                    total=core_diff.progress.from_progress.total,
                )
                if core_diff.progress.from_progress
                else None,
                to=ProgressCounts(
                    completed=core_diff.progress.to_progress.completed,
                    pending=core_diff.progress.to_progress.pending,
                    blockers=core_diff.progress.to_progress.blockers,
                    total=core_diff.progress.to_progress.total,
                )
                if core_diff.progress.to_progress
                else None,
            )
            if core_diff.progress
            else None,
        )

        # 12. Build JourneyStateResponse
        journey_state = await cls.get_journey_state(journey=updated_journey, db=db)

        # 13. Next recommendation
        next_rec = await cls.get_recommendation(journey=updated_journey, db=db)

        # 14. Save idempotency record and commit
        resp_obj = ActionResponse(
            journey=journey_state,
            diff=journey_diff,
            next_recommendation=next_rec,
        )
        req_hash = hashlib.sha256(
            json.dumps(
                {
                    "action_id": action_id,
                    "expected_snapshot_id": str(expected_snapshot_id),
                    "input": action_input or {},
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()

        await idempotency_repo.create(
            key=str(idempotency_key),
            session_id=session.id,
            journey_id=journey.id,
            action_id=action_id,
            request_hash=req_hash,
            response_body=resp_obj.model_dump(mode="json"),
            status_code=200,
        )
        await db.commit()

        return resp_obj

    @classmethod
    async def submit_clarification(
        cls,
        journey: JourneyModel,
        session: SessionModel,
        ambiguity_id: str,
        field: str,
        answer: Any,
        expected_snapshot_id: UUID,
        db: AsyncSession,
    ) -> ActionResponse:
        """Resolves one AMBIGUOUS field.

        Enforces:
        1. Stale-action protection: expected_snapshot_id == current (409 ACTION_STALE)
        2. Known ambiguity: ambiguity_id and field match pack manifest (422 ACTION_INVALID)
        3. Valid answer: answer is valid for the target field/ambiguity
        4. Single-field update: updates ONLY the targeted field and recomputes fixpoint
        5. Surfaces next ambiguity if present (Only one at a time!)
        6. Atomic snapshot creation + audit events
        7. Pure diff generation + next recommendation computation
        """
        # 1. Stale Action Check
        if journey.current_snapshot_id != expected_snapshot_id:
            raise HTTPException(
                status_code=409,
                detail=ErrorEnvelope(
                    error=ErrorObject(
                        code=ErrorCode.ACTION_STALE,
                        message=(
                            "The journey state has changed since this clarification was requested. "
                            "Please refresh."
                        ),
                        details={"current_snapshot_id": str(journey.current_snapshot_id)},
                    )
                ).model_dump(mode="json"),
            )

        # 2. Acquire row lock
        journey_repo = JourneyRepository(db)
        locked_journey = await journey_repo.get_by_id_for_update(journey.id)
        if locked_journey:
            journey = locked_journey

        # 3. Get pack manifest
        manifest = pack_registry.get_pack(journey.journey_type)
        if not manifest:
            raise HTTPException(
                status_code=404,
                detail=ErrorEnvelope(
                    error=ErrorObject(
                        code=ErrorCode.INVALID_JOURNEY_TYPE,
                        message=f"Journey pack '{journey.journey_type}' not found",
                    )
                ).model_dump(mode="json"),
            )

        # 4. Get current snapshot
        snapshot_repo = SnapshotRepository(db)
        curr_snap = (
            await snapshot_repo.get_by_id(journey.current_snapshot_id)
            if journey.current_snapshot_id
            else None
        )
        if not curr_snap:
            curr_snap = await snapshot_repo.get_latest_by_journey_id(journey.id)
        if not curr_snap:
            raise HTTPException(status_code=404, detail="Snapshot not found")

        # 5. Validate ambiguity and field match
        amb_rule = next(
            (a for a in (manifest.ambiguity_rules or []) if a.ambiguity_id == ambiguity_id),
            None,
        )
        if not amb_rule:
            raise HTTPException(
                status_code=422,
                detail=ErrorEnvelope(
                    error=ErrorObject(
                        code=ErrorCode.ACTION_INVALID,
                        message=(
                            f"Unknown ambiguity_id '{ambiguity_id}' for journey type "
                            f"'{journey.journey_type}'"
                        ),
                        details={"ambiguity_id": ambiguity_id},
                    )
                ).model_dump(mode="json"),
            )

        if amb_rule.field != field:
            raise HTTPException(
                status_code=422,
                detail=ErrorEnvelope(
                    error=ErrorObject(
                        code=ErrorCode.ACTION_INVALID,
                        message=(
                            f"Ambiguity '{ambiguity_id}' targets field '{amb_rule.field}', "
                            f"not '{field}'"
                        ),
                        details={"expected_field": amb_rule.field, "provided_field": field},
                    )
                ).model_dump(mode="json"),
            )

        # Validate answer
        target_field_spec = next((f for f in manifest.state_schema if f.key == field), None)
        typed_answer = answer
        if amb_rule.choices:
            valid_vals = [c.value for c in amb_rule.choices]
            if answer not in valid_vals and str(answer) not in [str(v) for v in valid_vals]:
                raise HTTPException(
                    status_code=422,
                    detail=ErrorEnvelope(
                        error=ErrorObject(
                            code=ErrorCode.ACTION_INVALID,
                            message=(
                                f"Answer '{answer}' is not a valid choice for ambiguity "
                                f"'{ambiguity_id}'."
                            ),
                            details={"allowed_choices": valid_vals, "answer": answer},
                        )
                    ).model_dump(mode="json"),
                )
        elif target_field_spec:
            if target_field_spec.type == FieldType.MONEY:
                try:
                    typed_answer = int(float(answer))
                except (ValueError, TypeError) as exc:
                    raise HTTPException(
                        status_code=422,
                        detail=ErrorEnvelope(
                            error=ErrorObject(
                                code=ErrorCode.ACTION_INVALID,
                                message=f"Field '{field}' must be a valid numeric amount.",
                                details={"answer": answer},
                            )
                        ).model_dump(mode="json"),
                    ) from exc
            elif target_field_spec.type == FieldType.BOOLEAN:
                if isinstance(answer, str):
                    typed_answer = answer.lower() in ["true", "yes", "1"]
                else:
                    typed_answer = bool(answer)

        # 6. Previous CoreSnapshot
        prev_values = {
            k: (v.get("value") if isinstance(v, dict) else getattr(v, "value", None))
            for k, v in curr_snap.fields.items()
        }
        prev_statuses = {
            k: CoreFieldStatus(
                (v.get("status") or "BLOCKED")
                if isinstance(v, dict)
                else getattr(v, "status", "BLOCKED")
            )
            for k, v in curr_snap.fields.items()
        }
        prev_ambiguities: dict[str, CoreAmbiguity] = {}
        for f_key, f_data in curr_snap.fields.items():
            if isinstance(f_data, dict):
                amb = f_data.get("ambiguity")
                if amb:
                    raw_at = amb.get("answer_type", "TEXT")
                    prev_ambiguities[f_key] = CoreAmbiguity(
                        ambiguity_id=amb["ambiguity_id"],
                        field=amb.get("field", f_key),
                        reason=amb.get("reason", ""),
                        question=amb.get("question", ""),
                        answer_type=raw_at.value if hasattr(raw_at, "value") else str(raw_at),
                        choices=amb.get("choices"),
                    )
        if curr_snap.pending_clarification:
            pc = curr_snap.pending_clarification
            raw_at = pc.get("answer_type", "TEXT")
            prev_ambiguities[pc["field"]] = CoreAmbiguity(
                ambiguity_id=pc["ambiguity_id"],
                field=pc["field"],
                reason=pc.get("reason", ""),
                question=pc.get("question", ""),
                answer_type=raw_at.value if hasattr(raw_at, "value") else str(raw_at),
                choices=pc.get("choices"),
            )

        derived_states_a, _ = derive_field_states(
            manifest=manifest,
            current_values=prev_values,
            current_statuses=prev_statuses,
            ambiguities=prev_ambiguities,
            goal=curr_snap.goal or journey.goal,
        )
        prev_core_snapshot = CoreSnapshot(
            snapshot_id=curr_snap.id,
            journey_id=journey.id,
            journey_type=journey.journey_type,
            version_number=curr_snap.version_number,
            readiness=CoreReadiness(curr_snap.readiness),
            fields=derived_states_a,
            goal=curr_snap.goal or journey.goal,
        )

        # 7. Apply single-field mutation
        new_values = {**prev_values, field: typed_answer}
        new_statuses = {**prev_statuses, field: CoreFieldStatus.SATISFIED}

        # Check for remaining ambiguities in pack manifest (Only one at a time!)
        next_pending_ambiguity: CoreAmbiguity | None = None
        for other_amb in manifest.ambiguity_rules or []:
            if other_amb.ambiguity_id != ambiguity_id and other_amb.field != field:
                if (
                    other_amb.field in curr_snap.fields
                    and curr_snap.fields[other_amb.field].get("status") == "AMBIGUOUS"
                ):
                    next_pending_ambiguity = CoreAmbiguity(
                        ambiguity_id=other_amb.ambiguity_id,
                        field=other_amb.field,
                        reason=other_amb.reason,
                        question=other_amb.question,
                        answer_type=(
                            other_amb.answer_type.value
                            if hasattr(other_amb.answer_type, "value")
                            else str(other_amb.answer_type)
                        ),
                        choices=(
                            [c.model_dump() for c in (other_amb.choices or [])]
                            if other_amb.choices
                            else None
                        ),
                    )
                    break

        ambiguities_map = (
            {next_pending_ambiguity.field: next_pending_ambiguity} if next_pending_ambiguity else {}
        )
        derived_states_b, progress_counts = derive_field_states(
            manifest=manifest,
            current_values=new_values,
            current_statuses=new_statuses,
            ambiguities=ambiguities_map,
            goal=curr_snap.goal or journey.goal,
        )

        readiness_res = evaluate_readiness(
            manifest=manifest,
            field_states=derived_states_b,
            goal=curr_snap.goal or journey.goal,
        )
        if next_pending_ambiguity:
            readiness_res = CoreReadiness.NEEDS_REVIEW

        # 8. Mint CheckToken
        token = CheckToken(
            token_id=uuid4(),
            journey_id=journey.id,
            journey_type=journey.journey_type,
            action_id=f"CLARIFY:{ambiguity_id}",
            previous_snapshot_id=curr_snap.id,
            action_input={"answer": typed_answer},
            new_values={field: typed_answer},
            direct_fields=[field],
            created_at=datetime.now(UTC),
        )

        # 9. Persist snapshot
        snapshot_fields_dict = {
            k: {
                "key": f.key,
                "label": f.label,
                "status": (
                    f.status.value if isinstance(f.status, CoreFieldStatus) else str(f.status)
                ),
                "value": f.value,
                "display_value": f.display_value,
                "explanation": f.explanation,
                "resolve_action_id": f.resolve_action_id,
                "mandatory": f.mandatory,
                "derived": f.derived,
                "display": f.display,
                "ambiguity": asdict(f.ambiguity) if f.ambiguity else None,
            }
            for k, f in derived_states_b.items()
        }
        next_pending_dict = asdict(next_pending_ambiguity) if next_pending_ambiguity else None

        new_snapshot = await snapshot_repo.create(
            token=token,
            readiness=readiness_res.value,
            fields=snapshot_fields_dict,
            goal=curr_snap.goal or journey.goal,
            pending_clarification=next_pending_dict,
        )

        # 10. Update journey record
        updated_journey = await journey_repo.update_state(
            journey_id=journey.id,
            current_snapshot_id=new_snapshot.id,
            readiness=readiness_res.value,
            status=(
                JourneyStatus.COMPLETED.value
                if readiness_res == CoreReadiness.READY
                else (
                    JourneyStatus.NEEDS_REVIEW.value
                    if readiness_res == CoreReadiness.NEEDS_REVIEW
                    else JourneyStatus.IN_PROGRESS.value
                )
            ),
            updated_at=datetime.now(UTC),
        )
        if not updated_journey:
            updated_journey = journey
            updated_journey.current_snapshot_id = new_snapshot.id
            updated_journey.readiness = readiness_res.value
            updated_journey.status = (
                JourneyStatus.COMPLETED.value
                if readiness_res == CoreReadiness.READY
                else (
                    JourneyStatus.NEEDS_REVIEW.value
                    if readiness_res == CoreReadiness.NEEDS_REVIEW
                    else JourneyStatus.IN_PROGRESS.value
                )
            )

        # 11. Record Clarification & Audit events
        clarification_repo = ClarificationRepository(db)
        await clarification_repo.create(
            journey_id=journey.id,
            ambiguity_id=ambiguity_id,
            field_key=field,
            question=amb_rule.question,
            answer_type=(
                amb_rule.answer_type.value
                if hasattr(amb_rule.answer_type, "value")
                else str(amb_rule.answer_type)
            ),
        )
        audit_writer = AuditWriter(db)
        await audit_writer.record_clarification_answered(
            journey_id=journey.id,
            session_id=session.id,
            clarification_id=uuid4(),
            ambiguity_id=ambiguity_id,
            field_key=field,
            user_response={"answer": typed_answer},
            snapshot_id=new_snapshot.id,
        )
        if next_pending_ambiguity:
            await audit_writer.record_clarification_requested(
                journey_id=journey.id,
                session_id=session.id,
                ambiguity_id=next_pending_ambiguity.ambiguity_id,
                field_key=next_pending_ambiguity.field,
                question=next_pending_ambiguity.question,
            )
        await db.commit()

        # 12. Compute diff
        new_core_snapshot = CoreSnapshot(
            snapshot_id=new_snapshot.id,
            journey_id=journey.id,
            journey_type=journey.journey_type,
            version_number=new_snapshot.version_number,
            readiness=readiness_res,
            fields=derived_states_b,
            goal=curr_snap.goal or journey.goal,
        )
        core_diff = compute_diff(
            snapshot_a=prev_core_snapshot,
            snapshot_b=new_core_snapshot,
            manifest=manifest,
            direct_fields=[field],
            cause=f"CLARIFICATION:{ambiguity_id}",
        )

        def _to_field_status(status_val: Any) -> FieldStatus:
            raw = status_val.value if hasattr(status_val, "value") else str(status_val)
            return FieldStatus(raw)

        journey_diff = JourneyDiff(
            from_version=core_diff.from_version,
            to_version=core_diff.to_version,
            fields_changed=[
                FieldChange(
                    key=c.key,
                    label=c.label,
                    from_status=_to_field_status(c.from_status),
                    to_status=_to_field_status(c.to_status),
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
                    from_=ProgressCounts(
                        completed=core_diff.progress.from_progress.completed,
                        pending=core_diff.progress.from_progress.pending,
                        blockers=core_diff.progress.from_progress.blockers,
                        total=core_diff.progress.from_progress.total,
                    )
                    if core_diff.progress.from_progress
                    else None,
                    to=ProgressCounts(
                        completed=core_diff.progress.to_progress.completed,
                        pending=core_diff.progress.to_progress.pending,
                        blockers=core_diff.progress.to_progress.blockers,
                        total=core_diff.progress.to_progress.total,
                    )
                    if core_diff.progress.to_progress
                    else None,
                )
                if core_diff.progress
                else None
            ),
        )

        journey_state = await cls.get_journey_state(journey=updated_journey, db=db)
        next_rec = await cls.get_recommendation(journey=updated_journey, db=db)

        return ActionResponse(
            journey=journey_state,
            diff=journey_diff,
            next_recommendation=next_rec,
        )

    @classmethod
    async def get_diff(
        cls,
        journey: JourneyModel,
        from_ver: int,
        to_ver: int,
        db: AsyncSession,
    ) -> JourneyDiff:
        manifest = pack_registry.get_pack(journey.journey_type)
        if not manifest:
            raise HTTPException(
                status_code=404,
                detail=ErrorEnvelope(
                    error=ErrorObject(
                        code=ErrorCode.INVALID_JOURNEY_TYPE,
                        message=f"Journey pack '{journey.journey_type}' not found",
                    )
                ).model_dump(mode="json"),
            )

        snapshot_repo = SnapshotRepository(db)
        snap_a = await snapshot_repo.get_by_version(journey.id, from_ver)
        snap_b = await snapshot_repo.get_by_version(journey.id, to_ver)

        if not snap_a or not snap_b:
            missing_ver = from_ver if not snap_a else to_ver
            raise HTTPException(
                status_code=404,
                detail=ErrorEnvelope(
                    error=ErrorObject(
                        code=ErrorCode.VALIDATION_ERROR,
                        message=f"Snapshot version {missing_ver} not found for journey",
                    )
                ).model_dump(mode="json"),
            )

        def _to_core_snapshot(snap) -> CoreSnapshot:
            c_values = {
                k: (v.get("value") if isinstance(v, dict) else getattr(v, "value", None))
                for k, v in snap.fields.items()
            }
            c_statuses = {
                k: CoreFieldStatus(
                    (v.get("status") or "BLOCKED")
                    if isinstance(v, dict)
                    else getattr(v, "status", "BLOCKED")
                )
                for k, v in snap.fields.items()
            }
            derived_states, _ = derive_field_states(
                manifest=manifest,
                current_values=c_values,
                current_statuses=c_statuses,
                goal=snap.goal or journey.goal,
            )
            return CoreSnapshot(
                snapshot_id=snap.id,
                journey_id=journey.id,
                journey_type=journey.journey_type,
                version_number=snap.version_number,
                readiness=CoreReadiness(snap.readiness),
                fields=derived_states,
                goal=snap.goal or journey.goal,
            )

        core_snap_a = _to_core_snapshot(snap_a)
        core_snap_b = _to_core_snapshot(snap_b)

        core_diff = compute_diff(
            snapshot_a=core_snap_a,
            snapshot_b=core_snap_b,
            manifest=manifest,
        )

        def _to_field_status(status_val: Any) -> FieldStatus:
            raw = status_val.value if hasattr(status_val, "value") else str(status_val)
            return FieldStatus(raw)

        return JourneyDiff(
            from_version=core_diff.from_version,
            to_version=core_diff.to_version,
            fields_changed=[
                FieldChange(
                    key=c.key,
                    label=c.label,
                    from_status=_to_field_status(c.from_status),
                    to_status=_to_field_status(c.to_status),
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
                    from_=ProgressCounts(
                        completed=core_diff.progress.from_progress.completed,
                        pending=core_diff.progress.from_progress.pending,
                        blockers=core_diff.progress.from_progress.blockers,
                        total=core_diff.progress.from_progress.total,
                    )
                    if core_diff.progress.from_progress
                    else None,
                    to=ProgressCounts(
                        completed=core_diff.progress.to_progress.completed,
                        pending=core_diff.progress.to_progress.pending,
                        blockers=core_diff.progress.to_progress.blockers,
                        total=core_diff.progress.to_progress.total,
                    )
                    if core_diff.progress.to_progress
                    else None,
                )
                if core_diff.progress
                else None
            ),
        )
