import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import { NeedsReviewCard } from './NeedsReviewCard';
import type { components } from '@/api/types.gen';

type FieldState = components['schemas']['FieldState'];

const mockAmbiguousField1: FieldState = {
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
};

const mockAmbiguousField2: FieldState = {
  key: 'employment_type',
  label: 'Employment Classification',
  status: 'AMBIGUOUS',
  explanation: 'Second ambiguity in fields list',
  ambiguity: {
    ambiguity_id: 'EMPLOYMENT_MISMATCH',
    reason: 'Contract employment indicated in documents',
    question: 'Are you currently permanent or contract salaried?',
    answer_type: 'CHOICE',
    choices: [
      { value: 'PERMANENT', label: 'Permanent Full-time' },
      { value: 'CONTRACT', label: 'Fixed-term Contract' },
    ],
  },
};

const mockMoneyField: FieldState = {
  key: 'monthly_income',
  label: 'Verified Monthly Income',
  status: 'AMBIGUOUS',
  ambiguity: {
    ambiguity_id: 'ENTER_INCOME',
    question: 'Please confirm your exact net take-home pay.',
    answer_type: 'MONEY',
  },
};

const mockBooleanField: FieldState = {
  key: 'is_tax_resident',
  label: 'Tax Residency',
  status: 'AMBIGUOUS',
  ambiguity: {
    ambiguity_id: 'TAX_RESIDENCY',
    question: 'Are you an Indian tax resident for the current assessment year?',
    answer_type: 'BOOLEAN',
  },
};

function renderCard(
  props: React.ComponentProps<typeof NeedsReviewCard>
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <NeedsReviewCard {...props} />
    </QueryClientProvider>
  );
}

describe('NeedsReviewCard (F25)', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('renders question, reason, and choices for CHOICE answer type', () => {
    renderCard({
      journeyId: '11111111-1111-1111-1111-111111111111',
      snapshotId: 'cccccccc-3333-3333-3333-333333333333',
      field: mockAmbiguousField1,
    });

    expect(screen.getByTestId('needs-review-card')).toBeInTheDocument();
    expect(screen.getByText('Review Required')).toBeInTheDocument();
    expect(
      screen.getByText('Which amount reflects your recurring monthly net base salary?')
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Bank statement reflects ₹80,000 average monthly credit/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText('₹85,000 (Base Salary with deductions)')
    ).toBeInTheDocument();
    expect(
      screen.getByText('₹80,000 (Average in-hand deposit)')
    ).toBeInTheDocument();
    expect(screen.getByTestId('submit-clarification-btn')).toBeDisabled();
  });

  it('renders exactly ONE question when multiple ambiguous fields exist', () => {
    renderCard({
      journeyId: '11111111-1111-1111-1111-111111111111',
      snapshotId: 'cccccccc-3333-3333-3333-333333333333',
      fields: [mockAmbiguousField1, mockAmbiguousField2],
    });

    // Only first question is rendered
    expect(
      screen.getByText('Which amount reflects your recurring monthly net base salary?')
    ).toBeInTheDocument();
    expect(
      screen.queryByText('Are you currently permanent or contract salaried?')
    ).not.toBeInTheDocument();
  });

  it('submits selected choice and triggers onResolved callback', async () => {
    const user = userEvent.setup();
    const handleResolved = vi.fn();

    server.use(
      http.post('*/api/v1/journeys/:id/clarifications', async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        expect(body.ambiguity_id).toBe('INCOME_MISMATCH');
        expect(body.field).toBe('monthly_income');
        expect(body.answer).toBe(85000);
        expect(body.expected_snapshot_id).toBe('cccccccc-3333-3333-3333-333333333333');

        return HttpResponse.json({
          journey: {
            journey_id: '11111111-1111-1111-1111-111111111111',
            status: 'IN_PROGRESS',
            readiness: 'NOT_READY',
            version_number: 4,
            fields: [],
            progress: { completed: 6, pending: 1, blockers: 0, total: 7 },
            display: { title: 'Loan', summary: 'Updated' },
          },
          diff: {
            from_version: 3,
            to_version: 4,
            fields_changed: [],
            actions_unlocked: [],
            actions_removed: [],
          },
        });
      })
    );

    renderCard({
      journeyId: '11111111-1111-1111-1111-111111111111',
      snapshotId: 'cccccccc-3333-3333-3333-333333333333',
      field: mockAmbiguousField1,
      onResolved: handleResolved,
    });

    const choice1 = screen.getByTestId('clarification-choice-0');
    await user.click(choice1);

    const submitBtn = screen.getByTestId('submit-clarification-btn');
    expect(submitBtn).toBeEnabled();
    await user.click(submitBtn);

    expect(handleResolved).toHaveBeenCalledOnce();
  });

  it('renders MoneyInput for MONEY answer type', async () => {
    const user = userEvent.setup();
    renderCard({
      journeyId: '11111111-1111-1111-1111-111111111111',
      snapshotId: 'cccccccc-3333-3333-3333-333333333333',
      field: mockMoneyField,
    });

    const moneyInput = screen.getByTestId('clarification-input');
    expect(moneyInput).toBeInTheDocument();

    await user.type(moneyInput, '90000');
    expect(screen.getByTestId('submit-clarification-btn')).toBeEnabled();
  });

  it('renders boolean options for BOOLEAN answer type', async () => {
    const user = userEvent.setup();
    renderCard({
      journeyId: '11111111-1111-1111-1111-111111111111',
      snapshotId: 'cccccccc-3333-3333-3333-333333333333',
      field: mockBooleanField,
    });

    const yesBtn = screen.getByTestId('clarification-choice-true');
    expect(yesBtn).toBeInTheDocument();
    await user.click(yesBtn);

    expect(screen.getByTestId('submit-clarification-btn')).toBeEnabled();
  });

  it('displays error banner when submission fails', async () => {
    const user = userEvent.setup();

    server.use(
      http.post('*/api/v1/journeys/:id/clarifications', () => {
        return HttpResponse.json(
          {
            error: {
              code: 'ACTION_STALE',
              message: 'This journey snapshot has moved on. Please refresh.',
            },
          },
          { status: 409 }
        );
      })
    );

    renderCard({
      journeyId: '11111111-1111-1111-1111-111111111111',
      snapshotId: 'cccccccc-3333-3333-3333-333333333333',
      field: mockAmbiguousField1,
    });

    await user.click(screen.getByTestId('clarification-choice-0'));
    await user.click(screen.getByTestId('submit-clarification-btn'));

    expect(await screen.findByTestId('clarification-error')).toBeInTheDocument();
    expect(
      screen.getByText('This journey has moved on — refreshing')
    ).toBeInTheDocument();
  });

  it('contains no prohibited claims (% or score keywords)', () => {
    const { container } = renderCard({
      journeyId: '11111111-1111-1111-1111-111111111111',
      snapshotId: 'cccccccc-3333-3333-3333-333333333333',
      field: mockAmbiguousField1,
    });

    const html = container.innerHTML;
    expect(html).not.toContain('%');
    expect(html).not.toMatch(/\bscore\b/i);
    expect(html).not.toMatch(/\bapproval\b/i);
    expect(html).not.toMatch(/\bprobability\b/i);
    expect(html).not.toMatch(/\beligibility\b/i);
    expect(html).not.toMatch(/\bguaranteed\b/i);
  });
});
