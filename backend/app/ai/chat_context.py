"""Shared, compact context-building helpers for AIProvider.chat()
implementations (SarvamProvider, LLMProvider).

Kept as a single shared function rather than duplicated per-provider so
"the same logical chat context works regardless of provider" (every
provider that talks to a real model builds its Journey Copilot context the
same way) without introducing a second context system.
"""

from __future__ import annotations

from typing import Any

from app.schemas.journeys import JourneyDiff, RecommendationResponse


def build_other_valid_actions(
    recommendation: RecommendationResponse | None,
) -> list[dict[str, Any]]:
    """Every OTHER currently-valid candidate action, not just the top
    recommendation - so "what can I do" can be answered completely, while
    still only ever naming server-computed candidates."""
    if not recommendation or not recommendation.alternatives:
        return []
    return [
        {"title": alt.title, "why": alt.why, "kind": alt.kind.value}
        for alt in recommendation.alternatives
    ]


def build_diff_context(diff: JourneyDiff | None) -> dict[str, Any] | None:
    """The actual deterministic before/after change, compact enough for a
    chat prompt - or None when there is genuinely nothing to diff yet (the
    journey hasn't moved past its first snapshot). Never fabricated: this is
    a direct, minimal projection of JourneyService.get_diff's own real
    output, not a re-derivation."""
    if diff is None:
        return None
    return {
        "from_version": diff.from_version,
        "to_version": diff.to_version,
        "changed_fields": [
            {
                "label": fc.label,
                "from_status": fc.from_status.value,
                "to_status": fc.to_status.value,
                "display_value": fc.display_value,
                "cause": fc.cause,
            }
            for fc in diff.fields_changed
        ],
        "readiness_change": (
            {
                "from": diff.readiness.from_.value if diff.readiness.from_ else None,
                "to": diff.readiness.to.value if diff.readiness.to else None,
            }
            if diff.readiness
            else None
        ),
        "actions_unlocked": diff.actions_unlocked,
        "actions_removed": diff.actions_removed,
    }
