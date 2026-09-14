import { describe, it, expect } from 'vitest';
import { classifyInteraction } from './actionInteraction';
import type { components } from '@/api/types.gen';

type ActionOption = components['schemas']['ActionOption'];

function makeAction(overrides: Partial<ActionOption>): ActionOption {
  return {
    action_id: 'GENERIC_ACTION',
    title: 'Generic Action',
    kind: 'FORM',
    why: 'Because.',
    unlocks: ['some_field'],
    ...overrides,
  } as ActionOption;
}

describe('classifyInteraction', () => {
  it('returns EVIDENCE for any EVIDENCE-kind action regardless of action_id', () => {
    expect(classifyInteraction(makeAction({ kind: 'EVIDENCE', action_id: 'UPLOAD_ANYTHING' }))).toBe(
      'EVIDENCE'
    );
  });

  it('returns CLARIFICATION for any CLARIFICATION-kind action', () => {
    expect(classifyInteraction(makeAction({ kind: 'CLARIFICATION', action_id: 'CLARIFY_X' }))).toBe(
      'CLARIFICATION'
    );
  });

  it('returns VIDEO_VERIFICATION for a FORM action whose id contains VIDEO or LIVENESS, on any pack', () => {
    expect(classifyInteraction(makeAction({ action_id: 'START_VIDEO_KYC' }))).toBe('VIDEO_VERIFICATION');
    expect(classifyInteraction(makeAction({ action_id: 'CAPTURE_LIVENESS_SELFIE' }))).toBe(
      'VIDEO_VERIFICATION'
    );
  });

  it('returns SCHEDULING for a FORM action whose id starts with SCHEDULE_', () => {
    expect(classifyInteraction(makeAction({ action_id: 'SCHEDULE_UNDERWRITING_CALL' }))).toBe(
      'SCHEDULING'
    );
  });

  it('returns CONSENT for a FORM action whose id starts with SIGN_/ACCEPT_ or mentions MANDATE', () => {
    expect(classifyInteraction(makeAction({ action_id: 'SIGN_CARD_AGREEMENT' }))).toBe('CONSENT');
    expect(classifyInteraction(makeAction({ action_id: 'ACCEPT_ACCOUNT_TERMS' }))).toBe('CONSENT');
    expect(classifyInteraction(makeAction({ action_id: 'ACCEPT_POLICY_TERMS' }))).toBe('CONSENT');
    expect(classifyInteraction(makeAction({ action_id: 'SETUP_SIP_MANDATE' }))).toBe('CONSENT');
  });

  it('returns generic FORM for a plain field-entry action that matches no special pattern', () => {
    expect(classifyInteraction(makeAction({ action_id: 'VERIFY_PAN_LINK' }))).toBe('FORM');
    expect(classifyInteraction(makeAction({ action_id: 'ADD_NOMINEE' }))).toBe('FORM');
    expect(classifyInteraction(makeAction({ action_id: 'SET_LOAN_TENURE' }))).toBe('FORM');
  });

  it('a bare CONFIRM_ prefix is deliberately NOT treated as consent - safety regression', () => {
    // Found via §6 classifier-safety review against the REAL backend
    // manifest (backend/app/packs/manifests/credit_card.yaml):
    // confirm_dispatch_address ("Confirm Delivery Location", kind=FORM) is a
    // genuine address data-entry form, not an agreement to accept. A
    // CONFIRM_ pattern would have misrouted it to the single-checkbox
    // ConsentPanel, silently discarding whatever real address fields its
    // input_schema defines. "Confirm" is ambiguous between "confirm this
    // data" and "confirm you agree" in a way "sign"/"accept" are not, so it
    // is excluded entirely and safely falls through to generic FORM
    // (§6: "If an action is ambiguous, safely fall back to generic FORM").
    expect(classifyInteraction(makeAction({ action_id: 'CONFIRM_DISPATCH_ADDRESS' }))).toBe('FORM');
    expect(classifyInteraction(makeAction({ action_id: 'confirm_dispatch_address' }))).toBe('FORM');
  });

  it('representative real action_ids from all six backend manifests classify correctly (§6 audit)', () => {
    // Pulled verbatim from backend/app/packs/manifests/*.yaml (lowercase
    // snake_case, as the real backend actually emits - not this repo's
    // frontend mock convention) to prove the classifier is genuinely
    // case-insensitive and pattern-based, not tuned to one naming style.
    const expectations: Array<[string, ReturnType<typeof classifyInteraction>]> = [
      // lending.yaml
      ['upload_income_proof', 'EVIDENCE'], // (kind is what actually drives EVIDENCE; id alone would be FORM)
      ['link_aa_account', 'FORM'],
      ['submit_employment_info', 'FORM'],
      ['verify_employer_record', 'FORM'],
      ['accept_loan_terms', 'CONSENT'],
      // insurance.yaml
      ['submit_medical_declaration', 'FORM'],
      ['submit_ped_exemption', 'FORM'],
      ['schedule_tele_mer', 'SCHEDULING'],
      ['setup_insurance_mandate', 'CONSENT'],
      ['accept_insurance_policy', 'CONSENT'],
      // kyc.yaml
      ['link_pan_record', 'FORM'],
      ['capture_liveness_selfie', 'VIDEO_VERIFICATION'],
      ['validate_gps_location', 'FORM'],
      ['sign_rekyc_undertaking', 'CONSENT'],
      // credit_card.yaml
      ['verify_employment_details', 'FORM'],
      ['confirm_dispatch_address', 'FORM'], // the ambiguous case above, by its real id
      ['sign_cardholder_agreement', 'CONSENT'],
      // account_opening.yaml
      ['verify_pan_for_banking', 'FORM'],
      ['declare_account_nominee', 'FORM'],
      ['opt_out_nominee', 'FORM'],
      ['complete_video_kyc', 'VIDEO_VERIFICATION'],
      ['accept_banking_terms', 'CONSENT'],
      // investment.yaml
      ['check_kra_status', 'FORM'],
      ['complete_risk_questionnaire', 'FORM'],
      ['link_upi_penny_drop', 'FORM'],
      ['register_enach_mandate', 'CONSENT'],
      ['sign_investment_declaration', 'CONSENT'],
    ];

    for (const [actionId, expected] of expectations) {
      const kind = actionId === 'upload_income_proof' ? 'EVIDENCE' : 'FORM';
      const result = classifyInteraction(makeAction({ action_id: actionId, kind }));
      expect(result, `${actionId} expected ${expected}, got ${result}`).toBe(expected);
    }
  });

  it('defaults to FORM when no action is resolved yet', () => {
    expect(classifyInteraction(undefined)).toBe('FORM');
  });

  it('never keys off journey_type - only off the action\'s own kind/action_id (architectural regression)', () => {
    // The exact same action_id pattern classifies identically no matter what
    // journey it belongs to conceptually - there is no journey_type
    // parameter to this function at all, which is the point: journey-
    // specific branching belongs in manifests/fixtures, never in this
    // presentation-layer classifier.
    const insuranceMandate = makeAction({ action_id: 'SETUP_PREMIUM_MANDATE' });
    const investmentMandate = makeAction({ action_id: 'SETUP_SIP_MANDATE' });
    expect(classifyInteraction(insuranceMandate)).toBe(classifyInteraction(investmentMandate));
  });
});
