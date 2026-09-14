import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import { Screen04CurrentStatus } from '@/screens/Screen04CurrentStatus';
import type { components } from '@/api/types.gen';

type JourneyStateResponse = components['schemas']['JourneyStateResponse'];

function renderWithProviders(initialRoute = '/j/11111111-1111-1111-1111-111111111111') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <Routes>
          <Route path="/j/:id" element={<Screen04CurrentStatus />} />
          <Route path="/j/:id/next" element={<div data-testid="next-screen">Recommendation Screen</div>} />
          <Route path="/j/:id/act/:actionId" element={<div data-testid="act-screen">Action Screen</div>} />
          <Route path="/my-journeys" element={<div data-testid="my-journeys-screen">My Journeys</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Screen04CurrentStatus (F14)', () => {
  it('renders heading, progress ring, and legend breakdown', async () => {
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Your Current Status')).toBeInTheDocument();
    });

    // Verify Progress Ring
    expect(screen.getByTestId('progress-ring')).toBeInTheDocument();
    expect(screen.getByTestId('progress-ring-count')).toHaveTextContent('3/7');
    expect(screen.getByTestId('progress-ring-label')).toHaveTextContent('Completed');

    // Verify Legend. These must match the fixture's `fields` array 1:1 (3
    // SATISFIED, 4 BLOCKED, 0 otherwise) - regression coverage for a fixture
    // authoring bug where `progress` mislabeled 3 of the 4 actually-BLOCKED
    // fields as "pending", contradicting the "Blocked Items (4)" list
    // rendered from the same fields array on the same screen.
    expect(screen.getByText('3 Completed')).toBeInTheDocument();
    expect(screen.getByText('0 Pending')).toBeInTheDocument();
    expect(screen.getByText('4 Blockers')).toBeInTheDocument();
  });

  it('renders blocked items with Resolve buttons', async () => {
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText(/Blocked Items/i)).toBeInTheDocument();
    });

    expect(screen.getByText('Verified Monthly Income')).toBeInTheDocument();
    expect(screen.getByText('Salary Account Verification')).toBeInTheDocument();
    expect(screen.getByText('PAN Card Verification')).toBeInTheDocument();
    expect(screen.getByText('Current Residential Address')).toBeInTheDocument();

    const resolveButtons = screen.getAllByRole('button', { name: /Resolve/i });
    expect(resolveButtons.length).toBeGreaterThan(0);
  });

  it('navigates to action route when Resolve button is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Verified Monthly Income')).toBeInTheDocument();
    });

    const incomeResolveBtn = screen.getByRole('button', {
      name: /Resolve Verified Monthly Income/i,
    });
    await user.click(incomeResolveBtn);

    await waitFor(() => {
      expect(screen.getByTestId('act-screen')).toBeInTheDocument();
    });
  });

  it('navigates to recommendation screen when Recommended Next Step is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Your Current Status')).toBeInTheDocument();
    });

    const nextStepBtn = screen.getByRole('button', {
      name: /Recommended Next Step/i,
    });
    await user.click(nextStepBtn);

    await waitFor(() => {
      expect(screen.getByTestId('next-screen')).toBeInTheDocument();
    });
  });

  it('toggles completed requirements disclosure', async () => {
    const user = userEvent.setup();
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText(/Completed Requirements/i)).toBeInTheDocument();
    });

    const toggleButton = screen.getByRole('button', { name: /Completed Requirements/i });

    // Expand
    await user.click(toggleButton);
    expect(screen.getByText('Loan Amount')).toBeInTheDocument();
    expect(screen.getByText('Repayment Tenure')).toBeInTheDocument();
    expect(screen.getByText('Employment Classification')).toBeInTheDocument();

    // Collapse
    await user.click(toggleButton);
    expect(screen.queryByText('Repayment Tenure')).not.toBeInTheDocument();
  });

  it('renders NeedsReviewCard for an AMBIGUOUS field on a resumed/navigated-to journey', async () => {
    // Screen 4 is exactly where resume_screen: NEEDS_REVIEW sends a returning applicant,
    // and it must surface the pending clarification standalone here - not only right
    // after the action that caused it (previously only Screen 7/8 wired NeedsReviewCard).
    const needsReviewJourney: JourneyStateResponse = {
      journey_id: '11111111-1111-1111-1111-111111111111',
      journey_type: 'LENDING',
      schema_version: '1.0.0',
      snapshot_id: 'cccccccc-3333-3333-3333-333333333333',
      version_number: 3,
      readiness: 'NEEDS_REVIEW',
      status: 'IN_PROGRESS',
      fields: [
        {
          key: 'monthly_income',
          label: 'Verified Monthly Income',
          status: 'AMBIGUOUS',
          explanation: 'Bank statement salary credit differs from declared amount.',
          ambiguity: {
            ambiguity_id: 'INCOME_MISMATCH',
            reason: 'Bank statement reflects ₹80,000 average monthly credit, while salary slip indicates ₹85,000.',
            question: 'Which amount reflects your recurring monthly net base salary?',
            answer_type: 'CHOICE',
            choices: [
              { value: 85000, label: '₹85,000 (Base Salary with deductions)' },
              { value: 80000, label: '₹80,000 (Average in-hand deposit)' },
            ],
          },
        },
        {
          key: 'pan_verification',
          label: 'PAN Card Verification',
          status: 'BLOCKED',
          explanation: 'PAN required for KYC.',
          resolve_action_id: 'UPLOAD_PAN',
          mandatory: true,
        },
      ],
      progress: { completed: 0, pending: 1, blockers: 1, total: 2 },
      display: { title: 'Personal Loan', summary: '₹5,00,000 · Home Renovation' },
      updated_at: '2026-09-12T10:10:00Z',
    };

    server.use(
      http.get('*/api/v1/journeys/:journey_id', () => HttpResponse.json(needsReviewJourney))
    );

    renderWithProviders();

    expect(await screen.findByTestId('needs-review-card')).toBeInTheDocument();
    expect(
      screen.getByText('Which amount reflects your recurring monthly net base salary?')
    ).toBeInTheDocument();

    // The AMBIGUOUS field is handled by NeedsReviewCard, not the generic BlockerCard
    // "Resolve" flow (which offers no targeted clarification question) - it must not
    // also appear duplicated in Blocked Items.
    expect(screen.getByText('Blocked Items (1)')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Resolve Verified Monthly Income/i })).not.toBeInTheDocument();
  });

  it('strictly asserts absence of prohibited words and % character', async () => {
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Your Current Status')).toBeInTheDocument();
    });

    const bodyText = document.body.textContent || '';
    const bodyHtml = document.body.innerHTML || '';

    // No % symbol in text/html
    expect(bodyText).not.toContain('%');
    expect(bodyHtml).not.toContain('%');

    // No prohibited words
    expect(bodyText).not.toMatch(/\bscore\b/i);
    expect(bodyText).not.toMatch(/\bapproval\b/i);
    expect(bodyText).not.toMatch(/\bprobability\b/i);
    expect(bodyText).not.toMatch(/\beligibility\b/i);
    expect(bodyText).not.toMatch(/\bguaranteed\b/i);
  });
});
