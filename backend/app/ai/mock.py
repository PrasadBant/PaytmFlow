import re
from typing import Any

from app.ai.models import ActionRankingResult, AIConflict, AIDetectedField, AIInterpretationResult
from app.core.models import CoreSnapshot
from app.packs.contract import ActionSpec, FieldType, GoalFieldSpec, JourneyPackManifest


class MockAI:
    """Deterministic Mock AI provider for PaytmFlow.

    Supplies high-fidelity, reproducible outputs for all six journey packs,
    adhering strictly to schemas and banned words invariants.
    """

    async def parse_goal(
        self,
        journey_type: str,
        natural_language: str,
        goal_schema: list[GoalFieldSpec],
    ) -> dict[str, Any]:
        """Extracts goal fields from natural language prompt deterministically."""
        text = natural_language.lower()
        extracted: dict[str, Any] = {}

        # 1. Extract money / numbers
        numbers = [int(n) for n in re.findall(r"\b\d+\b", text)]
        lakh_matches = re.findall(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac|l)\b", text)
        k_matches = re.findall(r"(\d+(?:\.\d+)?)\s*k\b", text)

        parsed_amount = None
        if lakh_matches:
            parsed_amount = int(float(lakh_matches[0]) * 100000)
        elif k_matches:
            parsed_amount = int(float(k_matches[0]) * 1000)
        elif numbers:
            parsed_amount = next((n for n in numbers if n >= 1000), numbers[0])

        for spec in goal_schema:
            k = spec.key
            if spec.type in [FieldType.MONEY, FieldType.NUMBER]:
                if k in ["loan_amount", "sum_insured", "target_amount", "credit_limit"]:
                    if parsed_amount is not None:
                        val = parsed_amount
                        if spec.min is not None:
                            val = max(val, int(spec.min))
                        if spec.max is not None:
                            val = min(val, int(spec.max))
                        extracted[k] = val
                    elif spec.min is not None:
                        extracted[k] = int(spec.min)
                elif k == "tenure_months":
                    tenure = next((n for n in numbers if 6 <= n <= 84), 24)
                    extracted[k] = tenure
            elif spec.type == FieldType.ENUM and spec.options:
                chosen_opt = None
                for opt in spec.options:
                    opt_val = opt.value.lower().replace("_", " ")
                    opt_label = opt.label.lower()
                    if (
                        opt.value.lower() in text
                        or opt_val in text
                        or opt_label in text
                        or any(word in text for word in opt_label.split() if len(word) > 3)
                    ):
                        chosen_opt = opt.value
                        break
                extracted[k] = chosen_opt or spec.options[0].value
            elif spec.type == FieldType.BOOLEAN:
                if "yes" in text or "true" in text or "with" in text or "co-applicant" in text:
                    extracted[k] = True
                else:
                    extracted[k] = False
            elif spec.type == FieldType.TEXT:
                extracted[k] = "Standard Application"

        return extracted

    async def reconcile_evidence(
        self,
        doc_type: str,
        extracted_text: str,
        manifest: JourneyPackManifest,
        existing_fields: dict[str, Any] | None = None,
    ) -> AIInterpretationResult:
        """Deterministically extracts evidence data and detects potential conflicts."""
        existing_fields = existing_fields or {}
        text = (extracted_text or "").lower()

        # Find matching evidence mapping in pack manifest
        mapping = next(
            (m for m in manifest.evidence_mappings if m.doc_type == doc_type),
            None,
        )

        state_schema_map = {f.key: f for f in manifest.state_schema}
        raw_values: dict[str, Any] = {}
        detected_fields: list[AIDetectedField] = []
        conflicts: list[AIConflict] = []

        # Check for simulated conflict triggers
        is_conflict_simulated = (
            "conflict" in text
            or "mismatch" in text
            or "differ" in text
            or (
                doc_type in ["BANK_STATEMENT", "BANK_STATEMENT_SUMMARY"]
                and existing_fields.get("monthly_income") == 85000
                and "62000" in text
            )
        )

        if is_conflict_simulated and manifest.ambiguity_rules:
            amb = manifest.ambiguity_rules[0]
            conflicts.append(
                AIConflict(
                    ambiguity_id=amb.ambiguity_id,
                    field=amb.field,
                    message=(
                        f"Document data conflicts with previously declared or verified {amb.field}"
                    ),
                )
            )
            detected_fields.append(
                AIDetectedField(
                    key="monthly_income",
                    label="Average Monthly Inflow",
                    display_value="₹62,000",
                    value=62000,
                )
            )
            return AIInterpretationResult(
                verified=False,
                confidence=0.81,
                detected=detected_fields,
                summary=f"Detected potential mismatch in {doc_type} requiring user confirmation.",
                conflicts=conflicts,
                raw_values={"monthly_income": 62000},
            )

        # Standard deterministic extraction based on doc_type and manifest mapping
        if mapping:
            target_keys = mapping.extraction_keys or [mapping.target_field]
        else:
            target_keys = [f.key for f in manifest.state_schema[:2]]

        confidence_threshold = mapping.confidence_threshold if mapping else 0.80
        confidence = min(0.98, confidence_threshold + 0.07)

        for key in target_keys:
            field_spec = state_schema_map.get(key)
            if not field_spec:
                continue

            # Deterministic values by field key and type
            if field_spec.type == FieldType.MONEY:
                val = 85000
                disp = "₹85,000"
            elif field_spec.type == FieldType.BOOLEAN:
                val = True
                disp = "Verified"
            elif field_spec.type == FieldType.TEXT:
                if "employer" in key or "company" in key or "organization" in key:
                    val = "Acme Technologies India Pvt Ltd"
                    disp = val
                elif "pan" in key:
                    val = "ABCDE1234F"
                    disp = val
                elif "account" in key:
                    val = "HDFC0001234"
                    disp = "HDFC Bank ··· 1234"
                elif "nominee" in key:
                    val = "Ananya Sharma"
                    disp = val
                else:
                    val = "Verified Document Record"
                    disp = val
            elif field_spec.type == FieldType.ENUM and field_spec.options:
                val = field_spec.options[0].value
                disp = field_spec.options[0].label
            elif field_spec.type == FieldType.NUMBER:
                val = 1
                disp = "1"
            elif field_spec.type == FieldType.DATE:
                val = "2026-03-01"
                disp = "01 Mar 2026"
            else:
                val = True
                disp = "Verified"

            raw_values[key] = val
            detected_fields.append(
                AIDetectedField(
                    key=key,
                    label=field_spec.label,
                    display_value=disp,
                    value=val,
                )
            )

        doc_name_clean = doc_type.replace("_", " ").title()
        summary = (
            f"Verified {doc_name_clean} with high confidence ({int(confidence * 100)}%). "
            f"Extracted {len(detected_fields)} attribute(s) successfully."
        )

        return AIInterpretationResult(
            verified=True,
            confidence=confidence,
            detected=detected_fields,
            summary=summary,
            conflicts=[],
            raw_values=raw_values,
        )

    async def select_action(
        self,
        snapshot: CoreSnapshot,
        candidate_actions: list[ActionSpec],
        manifest: JourneyPackManifest,
    ) -> ActionRankingResult:
        """Ranks candidate actions prioritizing maximal downstream unblocking."""
        if not candidate_actions:
            return ActionRankingResult(
                recommended_action_id="",
                why="No candidate actions currently executable",
                ranking_order=[],
            )

        top_action = candidate_actions[0]
        why = (
            top_action.why
            or f"Completing {top_action.title} unblocks critical journey verifications."
        )

        return ActionRankingResult(
            recommended_action_id=top_action.action_id,
            why=why,
            ranking_order=[a.action_id for a in candidate_actions],
        )

    async def explain(
        self,
        field_key: str,
        from_status: str,
        to_status: str,
        action_id: str | None,
        manifest: JourneyPackManifest,
    ) -> str:
        """Produces clear, human-readable explanations of state changes or blocker reasons."""
        spec = next((f for f in manifest.state_schema if f.key == field_key), None)
        label = spec.label if spec else field_key.replace("_", " ").title()

        if to_status == "SATISFIED":
            if from_status == "BLOCKED":
                return f"{label} has been verified and satisfied successfully."
            return f"{label} is active and verified."
        if to_status == "AMBIGUOUS":
            return f"{label} requires additional confirmation due to conflicting document data."
        if to_status == "BLOCKED":
            return (
                spec.explanation
                if (spec and spec.explanation)
                else f"{label} is pending prerequisite verification."
            )

        return f"Status of {label} updated to {to_status}."
