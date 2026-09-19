import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { EvidenceComparisonWorkspace } from './EvidenceComparisonWorkspace';
import type { ReviewCaseDetail } from '@/api/hooks/useReview';

function buildDetail(provider: string | null): ReviewCaseDetail {
  return {
    case_id: 'aaaaaaaa-1024-4000-8000-000000001024',
    case_number: 'PF-DEMO-1024',
    journey_id: '11111111-1111-1111-1111-111111111111',
    journey_type: 'LENDING',
    journey_display_name: 'Personal Loan',
    field_key: 'monthly_income',
    reason_code: 'INCOME_MISMATCH',
    reason_title: 'Bank statement credit differs from salary slip',
    reason_description: 'Two submitted sources contain different income values.',
    priority: 'MEDIUM',
    status: 'REVIEW_REQUIRED',
    case_version: 1,
    assigned_reviewer: null,
    is_locked: false,
    resolution_type: null,
    resolution_reason: null,
    resolution_notes: null,
    requested_information: null,
    escalation_reason: null,
    created_at: '2026-09-19T04:00:00Z',
    updated_at: '2026-09-19T04:00:00Z',
    resolved_at: null,
    journey_context: {
      journey_id: '11111111-1111-1111-1111-111111111111',
      journey_type: 'LENDING',
      readiness: 'NEEDS_REVIEW',
      display: { title: 'Personal Loan' },
      progress: { completed: 3, pending: 2, blockers: 1, total: 6 },
      fields: [],
    } as unknown as ReviewCaseDetail['journey_context'],
    evidence: [
      {
        evidence_id: 'bbbbbbbb-0001-4000-8000-000000000001',
        doc_type: 'SALARY_SLIP',
        filename: 'salary_slip_sept.pdf',
        uploaded_at: '2026-09-19T03:58:00Z',
        verified: true,
        confidence: 0.91,
        extracted_values: { monthly_income: 50000 },
        provider,
      },
    ],
  } as unknown as ReviewCaseDetail;
}

describe('EvidenceComparisonWorkspace - source traceability', () => {
  it('renders a source label for a known AI provider', () => {
    render(<EvidenceComparisonWorkspace detail={buildDetail('sarvam')} />);
    expect(screen.getByText('Sarvam Vision')).toBeInTheDocument();
  });

  it('renders the raw provider string for an unrecognized provider value', () => {
    render(<EvidenceComparisonWorkspace detail={buildDetail('some_new_provider')} />);
    expect(screen.getByText('some_new_provider')).toBeInTheDocument();
  });

  it('renders no source line when provider is null', () => {
    render(<EvidenceComparisonWorkspace detail={buildDetail(null)} />);
    expect(screen.queryByText('Source:')).not.toBeInTheDocument();
  });
});
