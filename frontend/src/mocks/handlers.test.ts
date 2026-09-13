import { describe, it, expect } from 'vitest';
import { apiClient, buildUrl } from '../api/client';
import { setOverrideScenario } from './scenarios';
import type { components } from '../api/types.gen';
import { ApiError } from '../api/errors';

// jsdom's fetch/FormData polyfill does not serialize a FormData body as real
// multipart/form-data (it stringifies it to the literal text "[object
// FormData]"), so any handler that actually reads the request body - as
// POST /evidence now must, to fix the doc_type-reuse bug - can't be exercised
// through `apiClient.postForm` in this jsdom test environment. This builds a
// real multipart body by hand so the request MSW receives is byte-for-byte
// what a real browser (or the Playwright e2e suite) would send.
function postMultipart<T>(endpoint: string, fields: Record<string, string>): Promise<T> {
  const boundary = `----testboundary${Math.random().toString(16).slice(2)}`;
  const body = Object.entries(fields)
    .map(([name, value]) => `--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${value}\r\n`)
    .join('') + `--${boundary}--\r\n`;

  return fetch(buildUrl(endpoint), {
    method: 'POST',
    headers: { 'Content-Type': `multipart/form-data; boundary=${boundary}` },
    body,
    credentials: 'include',
  }).then((res) => res.json() as Promise<T>);
}

describe('MSW Handlers & Scenarios Suite', () => {
  it('GET /api/v1/health returns ok status with 6 packs', async () => {
    const health = await apiClient.get<{ status: string; packs_loaded: number }>('/health');
    expect(health.status).toBe('ok');
    expect(health.packs_loaded).toBe(6);
  });

  it('GET /api/v1/session returns session payload and sets cookie', async () => {
    const session = await apiClient.get<{ session_id: string; created: boolean }>('/session');
    expect(session.session_id).toBe('00000000-0000-0000-0000-000000000001');
  });

  it('GET /api/v1/journey-packs returns all 6 journey packs', async () => {
    const res = await apiClient.get<{ packs: components['schemas']['JourneyPackSummary'][] }>('/journey-packs');
    expect(res.packs.length).toBe(6);
    expect(res.packs[0].journey_type).toBe('LENDING');
    expect(res.packs[0].flagship_demo).toBe(true);
  });

  it('GET /api/v1/journey-packs/:journey_type returns goal_schema for all 6 packs', async () => {
    const packs = ['LENDING', 'INSURANCE', 'CREDIT_CARD', 'KYC', 'ACCOUNT_OPENING', 'INVESTMENT'];
    for (const type of packs) {
      const pack = await apiClient.get<components['schemas']['JourneyPackDetail']>(`/journey-packs/${type}`);
      expect(pack.journey_type).toBe(type);
      expect(pack.goal_schema.length).toBeGreaterThan(0);
    }
  });

  it('POST /api/v1/journeys creates a new journey snapshot v1', async () => {
    const journey = await apiClient.post<components['schemas']['JourneyStateResponse']>('/journeys', {
      journey_type: 'LENDING',
      goal: { loan_amount: 500000 },
    });
    expect(journey.journey_type).toBe('LENDING');
    expect(journey.version_number).toBe(1);
    expect(journey.progress.completed).toBe(3);
  });

  it('GET /api/v1/journeys/:id returns journey state', async () => {
    const journey = await apiClient.get<components['schemas']['JourneyStateResponse']>(
      '/journeys/11111111-1111-1111-1111-111111111111'
    );
    expect(journey.journey_id).toBe('11111111-1111-1111-1111-111111111111');
    expect(journey.readiness).toBe('NOT_READY');
  });

  it('POST /api/v1/journeys/:id/evidence returns deterministic consequence preview', async () => {
    const evidence = await postMultipart<components['schemas']['EvidenceResponse']>(
      '/journeys/11111111-1111-1111-1111-111111111111/evidence',
      { doc_type: 'SALARY_SLIP', expected_snapshot_id: 'aaaaaaaa-1111-1111-1111-111111111111' }
    );
    expect(evidence.interpretation.verified).toBe(true);
    expect(evidence.consequence_preview).toBeDefined();
    expect(evidence.consequence_preview?.newly_satisfied[0].key).toBe('monthly_income');
    expect(evidence.requires_review).toBe(false);
  });

  it('Scenario "needsreview": evidence upload triggers requires_review and conflicts', async () => {
    setOverrideScenario('needsreview');
    const evidence = await postMultipart<components['schemas']['EvidenceResponse']>(
      '/journeys/11111111-1111-1111-1111-111111111111/evidence',
      { doc_type: 'BANK_STATEMENT', expected_snapshot_id: 'bbbbbbbb-2222-2222-2222-222222222222' }
    );
    expect(evidence.requires_review).toBe(true);
    expect(evidence.interpretation.conflicts.length).toBeGreaterThan(0);
    expect(evidence.interpretation.conflicts[0].ambiguity_id).toBe('INCOME_MISMATCH');
  });

  it('Scenario "stale": action mutation returns 409 ACTION_STALE with current_snapshot_id', async () => {
    setOverrideScenario('stale');
    try {
      await apiClient.post('/journeys/11111111-1111-1111-1111-111111111111/actions', {
        action_id: 'UPLOAD_INCOME_PROOF',
        expected_snapshot_id: 'aaaaaaaa-1111-1111-1111-111111111111',
        idempotency_key: '00000000-0000-0000-0000-000000000000',
      });
      expect.unreachable('Should fail with 409');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(409);
      expect(apiErr.code).toBe('ACTION_STALE');
      expect(apiErr.currentSnapshotId).toBe('bbbbbbbb-2222-2222-2222-222222222222');
    }
  });

  it('Scenario "invalid": action mutation returns 422 ACTION_INVALID', async () => {
    setOverrideScenario('invalid');
    try {
      await apiClient.post('/journeys/11111111-1111-1111-1111-111111111111/actions', {
        action_id: 'UPLOAD_INCOME_PROOF',
        expected_snapshot_id: 'aaaaaaaa-1111-1111-1111-111111111111',
        idempotency_key: '00000000-0000-0000-0000-000000000000',
      });
      expect.unreachable('Should fail with 422');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(422);
      expect(apiErr.code).toBe('ACTION_INVALID');
    }
  });

  it('Scenario "deadend": journey returns DEAD_END readiness state', async () => {
    setOverrideScenario('deadend');
    const journey = await apiClient.get<components['schemas']['JourneyStateResponse']>(
      '/journeys/11111111-1111-1111-1111-111111111111'
    );
    expect(journey.readiness).toBe('DEAD_END');
  });

  it('Scenario "empty": GET /journeys returns empty list', async () => {
    setOverrideScenario('empty');
    const res = await apiClient.get<{ journeys: components['schemas']['JourneyListItem'][] }>('/journeys');
    expect(res.journeys).toEqual([]);
  });

  describe('POST /evidence never reuses a previous document\'s result (regression)', () => {
    // Root cause of the reported bug: this handler used to return the exact same
    // salary-slip fixture for every evidence upload, regardless of doc_type. Each
    // assertion below proves the response is genuinely keyed off the real
    // doc_type sent, not left over from whichever document was uploaded first.

    it('Salary Slip, Bank Statement, and Address Proof each return their own filename/summary/values', async () => {
      const salarySlip = await postMultipart<components['schemas']['EvidenceResponse']>(
        '/journeys/11111111-1111-1111-1111-111111111111/evidence',
        { doc_type: 'SALARY_SLIP', expected_snapshot_id: 'x' }
      );
      const bankStatement = await postMultipart<components['schemas']['EvidenceResponse']>(
        '/journeys/11111111-1111-1111-1111-111111111111/evidence',
        { doc_type: 'BANK_STATEMENT', expected_snapshot_id: 'x' }
      );
      const addressProof = await postMultipart<components['schemas']['EvidenceResponse']>(
        '/journeys/11111111-1111-1111-1111-111111111111/evidence',
        { doc_type: 'ADDRESS_PROOF', expected_snapshot_id: 'x' }
      );

      // Every response is genuinely distinct - none of the three collapsed to the
      // same evidence_id, filename, or summary as another.
      const ids = [salarySlip.evidence_id, bankStatement.evidence_id, addressProof.evidence_id];
      const filenames = [salarySlip.filename, bankStatement.filename, addressProof.filename];
      const summaries = [
        salarySlip.interpretation.summary,
        bankStatement.interpretation.summary,
        addressProof.interpretation.summary,
      ];
      expect(new Set(ids).size).toBe(3);
      expect(new Set(filenames).size).toBe(3);
      expect(new Set(summaries).size).toBe(3);

      // Specifically: Bank Statement and Address Proof must never carry the
      // salary slip's filename, and must not surface its detected field key
      // (monthly_income came from THIS document, not a stale salary result -
      // bank_statement/current_address are the fields these two actually satisfy).
      expect(bankStatement.filename).not.toBe(salarySlip.filename);
      expect(bankStatement.interpretation.detected.map((d) => d.key)).not.toContain('employer_name');
      expect(bankStatement.interpretation.detected[0].key).toBe('bank_statement');

      expect(addressProof.filename).not.toBe(salarySlip.filename);
      expect(addressProof.filename).not.toBe(bankStatement.filename);
      expect(addressProof.interpretation.detected[0].key).toBe('current_address');
      expect(addressProof.interpretation.summary).not.toMatch(/salary|₹85,000/i);
    });

    it('an evidence action with no curated fixture reflects its own doc_type and submitted values, never salary-slip data', async () => {
      // PAN verification (or any other EVIDENCE action not yet given a bespoke
      // fixture) must not silently fall back to the salary slip's ₹85,000 -
      // this proves the generic fallback path is genuinely doc_type-driven and
      // never fabricates or reuses another document's specific figures.
      const panEvidence = await postMultipart<components['schemas']['EvidenceResponse']>(
        '/journeys/11111111-1111-1111-1111-111111111111/evidence',
        {
          doc_type: 'PAN_CARD',
          expected_snapshot_id: 'x',
          manual_fields: JSON.stringify({ pan_number: 'ABCDE1234F' }),
        }
      );

      expect(panEvidence.filename).not.toBe('payslip_august_2026.pdf');
      expect(panEvidence.interpretation.summary).not.toMatch(/salary|₹85,000/i);
      expect(panEvidence.interpretation.detected).toEqual([
        { key: 'pan_number', label: 'pan number', display_value: 'ABCDE1234F' },
      ]);
      expect(panEvidence.consequence_preview).toBeNull();
    });

    it('consecutive uploads of the SAME doc_type each still return that document\'s real (non-stale) evidence_id', async () => {
      const first = await postMultipart<components['schemas']['EvidenceResponse']>(
        '/journeys/11111111-1111-1111-1111-111111111111/evidence',
        { doc_type: 'SALARY_SLIP', expected_snapshot_id: 'x' }
      );
      const second = await postMultipart<components['schemas']['EvidenceResponse']>(
        '/journeys/11111111-1111-1111-1111-111111111111/evidence',
        { doc_type: 'BANK_STATEMENT', expected_snapshot_id: 'x' }
      );
      const third = await postMultipart<components['schemas']['EvidenceResponse']>(
        '/journeys/11111111-1111-1111-1111-111111111111/evidence',
        { doc_type: 'SALARY_SLIP', expected_snapshot_id: 'x' }
      );

      // Returning to SALARY_SLIP after an intervening BANK_STATEMENT upload must
      // show salary data again, not carry over the bank statement's result.
      expect(third.interpretation.detected[0].key).toBe(first.interpretation.detected[0].key);
      expect(third.filename).toBe(first.filename);
      expect(third.filename).not.toBe(second.filename);
    });
  });

  describe('Every journey shows its own pack data - never another journey\'s (regression)', () => {
    // Root cause: GET /journeys/:id, GET recommendation, POST actions/evidence/
    // clarifications all used to ignore the real journey_id and unconditionally
    // return LENDING fixture data. A cold load (refresh, deep link, "Resume"
    // from My Journeys) of ANY other journey silently showed someone else's
    // fields, progress and blockers. These assertions hit the endpoints exactly
    // as a fresh page load would (no prior cache to paper over it).
    const INSURANCE_ID = '22222222-2222-2222-2222-222222222222';
    const KYC_ID = '33333333-3333-3333-3333-333333333333';

    it('GET /journeys/:id returns INSURANCE fields for the INSURANCE journey_id, not LENDING\'s', async () => {
      const journey = await apiClient.get<components['schemas']['JourneyStateResponse']>(
        `/journeys/${INSURANCE_ID}`
      );
      expect(journey.journey_type).toBe('INSURANCE');
      const keys = journey.fields.map((f) => f.key);
      expect(keys).not.toContain('loan_amount');
      expect(keys).toContain('coverage_amount');
    });

    it('GET /journeys/:id returns KYC fields for the KYC journey_id, not LENDING\'s or INSURANCE\'s', async () => {
      const journey = await apiClient.get<components['schemas']['JourneyStateResponse']>(
        `/journeys/${KYC_ID}`
      );
      expect(journey.journey_type).toBe('KYC');
      const keys = journey.fields.map((f) => f.key);
      expect(keys).not.toContain('loan_amount');
      expect(keys).not.toContain('coverage_amount');
      expect(keys).toContain('aadhaar_number');
    });

    it('GET /journeys/:id/recommendation for INSURANCE surfaces its own pending clarification, not a Lending one', async () => {
      const rec = await apiClient.get<components['schemas']['RecommendationResponse']>(
        `/journeys/${INSURANCE_ID}/recommendation`
      );
      expect(rec.readiness).toBe('NEEDS_REVIEW');
      expect(rec.recommendation?.kind).toBe('CLARIFICATION');
      expect(rec.recommendation?.unlocks).toContain('medical_declaration');
    });

    it('an unknown journey_id 404s instead of silently returning Lending data', async () => {
      try {
        await apiClient.get('/journeys/00000000-0000-0000-0000-000000000000');
        expect.unreachable('expected a 404');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        expect((err as ApiError).status).toBe(404);
      }
    });

    it('journey.display never falls back to a Lending-specific title for another pack', async () => {
      const journey = await apiClient.get<components['schemas']['JourneyStateResponse']>(
        `/journeys/${INSURANCE_ID}`
      );
      expect(journey.display?.title).not.toBe('Personal Loan');
      expect(journey.display?.title).toBeTruthy();
    });
  });

  describe('Full EVIDENCE/FORM action cycle for every non-Lending pack (Phase 4/6 regression)', () => {
    // Earlier spot-checks only proved the cold-load GET was correct for these
    // three packs. This proves the full mutation cycle - preview/apply, snapshot
    // advance, progress recount, and next_recommendation - is also generic and
    // pack-correct, for both an EVIDENCE action (CREDIT_CARD/UPLOAD_ITR) and two
    // FORM actions (ACCOUNT_OPENING/VERIFY_PAN, INVESTMENT/SUBMIT_FATCA).
    const CREDIT_CARD_ID = '44444444-4444-4444-4444-444444444444';
    const ACCOUNT_OPENING_ID = '55555555-5555-5555-5555-555555555555';
    const INVESTMENT_ID = '66666666-6666-6666-6666-666666666666';

    it('CREDIT_CARD: uploading the ITR resolves itr_verification and readiness becomes READY', async () => {
      const before = await apiClient.get<components['schemas']['JourneyStateResponse']>(
        `/journeys/${CREDIT_CARD_ID}`
      );
      expect(before.progress).toEqual({ completed: 2, pending: 0, blockers: 1, total: 3 });

      const evidence = await postMultipart<components['schemas']['EvidenceResponse']>(
        `/journeys/${CREDIT_CARD_ID}/evidence`,
        { doc_type: 'ITR', expected_snapshot_id: before.snapshot_id }
      );
      expect(evidence.proposed_action_id).toBe('UPLOAD_ITR');
      expect(evidence.interpretation.detected.map((d) => d.key)).toContain('itr_verification');

      const result = await apiClient.post<components['schemas']['ActionResponse']>(
        `/journeys/${CREDIT_CARD_ID}/actions`,
        {
          action_id: 'UPLOAD_ITR',
          expected_snapshot_id: before.snapshot_id,
          idempotency_key: '10000000-0000-0000-0000-000000000001',
        }
      );
      expect(result.journey.journey_type).toBe('CREDIT_CARD');
      const itrField = result.journey.fields.find((f) => f.key === 'itr_verification');
      expect(itrField?.status).toBe('SATISFIED');
      expect(result.journey.progress).toEqual({ completed: 3, pending: 0, blockers: 0, total: 3 });
      expect(result.journey.readiness).toBe('READY');
      expect(result.next_recommendation?.recommendation).toBeNull();
      // No Lending or Insurance field ever appears on a Credit Card journey.
      expect(result.journey.fields.map((f) => f.key)).not.toContain('loan_amount');
    });

    it('ACCOUNT_OPENING: submitting VERIFY_PAN (a FORM action) resolves pan_record generically', async () => {
      const before = await apiClient.get<components['schemas']['JourneyStateResponse']>(
        `/journeys/${ACCOUNT_OPENING_ID}`
      );
      const result = await apiClient.post<components['schemas']['ActionResponse']>(
        `/journeys/${ACCOUNT_OPENING_ID}/actions`,
        {
          action_id: 'VERIFY_PAN',
          expected_snapshot_id: before.snapshot_id,
          idempotency_key: '10000000-0000-0000-0000-000000000002',
          input: { pan_record: 'ABCDE1234F' },
        }
      );
      expect(result.journey.journey_type).toBe('ACCOUNT_OPENING');
      const panField = result.journey.fields.find((f) => f.key === 'pan_record');
      expect(panField?.status).toBe('SATISFIED');
      expect(panField?.display_value).toBe('ABCDE1234F');
      expect(result.journey.progress).toEqual({ completed: 2, pending: 0, blockers: 0, total: 2 });
      expect(result.journey.readiness).toBe('READY');
    });

    it('INVESTMENT: submitting SUBMIT_FATCA (a FORM action) resolves fatca_declaration generically', async () => {
      const before = await apiClient.get<components['schemas']['JourneyStateResponse']>(
        `/journeys/${INVESTMENT_ID}`
      );
      const result = await apiClient.post<components['schemas']['ActionResponse']>(
        `/journeys/${INVESTMENT_ID}/actions`,
        {
          action_id: 'SUBMIT_FATCA',
          expected_snapshot_id: before.snapshot_id,
          idempotency_key: '10000000-0000-0000-0000-000000000003',
          input: { fatca_declaration: 'Resident' },
        }
      );
      expect(result.journey.journey_type).toBe('INVESTMENT');
      const fatcaField = result.journey.fields.find((f) => f.key === 'fatca_declaration');
      expect(fatcaField?.status).toBe('SATISFIED');
      expect(result.journey.progress).toEqual({ completed: 2, pending: 0, blockers: 0, total: 2 });
      expect(result.journey.readiness).toBe('READY');
      // GET /diff for this journey now reflects THIS journey's own change, not
      // another pack's cached diff.
      const diff = await apiClient.get<components['schemas']['JourneyDiff']>(
        `/journeys/${INVESTMENT_ID}/diff`
      );
      expect(diff.fields_changed.map((f) => f.key)).toContain('fatca_declaration');
    });

    it('a stale expected_snapshot_id on a non-Lending journey is rejected with ACTION_STALE (409), not silently applied', async () => {
      try {
        await apiClient.post(`/journeys/${ACCOUNT_OPENING_ID}/actions`, {
          action_id: 'VERIFY_PAN',
          expected_snapshot_id: 'this-snapshot-id-does-not-exist',
          idempotency_key: '10000000-0000-0000-0000-000000000004',
          input: { pan_record: 'ZZZZZ0000Z' },
        });
        expect.unreachable('expected a 409');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        expect((err as ApiError).status).toBe(409);
      }
    });
  });

  describe('Switching between journeys mid-session never leaks state (Phase 17 regression)', () => {
    // A user who opens Lending, then Insurance, then comes back to Lending in
    // the SAME session/tab must see each journey's own data every time - not
    // whatever the other journey most recently mutated into.
    const LENDING_ID = '11111111-1111-1111-1111-111111111111';
    const INSURANCE_ID = '22222222-2222-2222-2222-222222222222';

    it('fetching Lending, then Insurance, then Lending again returns each journey\'s own fields every time', async () => {
      const lendingFirst = await apiClient.get<components['schemas']['JourneyStateResponse']>(
        `/journeys/${LENDING_ID}`
      );
      expect(lendingFirst.journey_type).toBe('LENDING');

      const insurance = await apiClient.get<components['schemas']['JourneyStateResponse']>(
        `/journeys/${INSURANCE_ID}`
      );
      expect(insurance.journey_type).toBe('INSURANCE');
      expect(insurance.fields.map((f) => f.key)).not.toEqual(
        expect.arrayContaining(['loan_amount', 'employer_name'])
      );

      const lendingSecond = await apiClient.get<components['schemas']['JourneyStateResponse']>(
        `/journeys/${LENDING_ID}`
      );
      expect(lendingSecond.journey_type).toBe('LENDING');
      expect(lendingSecond.fields.map((f) => f.key)).not.toContain('coverage_amount');
    });
  });
});
