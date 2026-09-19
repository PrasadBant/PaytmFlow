import re
from typing import Any

from app.ai.models import ActionRankingResult, AIInterpretationResult
from app.core.models import CoreSnapshot
from app.packs.contract import ActionSpec, FieldType, GoalFieldSpec, JourneyPackManifest
from app.schemas.journeys import FieldState, JourneyStateResponse, RecommendationResponse

_CHAT_STOPWORDS = {
    "is",
    "my",
    "the",
    "a",
    "an",
    "what",
    "do",
    "does",
    "i",
    "need",
    "for",
    "of",
    "to",
    "this",
    "are",
    "am",
    "it",
    "on",
    "in",
    "have",
    "has",
    "will",
    "can",
    "you",
    "me",
    "about",
    "with",
    "currently",
    "current",
    "status",
}


def _match_field(question_words: set[str], fields: list[FieldState]) -> FieldState | None:
    """Finds the field whose label best overlaps with the question's own words.

    Generic across every journey pack (driven entirely by each field's
    already-server-computed `label`, never a journey-type branch) - this is
    what lets "what is my monthly income" or "is my employer verified" get a
    real, field-specific answer instead of a generic status blurb.
    """
    best: FieldState | None = None
    best_score = 0
    for f in fields:
        label_tokens = re.findall(r"[a-z]+", f.label.lower())
        label_words = {w for w in label_tokens if len(w) > 2 and w not in _CHAT_STOPWORDS}
        score = len(label_words & question_words)
        if score > best_score:
            best_score = score
            best = f
    return best


def _field_reply(f: FieldState) -> str:
    status = f.status.value
    if status == "SATISFIED":
        detail = (
            f" It's recorded as {f.display_value}."
            if f.display_value and f.display_value not in ("Verified", "Pending")
            else " It's verified and complete."
        )
        return f"{f.label} is all set.{detail}"
    if status == "AMBIGUOUS":
        if f.ambiguity and f.ambiguity.question:
            return f.ambiguity.question
        return f"{f.label} needs a quick clarification before it can be confirmed."
    if status == "BLOCKED":
        return f.explanation or f"{f.label} is still pending - it hasn't been submitted yet."
    return f"{f.label}: {f.display_value}."


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
        raw_text = natural_language.lower().strip()
        # Normalize commas in formatted numbers e.g. "2,50,000" -> "250000"
        text = re.sub(r"(\d),(\d)", r"\1\2", raw_text)
        extracted: dict[str, Any] = {}

        # 1. Extract money / numbers
        numbers = [int(n) for n in re.findall(r"\b\d+\b", text)]
        crore_matches = re.findall(r"(\d+(?:\.\d+)?)\s*(?:crore|cr)\b", text)
        lakh_matches = re.findall(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac|l)\b", text)
        k_matches = re.findall(r"(\d+(?:\.\d+)?)\s*k\b", text)

        parsed_amount = None
        if crore_matches:
            parsed_amount = int(float(crore_matches[0]) * 10000000)
        elif lakh_matches:
            parsed_amount = int(float(lakh_matches[0]) * 100000)
        elif k_matches:
            parsed_amount = int(float(k_matches[0]) * 1000)
        elif numbers:
            parsed_amount = next((n for n in numbers if n >= 500), numbers[0])

        for spec in goal_schema:
            k = spec.key
            if spec.type == FieldType.MONEY or (
                spec.type == FieldType.NUMBER
                and any(
                    w in k
                    for w in [
                        "amount",
                        "limit",
                        "deposit",
                        "sum",
                        "insured",
                        "sip",
                        "balance",
                        "target",
                    ]
                )
            ):
                if parsed_amount is not None:
                    val = parsed_amount
                    if spec.min is not None:
                        val = max(val, int(spec.min))
                    if spec.max is not None:
                        val = min(val, int(spec.max))
                    extracted[k] = val
                elif spec.min is not None:
                    extracted[k] = int(spec.min)
            elif spec.type == FieldType.NUMBER and any(
                w in k for w in ["tenure", "duration", "term", "month", "year"]
            ):
                year_matches = re.findall(r"(\d+)\s*(?:years?|yrs?)", text)
                month_matches = re.findall(r"(\d+)\s*(?:months?|mos?|m)\b", text)
                if "year" in k and year_matches:
                    extracted[k] = int(year_matches[0])
                elif "month" in k and month_matches:
                    extracted[k] = int(month_matches[0])
                elif "tenure" in k and year_matches:
                    extracted[k] = int(year_matches[0]) * 12
                else:
                    tenure = next((n for n in numbers if 6 <= n <= 84 and n != parsed_amount), 24)
                    extracted[k] = tenure
            elif spec.type == FieldType.ENUM and spec.options:
                chosen_opt = None
                # Check specialized domain aliases first
                if "lump" in text or "lumpsum" in text or "one time" in text or "one-time" in text:
                    chosen_opt = next((o.value for o in spec.options if "LUMP" in o.value), None)
                elif "sip" in text or "monthly sip" in text or "per month" in text:
                    chosen_opt = next((o.value for o in spec.options if "SIP" in o.value), None)
                elif "medic" in text or "health" in text or "hospital" in text:
                    chosen_opt = next(
                        (
                            o.value
                            for o in spec.options
                            if "MEDIC" in o.value or "HEALTH" in o.value
                        ),
                        None,
                    )
                elif "renovat" in text or "home" in text or "house" in text:
                    chosen_opt = next(
                        (
                            o.value
                            for o in spec.options
                            if "HOME" in o.value or "RENOVAT" in o.value
                        ),
                        None,
                    )
                elif "educat" in text or "study" in text or "college" in text:
                    chosen_opt = next((o.value for o in spec.options if "EDUCAT" in o.value), None)
                elif "cashback" in text:
                    chosen_opt = next(
                        (o.value for o in spec.options if "CASHBACK" in o.value), None
                    )
                elif "reward" in text:
                    chosen_opt = next((o.value for o in spec.options if "REWARD" in o.value), None)
                elif "travel" in text or "flight" in text:
                    chosen_opt = next((o.value for o in spec.options if "TRAVEL" in o.value), None)
                elif "family" in text or "floater" in text:
                    chosen_opt = next((o.value for o in spec.options if "FAMILY" in o.value), None)
                elif "individual" in text or "self" in text:
                    chosen_opt = next(
                        (o.value for o in spec.options if "INDIVIDUAL" in o.value), None
                    )
                elif "salary" in text or "corporate" in text:
                    chosen_opt = next((o.value for o in spec.options if "SALARY" in o.value), None)
                elif "saving" in text or "digital" in text:
                    chosen_opt = next((o.value for o in spec.options if "SAVING" in o.value), None)
                elif "upgrade" in text or "limit" in text:
                    chosen_opt = next(
                        (
                            o.value
                            for o in spec.options
                            if "UPGRADE" in o.value or "LIMIT" in o.value
                        ),
                        None,
                    )
                elif "address" in text:
                    chosen_opt = next((o.value for o in spec.options if "ADDRESS" in o.value), None)
                elif "periodic" in text or "rekyc" in text:
                    chosen_opt = next(
                        (o.value for o in spec.options if "PERIODIC" in o.value), None
                    )

                if not chosen_opt:
                    stop_words = {
                        "loan",
                        "card",
                        "policy",
                        "cover",
                        "account",
                        "investment",
                        "update",
                        "plan",
                        "option",
                        "paytm",
                    }
                    for opt in spec.options:
                        opt_val = opt.value.lower().replace("_", " ")
                        opt_label = opt.label.lower()
                        if (
                            opt.value.lower() in text
                            or opt_val in text
                            or opt_label in text
                            or any(
                                word in text
                                for word in opt_label.split()
                                if len(word) > 3 and word not in stop_words
                            )
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
        ocr_meta: dict[str, Any] | None = None,
        raw_file: bytes | None = None,
        filename: str | None = None,
    ) -> AIInterpretationResult:
        """Deterministically extracts evidence data and detects potential conflicts using
        content-based validation.

        `ocr_meta` is accepted for AIProvider Protocol compatibility and
        intentionally unused - MockAI's purpose is fixed, reproducible
        output regardless of real OCR signals.
        """
        from app.docai.document_validator import validate_document

        existing_fields = existing_fields or {}
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

        outcome = validate_document(
            text=extracted_text,
            expected_doc_type=doc_type,
            manifest=manifest,
            accepted_doc_types=accepted_doc_types,
            existing_fields=existing_fields,
            ocr_confidence=0.95,
            is_mock=True,
        )

        return AIInterpretationResult(
            verified=outcome.is_verified,
            confidence=outcome.confidence,
            detected=outcome.detected_fields,
            summary=outcome.reason,
            conflicts=outcome.conflicts,
            raw_values=outcome.raw_values,
            auxiliary_facts=outcome.auxiliary_facts,
            resolved_doc_type=outcome.predicted_doc_type,
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

    async def chat(
        self,
        message: str,
        manifest: JourneyPackManifest,
        journey_state: JourneyStateResponse,
        recommendation: RecommendationResponse | None,
    ) -> str:
        """Answers free-form questions deterministically, grounded strictly in
        the already-computed journey_state/recommendation data - never in
        journey-type branching (all journeys share this same logic, driven
        by the data each pack manifest already produces).
        """
        q = message.lower()
        top_action = recommendation.recommendation if recommendation else None
        q_tokens = re.findall(r"[a-z]+", q)
        question_words = {w for w in q_tokens if len(w) > 2 and w not in _CHAT_STOPWORDS}

        if re.search(r"^(hi|hello|hey|good morning|good evening)\b", q.strip()):
            return (
                f'Hello! I\'m here to help with your "{journey_state.display.title}" application. '
                "Ask me about your next step, required documents, why something's blocked, "
                "or your overall progress."
            )

        if re.search(r"^(thanks|thank you|thx|ok|okay|got it|cool|great)\b", q.strip()):
            return "You're welcome! Let me know if you have more questions about your application."

        if re.search(r"eligib|qualify|approv", q):
            p = journey_state.progress
            next_step = f' Your next step is "{top_action.title}".' if top_action else ""
            return (
                f"There's no single eligibility decision made all at once - it's based on "
                f"completing a fixed set of requirements. You've completed {p.completed} of "
                f"{p.total} so far.{next_step}"
            )

        if re.search(r"cancel|withdraw|delete (my )?application|stop (my )?application", q):
            return (
                "This assistant can't cancel or withdraw an application. "
                "If you'd like to stop, simply don't complete the remaining steps - "
                "nothing here is submitted irreversibly until you finish."
            )

        if re.search(r"how long|how much time|when will|timeline|turnaround", q):
            p = journey_state.progress
            return (
                "There's no fixed timeline here - it depends on how quickly the remaining "
                f"requirements are completed. You have {p.pending} pending and {p.blockers} "
                f"blocked out of {p.total} total."
            )

        if re.search(r"interest rate|\bfee\b|\bfees\b|\bcharge\b|\bcost\b|\bpremium\b|\bemi\b", q):
            return (
                "I don't have pricing, fee, or rate details in this application's data - please "
                "check the official product terms for that. I can help with what's still needed "
                "to complete your application though."
            )

        # A specific field mention ("what is my monthly income", "is my employer
        # verified") gets a real, field-grounded answer before any of the
        # broader structural intents below - this is what makes the assistant
        # actually answer the question asked instead of a generic status blurb.
        matched_field = _match_field(question_words, journey_state.fields)
        if matched_field:
            return _field_reply(matched_field)

        if re.search(r"next|what should i do|proceed|what now", q):
            if recommendation and recommendation.readiness.value == "READY":
                return (
                    "Your application already satisfies every requirement - "
                    "head to the completion screen to finish up."
                )
            if recommendation and recommendation.readiness.value == "DEAD_END":
                return (
                    "This path has reached a dead end with your current answers. "
                    "Check the alternative actions shown on screen for another way forward."
                )
            if top_action:
                why_text = (top_action.why or "").strip()
                if why_text and why_text[-1] not in ".!?":
                    why_text += "."
                why = f" {why_text}" if why_text else ""
                unlocks = (
                    f" Completing it unlocks: {', '.join(top_action.unlocks)}."
                    if top_action.unlocks
                    else ""
                )
                return f'Your recommended next step is "{top_action.title}".{why}{unlocks}'
            return (
                "There are no pending actions right now - "
                "review your status or proceed to completion."
            )

        if re.search(r"document|upload|proof|evidence", q):
            if top_action and top_action.kind.value == "EVIDENCE" and top_action.accepts:
                accepted = ", ".join(top_action.accepts)
                return (
                    f'For "{top_action.title}", you can upload: {accepted}. '
                    "Make sure the document is clear, complete, and uncropped."
                )
            return (
                "Make sure your document is clear, complete, and uncropped. For income proof, "
                "recent salary slips or bank statements showing steady deposits are accepted."
            )

        if re.search(r"review|conflict|blocked|why", q):
            pending = journey_state.pending_clarification
            if pending and pending.ambiguity and pending.ambiguity.question:
                return pending.ambiguity.question
            if pending and pending.explanation:
                return pending.explanation
            blocked_field = next(
                (f for f in journey_state.fields if f.status.value == "BLOCKED" and f.explanation),
                None,
            )
            if blocked_field:
                return f"{blocked_field.label}: {blocked_field.explanation}"
            return (
                'When an item shows "Needs Review", a manual verification or a simple '
                "clarification question will ensure the data matches accurately."
            )

        if re.search(r"progress|complete|how much|status", q):
            p = journey_state.progress
            return (
                f"You've completed {p.completed} of {p.total} requirements. "
                f"{p.pending} are pending and {p.blockers} are currently blocked."
            )

        if re.search(r"\bpan\b|tax", q):
            return (
                "Ensure your PAN number format is correct (10 characters: 5 letters, "
                "4 numbers, 1 letter). We validate format and identity against official records."
            )

        if re.search(r"liveness|video|photo|selfie", q):
            return (
                "Video and liveness checks verify that the applicant is present in real time. "
                "Simply follow the on-screen prompts to complete verification."
            )

        return (
            "I don't have a specific answer for that in your application data. "
            "I can help with: your next step, required documents, why something's "
            "blocked, or your overall progress - just ask."
        )

    async def general_chat(self, message: str) -> str:
        """Deterministic fallback for chat with no journey started yet -

        used directly before any application exists, and as the safety net
        under LLMProvider.general_chat when the real model is unavailable.
        """
        q = message.lower().strip()

        if re.search(r"^(hi|hello|hey|good morning|good evening)\b", q):
            return (
                "Hello! I can help you fill out this application form - ask me about "
                "any field, or how the process works."
            )

        if re.search(r"^(thanks|thank you|thx|ok|okay|got it|cool|great)\b", q):
            return "You're welcome! Let me know if you have more questions."

        return (
            "I can help with general questions about filling out this form. "
            "Once you start your application, I can also help with next steps, "
            "documents, and progress on your specific case."
        )
