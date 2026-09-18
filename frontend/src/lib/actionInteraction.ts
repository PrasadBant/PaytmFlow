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
const CONSENT_PATTERN = /^(SIGN|ACCEPT)_|MANDATE|CONSENT|UNDERTAKING|TERMS|AGREEMENT/i;

export function classifyInteraction(action: ActionOption | undefined): InteractionType {
  if (!action) return 'FORM';
  if (action.kind === 'EVIDENCE') return 'EVIDENCE';
  if (action.kind === 'CLARIFICATION') return 'CLARIFICATION';

  const id = action.action_id || '';
  const title = action.title || '';
  if (VIDEO_PATTERN.test(id) || VIDEO_PATTERN.test(title)) return 'VIDEO_VERIFICATION';
  if (SCHEDULING_PATTERN.test(id) || SCHEDULING_PATTERN.test(title)) return 'SCHEDULING';

  // If an action has text, number, money, or enum fields (e.g. setup_insurance_mandate
  // or register_enach_mandate which collect bank account & IFSC), it must render
  // through SchemaForm to collect those inputs, not a single-checkbox ConsentPanel.
  const schema = Array.isArray(action.input_schema) ? action.input_schema : [];
  const hasDataFields = schema.some((f) => f && f.type !== 'boolean');
  if (hasDataFields) {
    return 'FORM';
  }

  if (CONSENT_PATTERN.test(id) || CONSENT_PATTERN.test(title)) return 'CONSENT';
  return 'FORM';
}
