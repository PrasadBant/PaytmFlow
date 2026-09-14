import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import { Screen09CompleteJourney } from '@/screens/Screen09CompleteJourney';
import type { components } from '@/api/types.gen';

type JourneyStateResponse = components['schemas']['JourneyStateResponse'];

const mockReadyJourney: JourneyStateResponse = {
  journey_id: '11111111-1111-1111-1111-111111111111',
  journey_type: 'LENDING',
  schema_version: '1.0.0',
  snapshot_id: '55555555-5555-5555-5555-555555555555',
  version_number: 5,
  readiness: 'READY',
  status: 'COMPLETED',
  fields: [
    {
      key: 'loan_amount',
      label: 'Loan Amount',
      status: 'SATISFIED',
      display_value: '₹5,00,000',
    },
    {
      key: 'monthly_income',
      label: 'Verified Monthly Income',
      status: 'SATISFIED',
      display_value: '₹85,000',
    },
    {
      key: 'bank_statement',
      label: 'Salary Account Verification',
      status: 'SATISFIED',
      display_value: 'Verified (HDFC Bank)',
    },
  ],
  progress: {
    completed: 3,
    pending: 0,
    blockers: 0,
    total: 3,
  },
  display: {
    title: 'Personal Loan',
    summary: '₹5,00,000 · Home Renovation',
  },
  ui_labels: {
    completion_heading: 'Application Ready!',
    completion_subtext: 'All 3 verification steps completed. You may now proceed to final handoff.',
  },
  updated_at: '2026-09-12T10:20:00Z',
};

const mockNotReadyJourney: JourneyStateResponse = {
  ...mockReadyJourney,
  readiness: 'NOT_READY',
  status: 'IN_PROGRESS',
  progress: {
    completed: 2,
    pending: 0,
    blockers: 1,
    total: 3,
  },
};

function renderScreen9(
  initialEntry = '/j/11111111-1111-1111-1111-111111111111/complete',
  journeyData: JourneyStateResponse = mockReadyJourney
) {
  server.use(
    http.get('*/api/v1/journeys/:id', () => {
      return HttpResponse.json(journeyData);
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
          <Route path="/j/:id/complete" element={<Screen09CompleteJourney />} />
          <Route path="/j/:id" element={<div data-testid="screen-04-stub">Current Status Stub</div>} />
          <Route path="/my-journeys" element={<div data-testid="my-journeys-stub">My Journeys Stub</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Screen09CompleteJourney (F23)', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('renders completion title, checklist, and ready badge when journey is READY', async () => {
    renderScreen9();

    expect(await screen.findByTestId('completion-title')).toHaveTextContent('Application Ready!');
    expect(screen.getByText('Verification Complete')).toBeInTheDocument();
    expect(screen.getByText('Snapshot v5')).toBeInTheDocument();
    // The checklist is the reference's fixed 4-line generic completion summary
    // (each line is a true corollary of readiness === READY for any pack, not
    // per-field business data), not a per-field listing.
    expect(screen.getByTestId('verification-checklist-section')).toBeInTheDocument();
    expect(screen.getByText('All mandatory fields completed')).toBeInTheDocument();
    expect(screen.getByText('No blockers remaining')).toBeInTheDocument();
    expect(screen.getByText('Documents verified')).toBeInTheDocument();
    expect(screen.getByText('Ready for provider handoff')).toBeInTheDocument();
    expect(screen.queryByText('Verified Monthly Income')).not.toBeInTheDocument();
    expect(screen.getByTestId('proceed-handoff-btn')).toBeInTheDocument();
    expect(screen.getByText('Proceed to Handoff')).toBeInTheDocument();
    expect(screen.getByTestId('review-app-btn')).toBeInTheDocument();
  });

  it('displays "Proceed to Handoff" and never "Proceed to Submit"', async () => {
    const { container } = renderScreen9();

    expect(await screen.findByTestId('proceed-handoff-btn')).toHaveTextContent('Proceed to Handoff');
    expect(container.innerHTML).not.toMatch(/Proceed to Submit/i);
  });

  it('does not contain inappropriate submission-oriented language', async () => {
    const { container } = renderScreen9();

    await screen.findByTestId('completion-title');

    const html = container.innerHTML;
    // "submission" is permitted only inside the explicit disclaimer sentence
    // stating that no submission takes place; it must not appear as an
    // affirmative claim that PaytmFlow itself is submitting anything.
    expect(html).not.toMatch(/proceed to submit/i);
    expect(html).not.toMatch(/submit your application/i);
    expect(html).not.toMatch(/ready for submission/i);
  });

  it('renders not ready guard banner when journey readiness is NOT_READY', async () => {
    renderScreen9('/j/11111111-1111-1111-1111-111111111111/complete', mockNotReadyJourney);

    expect(await screen.findByTestId('not-ready-guard-banner')).toBeInTheDocument();
    expect(screen.getByText('Journey Not Ready for Completion')).toBeInTheDocument();
    expect(screen.queryByTestId('proceed-handoff-btn')).not.toBeInTheDocument();
  });

  it('opens handoff modal explaining no submission occurs in this workspace and navigates to My Journeys', async () => {
    const user = userEvent.setup();
    renderScreen9();

    const handoffBtn = await screen.findByTestId('proceed-handoff-btn');
    await user.click(handoffBtn);

    expect(await screen.findByText('Application Package Ready for Handoff')).toBeInTheDocument();
    expect(screen.getByTestId('handoff-modal-content')).toHaveTextContent(
      'No actual financial or credit submission takes place inside this application.'
    );

    const doneBtn = screen.getByTestId('handoff-done-btn');
    await user.click(doneBtn);

    expect(await screen.findByTestId('my-journeys-stub')).toBeInTheDocument();
  });

  it('closes the handoff modal via the Close button without navigating or changing state', async () => {
    const user = userEvent.setup();
    renderScreen9();

    const handoffBtn = await screen.findByTestId('proceed-handoff-btn');
    await user.click(handoffBtn);

    expect(await screen.findByText('Application Package Ready for Handoff')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Close' }));

    expect(screen.queryByText('Application Package Ready for Handoff')).not.toBeInTheDocument();
    // Still on Screen 9 - closing the modal does not navigate away.
    expect(screen.getByTestId('screen-09-complete-journey')).toBeInTheDocument();
  });

  it('closes the handoff modal on Escape key press', async () => {
    const user = userEvent.setup();
    renderScreen9();

    const handoffBtn = await screen.findByTestId('proceed-handoff-btn');
    await user.click(handoffBtn);

    expect(await screen.findByText('Application Package Ready for Handoff')).toBeInTheDocument();

    await user.keyboard('{Escape}');

    expect(screen.queryByText('Application Package Ready for Handoff')).not.toBeInTheDocument();
  });

  it('navigates to journey overview on "Review Application" click', async () => {
    const user = userEvent.setup();
    renderScreen9();

    const reviewBtn = await screen.findByTestId('review-app-btn');
    await user.click(reviewBtn);

    expect(await screen.findByTestId('screen-04-stub')).toBeInTheDocument();
  });

  it('renders the identical generic checklist for a completely different pack (no per-pack branching)', async () => {
    const kycReadyJourney: JourneyStateResponse = {
      ...mockReadyJourney,
      journey_type: 'KYC',
      fields: [
        { key: 'aadhaar_verified', label: 'Aadhaar Verification', status: 'SATISFIED' },
      ],
      display: { title: 'Video & Biometric KYC', summary: 'Wallet Upgrade' },
    };
    renderScreen9('/j/11111111-1111-1111-1111-111111111111/complete', kycReadyJourney);

    expect(await screen.findByTestId('completion-title')).toHaveTextContent('Application Ready!');
    expect(screen.getByText('All mandatory fields completed')).toBeInTheDocument();
    expect(screen.getByText('No blockers remaining')).toBeInTheDocument();
    expect(screen.getByText('Documents verified')).toBeInTheDocument();
    expect(screen.getByText('Ready for provider handoff')).toBeInTheDocument();
    expect(screen.queryByText('Aadhaar Verification')).not.toBeInTheDocument();
  });

  it('strictly contains no prohibited words (approv, score, gauge, etc.) or %', async () => {
    const { container } = renderScreen9();

    await screen.findByTestId('completion-title');

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
