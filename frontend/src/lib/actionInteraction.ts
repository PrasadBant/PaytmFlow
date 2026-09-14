import type { components } from '@/api/types.gen';

type ActionOption = components['schemas']['ActionOption'];

/**
 * A real financial-services journey doesn't ask for everything through a
 * generic text-field form or a document upload. Some FORM-kind actions are
 * genuinely a different interaction: booking a call, giving explicit
 * consent for a recurring debit, or a liveness/video check.
 *
 * The wire contract (`contract/openapi.yaml`) freezes `ActionOption.kind` to
 * exactly `EVIDENCE | FORM | CLARIFICATION` (00_SHARED_CONTRACT.md §6, §9 —
 * changing it is a breaking contract change requiring the joint change
 * protocol, not something a UI polish pass does solo). This classifier does
 * NOT add a wire-level kind. It's a presentation-only refinement layered on
 * top of `kind: FORM`, inferred from the action's own action_id/title - the
 * same data every pack already provides - never from journey_type. Any pack
 * whose actions happen to match these patterns gets the richer UI; none is
 * special-cased by name.
 */
export type InteractionType =
  | 'EVIDENCE'
  | 'VIDEO_VERIFICATION'
  | 'SCHEDULING'
  | 'CONSENT'
  | 'FORM'
  | 'CLARIFICATION';

const VIDEO_PATTERN = /VIDEO|LIVENESS/i;
const SCHEDULING_PATTERN = /^SCHEDULE_|SCHEDULING/i;
// Deliberately SIGN_/ACCEPT_/MANDATE only - "sign" and "accept" are
// unambiguous consent verbs in this domain. A bare CONFIRM_ prefix was
// tried and removed: the real Credit Card manifest's confirm_dispatch_address
// ("Confirm Delivery Location") is a genuine data-entry FORM (an address),
// not a consent checkbox, and would have been misclassified. Where an
// action IS a real confirmation-of-terms action, its own action_id should
// use accept_/sign_ instead (e.g. "accept_policy_terms"), which is
// unambiguous. When in doubt, this deliberately under-matches and falls
// through to generic FORM rather than risk a false positive.
const CONSENT_PATTERN = /^(SIGN|ACCEPT)_|MANDATE/i;

export function classifyInteraction(action: ActionOption | undefined): InteractionType {
  if (!action) return 'FORM';
  if (action.kind === 'EVIDENCE') return 'EVIDENCE';
  if (action.kind === 'CLARIFICATION') return 'CLARIFICATION';

  const id = action.action_id || '';
  if (VIDEO_PATTERN.test(id)) return 'VIDEO_VERIFICATION';
  if (SCHEDULING_PATTERN.test(id)) return 'SCHEDULING';
  if (CONSENT_PATTERN.test(id)) return 'CONSENT';
  return 'FORM';
}
