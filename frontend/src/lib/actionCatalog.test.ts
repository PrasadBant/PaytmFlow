import { describe, it, expect } from 'vitest';
import { getActionDefinition, ACTION_CATALOG } from './actionCatalog';
import { classifyInteraction } from './actionInteraction';

describe('actionCatalog (§6 & §7 audit)', () => {
  it('defines actions for all 6 journey packs', () => {
    expect(Object.keys(ACTION_CATALOG).length).toBeGreaterThan(20);
  });

  it('retrieves action definitions case-insensitively', () => {
    const actLower = getActionDefinition('upload_income_proof');
    const actUpper = getActionDefinition('UPLOAD_INCOME_PROOF');
    expect(actLower).toBeDefined();
    expect(actUpper).toBeDefined();
    expect(actLower?.kind).toBe('EVIDENCE');
  });

  it('returns undefined for unknown action IDs', () => {
    expect(getActionDefinition(undefined)).toBeUndefined();
    expect(getActionDefinition('UNKNOWN_NONEXISTENT_ACTION')).toBeUndefined();
  });

  it('all consent actions in the catalog classify as CONSENT interaction', () => {
    const consentActionIds = [
      'accept_loan_agreement',
      'ACCEPT_LOAN_TERMS',
      'accept_cardholder_agreement',
      'sign_cardholder_agreement',
      'confirm_policy_terms',
      'accept_insurance_policy',
      'confirm_digital_consent',
      'sign_rekyc_undertaking',
      'accept_banking_terms',
      'sign_investment_declaration',
    ];

    for (const actionId of consentActionIds) {
      const def = getActionDefinition(actionId);
      expect(def, `Action ${actionId} should exist in catalog`).toBeDefined();
      const interaction = classifyInteraction(def);
      expect(interaction, `Action ${actionId} should classify as CONSENT`).toBe('CONSENT');
    }
  });

  it('data-gathering form actions classify as FORM', () => {
    const formActionIds = [
      'submit_employment_info',
      'provide_employment_info',
      'confirm_dispatch_address',
      'declare_medical_history',
      'submit_medical_declaration',
      'verify_pan_for_rekyc',
      'declare_account_nominee',
      'complete_risk_questionnaire',
    ];

    for (const actionId of formActionIds) {
      const def = getActionDefinition(actionId);
      expect(def, `Action ${actionId} should exist in catalog`).toBeDefined();
      const interaction = classifyInteraction(def);
      expect(interaction, `Action ${actionId} should classify as FORM`).toBe('FORM');
    }
  });
});
