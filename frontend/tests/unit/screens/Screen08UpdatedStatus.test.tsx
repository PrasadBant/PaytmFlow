import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Screen08UpdatedStatus } from '@/screens/Screen08UpdatedStatus';
import type { components } from '@/api/types.gen';

type ActionResponse = components['schemas']['ActionResponse'];
type JourneyStateResponse = components['schemas']['JourneyStateResponse'];

const mockJourney: JourneyStateResponse = {
  journey_id: '11111111-1111-1111-1111-111111111111',
  journey_type: 'LENDING',
  schema_version: '1.0.0',
  snapshot_id: '33333333-3333-3333-3333-333333333333',
  version_number: 2,
  readiness: 'NOT_READY',
  status: 'IN_PROGRESS',
  fields: [
    {
      key: 'loan_amount',
      label: 'Loan Amount',
      status: 'SATISFIED',
      display_value: '₹5,00,000',
    },
    {
      key: 'monthly_income',
      label: 'Monthly Income',
      status: 'SATISFIED',
      display_value: '₹85,000',
    },
    {
      key: 'bank_statement',
      label: 'Salary Bank Statement',
      status: 'BLOCKED',
      explanation: 'Upload past 6 months bank statement to verify salary credits.',
      resolve_action_id: 'UPLOAD_BANK_STATEMENT',
      mandatory: true,
    },
    {
      key: 'identity_proof',
      label: 'Identity Document',
      status: 'BLOCKED',
      explanation: 'Aadhaar or PAN required for KYC.',
      resolve_action_id: 'UPLOAD_AADHAAR',
      mandatory: true,
    },
  ],
  progress: {
    completed: 2,
    pending: 0,
    blockers: 2,
    total: 4,
  },
  display: {
    title: 'Personal Loan',
    summary: '₹5,00,000 · Home Renovation',
  },
  updated_at: '2026-09-12T10:10:00Z',
};

const mockActionResponse: ActionResponse = {
  journey: mockJourney,
  diff: {
    from_version: 1,
    to_version: 2,
    fields_changed: [
      {
        key: 'monthly_income',
        label: 'Monthly Income',
        from_status: 'BLOCKED',
        to_status: 'SATISFIED',
        display_value: '₹85,000',
        cause: 'ACTION:UPLOAD_INCOME_PROOF',
      },
    ],
    actions_unlocked: ['UPLOAD_BANK_STATEMENT'],
    actions_removed: ['UPLOAD_INCOME_PROOF'],
    readiness: {
      from: 'NOT_READY',
      to: 'NOT_READY',
    },
    progress: {
      from: { completed: 1, pending: 0, blockers: 3, total: 4 },
      to: { completed: 2, pending: 0, blockers: 2, total: 4 },
    },
  },
  next_recommendation: {
    snapshot_id: '33333333-3333-3333-3333-333333333333',
    readiness: 'NOT_READY',
    recommendation: {
      action_id: 'UPLOAD_BANK_STATEMENT',
      title: 'Upload Bank Statement',
      kind: 'EVIDENCE',
      why: 'Required to clear salary verification blocker.',
      unlocks: ['CREDIT_ASSESSMENT'],
    },
    alternatives: [],
    minimum_path_length: 2,
  },
};

function renderScreen8(
  initialEntry = '/j/11111111-1111-1111-1111-111111111111/updated',
  locationState?: Record<string, unknown>,
  customQueryClient?: QueryClient
) {
  const queryClient =
    customQueryClient ??
    new QueryClient({
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
            state:
              locationState !== undefined
                ? locationState
                : {
                    actionResponse: mockActionResponse,
                    journeyId: '11111111-1111-1111-1111-111111111111',
                  },
          },
        ]}
      >
        <Routes>
          <Route path="/j/:id/updated" element={<Screen08UpdatedStatus />} />
          <Route path="/j/:id" element={<div data-testid="screen-04-stub">Current Status Stub</div>} />
          <Route path="/j/:id/next" element={<div data-testid="screen-05-stub">Recommendation Stub</div>} />
          <Route path="/j/:id/complete" element={<div data-testid="screen-09-stub">Complete Stub</div>} />
          <Route path="/my-journeys" element={<div data-testid="my-journeys-stub">My Journeys Stub</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Screen08UpdatedStatus (F22)', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('renders celebratory header, title, and snapshot version', async () => {
    renderScreen8();

    expect(await screen.findByTestId('celebration-header')).toBeInTheDocument();
    expect(screen.getByTestId('progress-updated-title')).toHaveTextContent('Progress Updated!');
    expect(screen.getByText('Verified Update')).toBeInTheDocument();
    expect(screen.getByText('Snapshot v2')).toBeInTheDocument();
    expect(screen.getByText(/Personal Loan/i)).toBeInTheDocument();
  });

  it('renders progress completed/total accurately from server state without prohibited % or scores', async () => {
    const { container } = renderScreen8();

    expect(await screen.findByText('2/4')).toBeInTheDocument();
    expect(screen.getByText('2 Completed')).toBeInTheDocument();
    expect(screen.getByText('2 Blockers')).toBeInTheDocument();

    const html = container.innerHTML;
    expect(html).not.toContain('%');
    expect(html).not.toMatch(/\bscore\b/i);
    expect(html).not.toMatch(/\bapproval\b/i);
    expect(html).not.toMatch(/\bprobability\b/i);
    expect(html).not.toMatch(/\beligibility\b/i);
    expect(html).not.toMatch(/\bguaranteed\b/i);
  });

  it('renders verified applied JourneyDiff with correct variant and values', async () => {
    renderScreen8();

    expect(await screen.findByTestId('journey-diff-section')).toBeInTheDocument();
    expect(screen.getByText('What changed')).toBeInTheDocument();
    expect(screen.getByText('Applied')).toBeInTheDocument();
    expect(screen.getByTestId('diff-field-monthly_income')).toBeInTheDocument();
    expect(screen.getByTestId('unlocked-action-UPLOAD_BANK_STATEMENT')).toBeInTheDocument();
    expect(screen.getByTestId('removed-action-UPLOAD_INCOME_PROOF')).toBeInTheDocument();
  });

  it('renders remaining tasks / blockers and completed requirements', async () => {
    const user = userEvent.setup();
    renderScreen8();

    expect(await screen.findByTestId('remaining-tasks-section')).toBeInTheDocument();
    expect(screen.getByText('Remaining Tasks (2)')).toBeInTheDocument();
    expect(screen.getByText('Salary Bank Statement')).toBeInTheDocument();
    expect(screen.getByText('Identity Document')).toBeInTheDocument();

    // Toggle completed requirements
    const toggleBtn = screen.getByText(/Completed Requirements/i);
    expect(toggleBtn).toBeInTheDocument();
    await user.click(toggleBtn);
    expect(screen.getByText('Loan Amount')).toBeInTheDocument();
  });

  it('navigates to recommendation screen on "Take Recommended Step" click when NOT_READY', async () => {
    const user = userEvent.setup();
    renderScreen8();

    const nextStepBtn = await screen.findByTestId('take-next-step-btn');
    expect(nextStepBtn).toHaveTextContent('Take Recommended Step');
    await user.click(nextStepBtn);

    expect(await screen.findByTestId('screen-05-stub')).toBeInTheDocument();
  });

  it('navigates to status overview screen on "View Status Overview" click', async () => {
    const user = userEvent.setup();
    renderScreen8();

    const viewStatusBtn = await screen.findByTestId('view-full-status-btn');
    await user.click(viewStatusBtn);

    expect(await screen.findByTestId('screen-04-stub')).toBeInTheDocument();
  });

  it('navigates to complete screen when journey readiness is READY', async () => {
    const user = userEvent.setup();
    const readyJourney: JourneyStateResponse = {
      ...mockJourney,
      readiness: 'READY',
      status: 'COMPLETED',
      fields: mockJourney.fields.map((f) => ({ ...f, status: 'SATISFIED' })),
      progress: { completed: 4, pending: 0, blockers: 0, total: 4 },
    };

    const readyActionResponse: ActionResponse = {
      ...mockActionResponse,
      journey: readyJourney,
    };

    renderScreen8('/j/11111111-1111-1111-1111-111111111111/updated', {
      actionResponse: readyActionResponse,
      journeyId: '11111111-1111-1111-1111-111111111111',
    });

    const ctaBtn = await screen.findByTestId('take-next-step-btn');
    expect(ctaBtn).toHaveTextContent('Proceed to Complete');
    await user.click(ctaBtn);

    expect(await screen.findByTestId('screen-09-stub')).toBeInTheDocument();
  });

  it('renders all blockers cleared notice when no blockers remain', async () => {
    const allClearedJourney: JourneyStateResponse = {
      ...mockJourney,
      fields: mockJourney.fields.map((f) => ({ ...f, status: 'SATISFIED' })),
      progress: { completed: 4, pending: 0, blockers: 0, total: 4 },
    };

    renderScreen8('/j/11111111-1111-1111-1111-111111111111/updated', {
      actionResponse: { ...mockActionResponse, journey: allClearedJourney },
      journeyId: '11111111-1111-1111-1111-111111111111',
    });

    expect(await screen.findByText('All blockers cleared!')).toBeInTheDocument();
  });

  it('regression: never claims "income proof" for a non-LENDING/non-income update', async () => {
    // This screen previously hardcoded "Income verification marked as completed" /
    // "Your income proof has been successfully uploaded and verified." unconditionally,
    // regardless of pack or which field actually changed - a fabricated, journey-specific
    // claim shown after every action across all six packs. It must now be derived from
    // the real diff instead.
    const kycJourney: JourneyStateResponse = {
      ...mockJourney,
      journey_type: 'KYC',
      fields: [
        { key: 'aadhaar_verified', label: 'Aadhaar Verification', status: 'SATISFIED' },
      ],
      progress: { completed: 1, pending: 1, blockers: 0, total: 2 },
      display: { title: 'Video & Biometric KYC', summary: 'Wallet Upgrade' },
    };
    const kycActionResponse: ActionResponse = {
      journey: kycJourney,
      diff: {
        from_version: 1,
        to_version: 2,
        fields_changed: [
          {
            key: 'aadhaar_verified',
            label: 'Aadhaar Verification',
            from_status: 'BLOCKED',
            to_status: 'SATISFIED',
            display_value: 'Verified',
            cause: 'ACTION:VERIFY_AADHAAR',
          },
        ],
        actions_unlocked: [],
        actions_removed: [],
        readiness: { from: 'NOT_READY', to: 'NOT_READY' },
        progress: { from: { completed: 0, pending: 2, blockers: 0, total: 2 }, to: { completed: 1, pending: 1, blockers: 0, total: 2 } },
      },
      next_recommendation: null,
    };

    renderScreen8('/j/11111111-1111-1111-1111-111111111111/updated', {
      actionResponse: kycActionResponse,
      journeyId: '11111111-1111-1111-1111-111111111111',
    });

    await screen.findByTestId('celebration-header');
    expect(screen.queryByText(/income verification/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/income proof/i)).not.toBeInTheDocument();
    expect(screen.getByText('Aadhaar Verification marked as completed')).toBeInTheDocument();
    expect(
      screen.getByText('Your Aadhaar Verification has been successfully updated and verified.')
    ).toBeInTheDocument();
  });
});
