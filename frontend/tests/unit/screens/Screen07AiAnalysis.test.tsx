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

  it('Expected Outcome is driven exclusively by consequence_preview - changing AI prose cannot change it (regression)', async () => {
    // 00_SHARED_CONTRACT.md §6 item 4: "Screen 7's Expected Outcome list
    // renders THIS object [SimulationPreview], not interpretation.summary.
    // The AI writes the sentence; the engine writes the outcome." This
    // proves it structurally: two evidence responses share the exact same
    // (deterministic) consequence_preview but have wildly different -
    // including a deliberately wrong/misleading - AI summary sentence. The
    // rendered Expected Outcome card must be byte-identical between them,
    // while the AI summary card differs, because they are wired to
    // different props (ConsequencePreview never receives `interpretation`
    // at all - see ConsequencePreview.tsx's props type).
    const misleadingSummaryResponse: EvidenceResponse = {
      ...mockEvidenceResponse,
      interpretation: {
        ...mockEvidenceResponse.interpretation,
        // Deliberately false/misleading prose relative to the real
        // consequence_preview above (which still shows bank_statement
        // blocked and NOT_READY) - if Expected Outcome ever read from this
        // instead of consequence_preview, this test would catch it.
        summary: 'Congratulations, your loan is fully approved and ready for disbursal!',
      },
    };

    const { unmount } = renderScreen7(undefined, {
      evidenceResponse: mockEvidenceResponse,
      journeyId: '11111111-1111-1111-1111-111111111111',
      actionId: 'UPLOAD_INCOME_PROOF',
      snapshotId: '11111111-1111-1111-1111-111111111111',
    });
    await screen.findByTestId('consequence-preview-card');
    const firstOutcomeHtml = screen.getByTestId('consequence-preview-card').innerHTML;
    unmount();

    renderScreen7(undefined, {
      evidenceResponse: misleadingSummaryResponse,
      journeyId: '11111111-1111-1111-1111-111111111111',
      actionId: 'UPLOAD_INCOME_PROOF',
      snapshotId: '11111111-1111-1111-1111-111111111111',
    });
    await screen.findByTestId('consequence-preview-card');
    const secondOutcomeHtml = screen.getByTestId('consequence-preview-card').innerHTML;

    // Expected Outcome is byte-identical regardless of what the AI wrote.
    expect(secondOutcomeHtml).toBe(firstOutcomeHtml);
    // The two responses' own consequence_preview is what differs matters
    // are absent from Expected Outcome - the misleading prose text itself
    // must never leak into the deterministic card.
    expect(screen.getByTestId('consequence-preview-card')).not.toHaveTextContent(/approved|disbursal/i);
    // It DOES still correctly show the real deterministic prediction: still
    // blocked / NOT_READY - proving this isn't just an empty/stale render.
    expect(screen.getByTestId('consequence-preview-card')).toHaveTextContent('Salary Account Verification');
    expect(screen.getByTestId('consequence-preview-card')).toHaveTextContent('Still Blocked');

    // Meanwhile the AI summary card DID pick up the different (if
    // misleading) prose - confirming the two are wired to genuinely
    // different data sources, not that summary is simply unused.
    expect(screen.getByTestId('ai-summary-card')).toHaveTextContent(/approved and ready for disbursal/i);
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

  it('never falls back to a hardcoded Lending action_id when no action can be determined (regression)', async () => {
    // Root cause: this screen used to fall back to the literal string
    // 'UPLOAD_INCOME_PROOF' (a Lending-specific action id) whenever neither
    // locationState.actionId nor evidenceResponse.proposed_action_id was set -
    // e.g. a non-Lending document that didn't match any pending requirement.
    // Applying would then silently submit the WRONG action for whatever
    // journey/pack the user was actually in. It must refuse instead.
    const user = userEvent.setup();
    const unmatchedEvidence: EvidenceResponse = {
      ...mockEvidenceResponse,
      proposed_action_id: null,
    };

    renderScreen7('/j/11111111-1111-1111-1111-111111111111/analysis', {
      evidenceResponse: unmatchedEvidence,
      journeyId: '11111111-1111-1111-1111-111111111111',
      snapshotId: '11111111-1111-1111-1111-111111111111',
      // deliberately no actionId
    });

    const continueBtn = await screen.findByTestId('continue-apply-btn');
    await user.click(continueBtn);

    expect(await screen.findByTestId('apply-error-banner')).toBeInTheDocument();
    expect(screen.queryByTestId('screen-08-stub')).not.toBeInTheDocument();
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
