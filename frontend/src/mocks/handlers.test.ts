import { describe, it, expect } from 'vitest';
import { apiClient } from '../api/client';
import { setOverrideScenario } from './scenarios';
import type { components } from '../api/types.gen';
import { ApiError } from '../api/errors';

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
    const formData = new FormData();
    formData.append('doc_type', 'SALARY_SLIP');
    formData.append('expected_snapshot_id', 'aaaaaaaa-1111-1111-1111-111111111111');

    const evidence = await apiClient.postForm<components['schemas']['EvidenceResponse']>(
      '/journeys/11111111-1111-1111-1111-111111111111/evidence',
      formData
    );
    expect(evidence.interpretation.verified).toBe(true);
    expect(evidence.consequence_preview).toBeDefined();
    expect(evidence.consequence_preview?.newly_satisfied[0].key).toBe('monthly_income');
    expect(evidence.requires_review).toBe(false);
  });

  it('Scenario "needsreview": evidence upload triggers requires_review and conflicts', async () => {
    setOverrideScenario('needsreview');
    const formData = new FormData();
    formData.append('doc_type', 'BANK_STATEMENT');
    formData.append('expected_snapshot_id', 'bbbbbbbb-2222-2222-2222-222222222222');

    const evidence = await apiClient.postForm<components['schemas']['EvidenceResponse']>(
      '/journeys/11111111-1111-1111-1111-111111111111/evidence',
      formData
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
});
