import { describe, it, expect } from 'vitest';
import type { components, paths, operations } from './types.gen';

describe('API Generated Types Contract Verification', () => {
  it('exposes core schema types from OpenAPI contract', () => {
    type JourneyStateResponse = components['schemas']['JourneyStateResponse'];
    type JourneyPackSummary = components['schemas']['JourneyPackSummary'];
    type JourneyPackDetail = components['schemas']['JourneyPackDetail'];
    type ActionOption = components['schemas']['ActionOption'];
    type RecommendationResponse = components['schemas']['RecommendationResponse'];
    type EvidenceResponse = components['schemas']['EvidenceResponse'];
    type ActionResponse = components['schemas']['ActionResponse'];
    type JourneyDiff = components['schemas']['JourneyDiff'];
    type ErrorEnvelope = components['schemas']['ErrorEnvelope'];
    type ProgressCounts = components['schemas']['ProgressCounts'];
    type Readiness = components['schemas']['Readiness'];
    type JourneyType = components['schemas']['JourneyType'];

    const mockReadiness: Readiness = 'READY';
    const mockJourneyType: JourneyType = 'LENDING';
    const mockProgress: ProgressCounts = {
      completed: 3,
      pending: 4,
      blockers: 1,
      total: 7,
    };

    const mockSummary: Partial<JourneyPackSummary> = {
      journey_type: mockJourneyType,
      display_name: 'Personal Loan',
    };

    const mockDetail: Partial<JourneyPackDetail> = {
      journey_type: mockJourneyType,
      goal_schema: [],
    };

    const mockAction: ActionOption = {
      action_id: 'UPLOAD_INCOME_PROOF',
      title: 'Upload Salary Slip',
      kind: 'EVIDENCE',
      why: 'Verifies income level',
      unlocks: ['LOAN_AMOUNT'],
    };

    const mockState: Partial<JourneyStateResponse> = {
      journey_id: '123e4567-e89b-12d3-a456-426614174000',
      journey_type: mockJourneyType,
      version_number: 1,
      readiness: mockReadiness,
      progress: mockProgress,
    };

    const mockRecommendation: Partial<RecommendationResponse> = {
      snapshot_id: '123e4567-e89b-12d3-a456-426614174000',
      readiness: mockReadiness,
      recommendation: mockAction,
      alternatives: [],
      minimum_path_length: 1,
    };

    const mockEvidence: Partial<EvidenceResponse> = {
      evidence_id: '123e4567-e89b-12d3-a456-426614174000',
      filename: 'payslip.pdf',
      uploaded_at: '2026-09-12T00:00:00Z',
      requires_review: false,
    };

    const mockDiff: Partial<JourneyDiff> = {
      from_version: 1,
      to_version: 2,
      fields_changed: [],
      actions_unlocked: [],
      actions_removed: [],
    };

    const mockActionResponse: Partial<ActionResponse> = {
      journey: mockState as JourneyStateResponse,
      diff: mockDiff as JourneyDiff,
    };

    const mockError: ErrorEnvelope = {
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Invalid input',
      },
    };

    expect(mockReadiness).toBe('READY');
    expect(mockJourneyType).toBe('LENDING');
    expect(mockProgress.total).toBe(7);
    expect(mockSummary.display_name).toBe('Personal Loan');
    expect(mockDetail.journey_type).toBe('LENDING');
    expect(mockAction.action_id).toBe('UPLOAD_INCOME_PROOF');
    expect(mockState.readiness).toBe('READY');
    expect(mockRecommendation.minimum_path_length).toBe(1);
    expect(mockEvidence.filename).toBe('payslip.pdf');
    expect(mockDiff.from_version).toBe(1);
    expect(mockActionResponse.journey?.version_number).toBe(1);
    expect(mockError.error.code).toBe('VALIDATION_ERROR');
  });

  it('exposes API paths and operations from OpenAPI contract', () => {
    type SessionOp = operations['getSession'];
    type JourneysListOp = operations['listJourneys'];
    type CreateJourneyOp = operations['createJourney'];
    type GetJourneyOp = operations['getJourney'];
    type RecommendationOp = operations['getRecommendation'];
    type UploadEvidenceOp = operations['uploadEvidence'];
    type ApplyActionOp = operations['applyAction'];
    type SubmitClarificationOp = operations['submitClarification'];
    type GetDiffOp = operations['getDiff'];

    type SessionPath = paths['/api/v1/session'];
    type JourneysPath = paths['/api/v1/journeys'];
    type EvidencePath = paths['/api/v1/journeys/{journey_id}/evidence'];
    type ActionsPath = paths['/api/v1/journeys/{journey_id}/actions'];
    type ClarificationsPath = paths['/api/v1/journeys/{journey_id}/clarifications'];

    const operationKeys: Array<keyof operations> = [
      'getSession' as keyof operations,
      'listJourneys' as keyof operations,
      'createJourney' as keyof operations,
      'getJourney' as keyof operations,
      'getRecommendation' as keyof operations,
      'uploadEvidence' as keyof operations,
      'applyAction' as keyof operations,
      'submitClarification' as keyof operations,
      'getDiff' as keyof operations,
    ];

    const pathKeys: Array<keyof paths> = [
      '/api/v1/session',
      '/api/v1/journeys',
      '/api/v1/journeys/{journey_id}/evidence',
      '/api/v1/journeys/{journey_id}/actions',
      '/api/v1/journeys/{journey_id}/clarifications',
    ];

    // Reference types to satisfy compiler
    const testTypes: [
      SessionOp?,
      JourneysListOp?,
      CreateJourneyOp?,
      GetJourneyOp?,
      RecommendationOp?,
      UploadEvidenceOp?,
      ApplyActionOp?,
      SubmitClarificationOp?,
      GetDiffOp?,
      SessionPath?,
      JourneysPath?,
      EvidencePath?,
      ActionsPath?,
      ClarificationsPath?,
    ] = [];

    expect(operationKeys.length).toBe(9);
    expect(pathKeys.length).toBe(5);
    expect(testTypes.length).toBe(0);
  });
});
