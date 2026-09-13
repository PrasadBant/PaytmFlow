import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Screen07AiAnalysis } from '@/screens/Screen07AiAnalysis';
import type { components } from '@/api/types.gen';

type EvidenceResponse = components['schemas']['EvidenceResponse'];

const mockEvidenceResponse: EvidenceResponse = {
  evidence_id: '22222222-2222-2222-2222-222222222222',
  filename: 'payslip_august_2026.pdf',
  uploaded_at: '2026-09-12T10:05:00Z',
  size_bytes: 1428500,
  interpretation: {
    verified: true,
    confidence: 0.96,
    detected: [
      { key: 'monthly_income', label: 'Net Monthly Salary', display_value: '₹85,000' },
      { key: 'employer_name', label: 'Employer Organization', display_value: 'Paytm Technologies Ltd' },
    ],
    summary: 'Verified August 2026 salary slip confirming net in-hand credit of ₹85,000 from Paytm Technologies Ltd.',
    conflicts: [],
  },
  proposed_action_id: 'UPLOAD_INCOME_PROOF',
  consequence_preview: {
    newly_satisfied: [
      { key: 'monthly_income', label: 'Verified Monthly Income' },
    ],
    newly_unlocked: [
      { action_id: 'UPLOAD_BANK_STATEMENT', title: 'Upload Bank Statement' },
    ],
    still_blocked: [
      { key: 'bank_statement', label: 'Salary Account Verification' },
    ],
    predicted_readiness: 'NOT_READY',
    progress_before: { completed: 3, pending: 3, blockers: 1, total: 7 },
    progress_after: { completed: 4, pending: 2, blockers: 1, total: 7 },
  },
  requires_review: false,
};

function renderScreen7(
  initialEntry = '/j/11111111-1111-1111-1111-111111111111/analysis',
  locationState?: Record<string, unknown>
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter
        initialEntries={[
          {
            pathname: initialEntry,
            state: locationState ?? {
              evidenceResponse: mockEvidenceResponse,
              journeyId: '11111111-1111-1111-1111-111111111111',
              actionId: 'UPLOAD_INCOME_PROOF',
              snapshotId: '11111111-1111-1111-1111-111111111111',
            },
          },
        ]}
      >
        <Routes>
          <Route path="/j/:id/analysis" element={<Screen07AiAnalysis />} />
          <Route
            path="/j/:id/updated"
            element={<div data-testid="screen-08-stub">Updated Status Stub</div>}
          />
          <Route
            path="/j/:id/next"
            element={<div data-testid="screen-05-stub">Recommendation Stub</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Screen07AiAnalysis (F20)', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('renders heading, evidence card, plain text summary, and consequence preview', async () => {
    renderScreen7();

    expect(await screen.findByText('AI Document Analysis & Preview')).toBeInTheDocument();
    expect(screen.getByText('payslip_august_2026.pdf')).toBeInTheDocument();
    expect(screen.getByTestId('ai-summary-card')).toBeInTheDocument();
    expect(
      screen.getByText(/Verified August 2026 salary slip confirming net in-hand credit/i)
    ).toBeInTheDocument();
    expect(screen.getByTestId('consequence-preview-card')).toBeInTheDocument();
    expect(screen.getByTestId('continue-apply-btn')).toBeInTheDocument();
  });

  it('applies action on continue click and navigates to updated screen', async () => {
    const user = userEvent.setup();
    renderScreen7();

    const continueBtn = await screen.findByTestId('continue-apply-btn');
    await user.click(continueBtn);

    expect(await screen.findByTestId('screen-08-stub')).toBeInTheDocument();
  });

  it('renders review notice when requires_review is true', async () => {
    const reviewEvidence: EvidenceResponse = {
      ...mockEvidenceResponse,
      requires_review: true,
    };

    renderScreen7('/j/11111111-1111-1111-1111-111111111111/analysis', {
      evidenceResponse: reviewEvidence,
      journeyId: '11111111-1111-1111-1111-111111111111',
      snapshotId: '11111111-1111-1111-1111-111111111111',
    });

    expect(await screen.findByTestId('requires-review-notice')).toBeInTheDocument();
    expect(screen.queryByTestId('continue-apply-btn')).not.toBeInTheDocument();
  });

  it('renders fallback when navigated directly without evidence state', async () => {
    renderScreen7('/j/11111111-1111-1111-1111-111111111111/analysis', {});

    expect(await screen.findByText('No Evidence Upload to Analyze')).toBeInTheDocument();
  });

  it('strictly contains no prohibited words or percentage indicators', async () => {
    const { container } = renderScreen7();

    await screen.findByText('AI Document Analysis & Preview');

    const html = container.innerHTML;
    expect(html).not.toContain('%');
    expect(html).not.toMatch(/\bscore\b/i);
    expect(html).not.toMatch(/\bapproval\b/i);
    expect(html).not.toMatch(/\bprobability\b/i);
    expect(html).not.toMatch(/\beligibility\b/i);
    expect(html).not.toMatch(/\bguaranteed\b/i);
  });
});
