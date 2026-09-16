import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import { Screen10MyJourneys } from '@/screens/Screen10MyJourneys';
import type { JourneyListItem } from '@/api/hooks/useJourneyList';

const mockJourneys: JourneyListItem[] = [
  {
    journey_id: '11111111-1111-1111-1111-111111111111',
    journey_type: 'LENDING',
    display_name: 'Personal Loan',
    icon: 'rupee',
    title: '₹5,00,000 Personal Loan',
    summary: '4/7 steps completed — Income verified',
    status: 'IN_PROGRESS',
    readiness: 'NOT_READY',
    progress: { completed: 4, pending: 2, blockers: 1, total: 7 },
    updated_at: '2026-09-12T10:06:00Z',
    resume_screen: 'STATUS',
  },
  {
    journey_id: '22222222-2222-2222-2222-222222222222',
    journey_type: 'INSURANCE',
    display_name: 'Health & Life Insurance',
    icon: 'shield',
    title: '₹10,00,000 Health Comprehensive',
    summary: 'Medical declaration under review',
    status: 'NEEDS_REVIEW',
    readiness: 'NEEDS_REVIEW',
    progress: { completed: 2, pending: 2, blockers: 0, total: 4 },
    updated_at: '2026-09-11T16:30:00Z',
    resume_screen: 'NEEDS_REVIEW',
  },
  {
    journey_id: '33333333-3333-3333-3333-333333333333',
    journey_type: 'KYC',
    display_name: 'Video & Biometric KYC',
    icon: 'id',
    title: 'Full Wallet KYC Upgrade',
    summary: 'All verifications complete',
    status: 'COMPLETED',
    readiness: 'READY',
    progress: { completed: 5, pending: 0, blockers: 0, total: 5 },
    updated_at: '2026-09-10T09:15:00Z',
    resume_screen: 'COMPLETE',
  },
];

function renderScreen10(
  initialEntry = '/my-journeys',
  journeysData: JourneyListItem[] = mockJourneys
) {
  server.use(
    http.get('*/api/v1/journeys', () => {
      return HttpResponse.json({ journeys: journeysData });
    })
  );

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/my-journeys" element={<Screen10MyJourneys />} />
          <Route path="/j/:id" element={<div data-testid="screen-04-stub">Status Stub</div>} />
          <Route path="/j/:id/next" element={<div data-testid="screen-05-stub">Recommendation Stub</div>} />
          <Route path="/j/:id/complete" element={<div data-testid="screen-09-stub">Complete Stub</div>} />
          <Route path="/start" element={<div data-testid="screen-02-stub">Start Stub</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Screen10MyJourneys (F24)', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('resumes a journey via keyboard alone - Tab then Enter (regression)', async () => {
    // Real-user QA finding: this row - the primary way to resume a
    // journey - was a plain <div onClick>, unreachable and unusable via
    // keyboard alone (no Tab stop, no Enter/Space activation).
    const user = userEvent.setup();
    renderScreen10();

    const row = await screen.findByTestId('journey-row-11111111-1111-1111-1111-111111111111');
    expect(row).toHaveAttribute('tabIndex', '0');
    expect(row).toHaveAttribute('role', 'button');

    row.focus();
    expect(row).toHaveFocus();
    await user.keyboard('{Enter}');

    // journey.resume_screen: 'STATUS' -> navigates to /j/:id
    expect(await screen.findByTestId('screen-04-stub')).toBeInTheDocument();
  });

  it('renders title, tabs, start journey button, and all journeys by default', async () => {
    renderScreen10();

    expect(await screen.findByRole('heading', { name: 'My Journeys' })).toBeInTheDocument();
    expect(screen.getByTestId('start-journey-btn')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /All/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /In Progress/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Needs Review/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Completed/i })).toBeInTheDocument();

    expect(await screen.findByTestId('journey-row-11111111-1111-1111-1111-111111111111')).toBeInTheDocument();
    expect(screen.getByTestId('journey-row-22222222-2222-2222-2222-222222222222')).toBeInTheDocument();
    expect(screen.getByTestId('journey-row-33333333-3333-3333-3333-333333333333')).toBeInTheDocument();
    expect(screen.getByText('4/7 Completed')).toBeInTheDocument();
  });

  it('filters journeys when switching tabs', async () => {
    const user = userEvent.setup();
    renderScreen10();

    expect(await screen.findByTestId('journey-row-11111111-1111-1111-1111-111111111111')).toBeInTheDocument();

    // Switch to Completed tab
    const completedTab = screen.getByRole('tab', { name: /Completed/i });
    await user.click(completedTab);

    await waitFor(() => {
      expect(screen.queryByTestId('journey-row-11111111-1111-1111-1111-111111111111')).not.toBeInTheDocument();
      expect(screen.queryByTestId('journey-row-22222222-2222-2222-2222-222222222222')).not.toBeInTheDocument();
      expect(screen.getByTestId('journey-row-33333333-3333-3333-3333-333333333333')).toBeInTheDocument();
    });
  });

  it('honours initial ?tab= query parameter', async () => {
    renderScreen10('/my-journeys?tab=NEEDS_REVIEW');

    expect(await screen.findByTestId('journey-row-22222222-2222-2222-2222-222222222222')).toBeInTheDocument();
    expect(screen.queryByTestId('journey-row-11111111-1111-1111-1111-111111111111')).not.toBeInTheDocument();
  });

  it('navigates to the server-designated resume_screen when Resume is clicked', async () => {
    const user = userEvent.setup();
    renderScreen10();

    // Completed journey has resume_screen: 'COMPLETE'
    const completeResumeBtn = await screen.findByTestId('resume-btn-33333333-3333-3333-3333-333333333333');
    await user.click(completeResumeBtn);

    expect(await screen.findByTestId('screen-09-stub')).toBeInTheDocument();
  });

  it('renders empty state when no journeys match active tab', async () => {
    renderScreen10('/my-journeys', []);

    expect(await screen.findByTestId('empty-state')).toBeInTheDocument();
    expect(screen.getByText('No Financial Journeys Found')).toBeInTheDocument();
  });

  it('renders the real display_name/summary/updated_at for every pack - never a hardcoded LENDING fallback', async () => {
    // This screen previously hardcoded a journey_type-keyed switch of fixed row
    // titles (e.g. always "Loan / Lending" for LENDING) and a "Personal Loan •
    // ₹ 5,00,000" fallback whenever `summary` was falsy - both journey-specific
    // branching AND fabricated business data, ignoring the real (contract-required)
    // display_name/summary/updated_at fields. Assert a non-LENDING pack renders its
    // own real values with nothing hardcoded standing in for them.
    const investmentJourney: JourneyListItem = {
      journey_id: '99999999-9999-9999-9999-999999999999',
      journey_type: 'INVESTMENT',
      display_name: 'Investment / Wealth',
      icon: 'chart',
      title: 'Mutual Fund SIP Setup',
      summary: 'SIP amount ₹10,000 · Equity Fund',
      status: 'IN_PROGRESS',
      readiness: 'NOT_READY',
      progress: { completed: 1, pending: 2, blockers: 0, total: 3 },
      updated_at: '2026-09-10T08:00:00Z',
      resume_screen: 'STATUS',
    };

    renderScreen10('/my-journeys', [investmentJourney]);

    expect(await screen.findByTestId('journey-row-99999999-9999-9999-9999-999999999999')).toBeInTheDocument();
    expect(screen.getByText('Investment / Wealth')).toBeInTheDocument();
    expect(screen.getByText('SIP amount ₹10,000 · Equity Fund')).toBeInTheDocument();
    expect(screen.queryByText(/Personal Loan/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/5,00,000/i)).not.toBeInTheDocument();
  });

  it('strictly contains no prohibited words (approv, score, gauge, etc.) or %', async () => {
    const { container } = renderScreen10();

    await screen.findByRole('heading', { name: 'My Journeys' });

    const html = container.innerHTML;
    expect(html).not.toContain('%');
    expect(html).not.toMatch(/\bscore\b/i);
    expect(html).not.toMatch(/\bapproval\b/i);
    expect(html).not.toMatch(/\bapproved\b/i);
    expect(html).not.toMatch(/\bprobability\b/i);
    expect(html).not.toMatch(/\beligibility\b/i);
    expect(html).not.toMatch(/\bguaranteed\b/i);
  });
});
