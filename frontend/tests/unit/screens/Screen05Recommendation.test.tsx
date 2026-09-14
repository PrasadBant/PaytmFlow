import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, afterEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import { Screen05Recommendation } from '@/screens/Screen05Recommendation';
import { setOverrideScenario } from '@/mocks/scenarios';

function renderWithProviders(initialRoute = '/j/11111111-1111-1111-1111-111111111111/next') {
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
          <Route path="/j/:id" element={<div data-testid="status-screen">Status Screen</div>} />
          <Route path="/j/:id/next" element={<Screen05Recommendation />} />
          <Route path="/j/:id/act/:actionId" element={<div data-testid="act-screen">Action Screen</div>} />
          <Route path="/j/:id/complete" element={<div data-testid="complete-screen">Complete Screen</div>} />
          <Route path="/start" element={<div data-testid="start-screen">Start Screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Screen05Recommendation (F16)', () => {
  afterEach(() => {
    setOverrideScenario(null);
  });

  it('renders recommended next step card, alternatives list, and assistant help card', async () => {
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Recommended Next Step')).toBeInTheDocument();
    });

    // Recommendation card - the reference design has no "Recommended Next Action"
    // badge, just the icon/title/description/button.
    expect(screen.getByText('Upload Salary Slip')).toBeInTheDocument();
    expect(screen.queryByText('Recommended Next Action')).not.toBeInTheDocument();

    // Alternatives list
    expect(screen.getByText(/Alternative Options/i)).toBeInTheDocument();
    expect(screen.getByText('Adjust Loan Tenure')).toBeInTheDocument();
    expect(screen.getByText('Update Employer Details')).toBeInTheDocument();

    // Assistant Card
    expect(screen.getByText('Need Help with this Step?')).toBeInTheDocument();
  });

  it('navigates to action route when primary action CTA is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Upload Salary Slip')).toBeInTheDocument();
    });

    const ctaBtn = screen.getByRole('button', {
      name: /Take action: Upload Salary Slip/i,
    });
    await user.click(ctaBtn);

    await waitFor(() => {
      expect(screen.getByTestId('act-screen')).toBeInTheDocument();
    });
  });

  it('opens the FormActionModal (not the act/:actionId screen) when a FORM-kind alternative is selected', async () => {
    // "Adjust Loan Tenure" is a FORM-kind action. Per contract, kind tells Dev1 which
    // UI to open: EVIDENCE -> Screen 6, FORM -> generic action modal rendered from
    // input_schema, CLARIFICATION -> NeedsReviewCard. Screen 5 already holds the full
    // ActionOption (incl. input_schema), so FORM opens inline instead of navigating away.
    const user = userEvent.setup();
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Adjust Loan Tenure')).toBeInTheDocument();
    });

    const selectBtn = screen.getByRole('button', {
      name: /Select alternative action: Adjust Loan Tenure/i,
    });
    await user.click(selectBtn);

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText(/Tenure in Months/i)).toBeInTheDocument();
    expect(screen.queryByTestId('act-screen')).not.toBeInTheDocument();
  });

  it('a SCHEDULING/CONSENT/VIDEO_VERIFICATION-classified FORM action navigates to Screen 6, not the generic modal (consistency regression)', async () => {
    // Bug: Screen 4's "Resolve" link already sends a SCHEDULE_*/SIGN_*/
    // ACCEPT_*/*MANDATE*/*VIDEO* action to Screen 6's purpose-built
    // SchedulingPicker/ConsentPanel/VideoVerificationFlow, but selecting the
    // exact same action from HERE (Screen 5's recommendation/alternatives)
    // used to always open the bare generic FormActionModal instead - the
    // same action rendered two different, inconsistent UIs depending on
    // which screen the user reached it from. Only a genuinely generic FORM
    // action (like "Adjust Loan Tenure" above) should still open the modal.
    server.use(
      http.get('*/api/v1/journeys/:journey_id/recommendation', () =>
        HttpResponse.json({
          snapshot_id: 'aaaaaaaa-1111-1111-1111-111111111111',
          readiness: 'NOT_READY',
          recommendation: {
            action_id: 'SCHEDULE_UNDERWRITING_CALL',
            title: 'Medical Underwriting Call',
            kind: 'FORM',
            why: 'Select a time slot for the tele-medical consultation',
            unlocks: ['tele_underwriting_scheduled'],
          },
          alternatives: [],
          minimum_path_length: 1,
          source: 'AI_RANKED',
        })
      )
    );

    const user = userEvent.setup();
    renderWithProviders();

    const ctaBtn = await screen.findByRole('button', {
      name: /Take action: Medical Underwriting Call/i,
    });
    await user.click(ctaBtn);

    await waitFor(() => {
      expect(screen.getByTestId('act-screen')).toBeInTheDocument();
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders DeadEndState when scenario forces deadend', async () => {
    setOverrideScenario('deadend');
    renderWithProviders('/j/11111111-1111-1111-1111-111111111111/next');

    await waitFor(() => {
      expect(screen.getByTestId('dead-end-state')).toBeInTheDocument();
      expect(screen.getByText('No Automated Action Available')).toBeInTheDocument();
    });
  });

  it('routes a CLARIFICATION-kind recommendation to Screen 4, never to the act/:actionId screen', async () => {
    // Screen 6 (act/:actionId) has no UI for a CLARIFICATION action - per contract,
    // that kind maps to NeedsReviewCard. Previously "Take Action" navigated to
    // /j/:id/act/:actionId unconditionally regardless of kind, which would have opened
    // Screen 6's upload/form screen for a plain clarification question.
    server.use(
      http.get('*/api/v1/journeys/:journey_id/recommendation', () => {
        return HttpResponse.json({
          snapshot_id: '33333333-3333-3333-3333-333333333333',
          readiness: 'NEEDS_REVIEW',
          recommendation: {
            action_id: 'CLARIFY_MONTHLY_INCOME',
            title: 'Clarify Monthly Income',
            kind: 'CLARIFICATION',
            why: 'Salary credit amount does not match the declared income.',
            unlocks: [],
          },
          alternatives: [],
          minimum_path_length: 1,
          source: 'AI_RANKED',
        });
      })
    );

    const user = userEvent.setup();
    renderWithProviders();

    const ctaBtn = await screen.findByRole('button', {
      name: /Take action: Clarify Monthly Income/i,
    });
    await user.click(ctaBtn);

    await waitFor(() => {
      expect(screen.getByTestId('status-screen')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('act-screen')).not.toBeInTheDocument();
  });

  it('strictly contains no prohibited words or claims', async () => {
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Recommended Next Step')).toBeInTheDocument();
    });

    const bodyText = document.body.textContent || '';
    const bodyHtml = document.body.innerHTML || '';

    expect(bodyText).not.toContain('%');
    expect(bodyHtml).not.toContain('%');
    expect(bodyText).not.toMatch(/\bscore\b/i);
    expect(bodyText).not.toMatch(/\bapproval\b/i);
    expect(bodyText).not.toMatch(/\bprobability\b/i);
    expect(bodyText).not.toMatch(/\beligibility\b/i);
    expect(bodyText).not.toMatch(/\bguaranteed\b/i);
  });
});
