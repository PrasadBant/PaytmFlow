import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { Screen07AiAnalysis } from '@/screens/Screen07AiAnalysis';
import { FormActionModal } from '@/components/FormActionModal';
import { NeedsReviewCard } from '@/components/NeedsReviewCard';
import { apiClient } from '@/api/client';
import type { ActionOption } from '@/components/FormActionModal';
import type { components } from '@/api/types.gen';

type FieldState = components['schemas']['FieldState'];

const mockedNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockedNavigate,
  };
});

describe('Phase F27: Idempotency Keys & Rapid Double-Click Guards', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
  });

  it('Screen 7: Rapid double-click on Apply Changes button fires exactly ONE mutation with a valid UUID idempotency_key', async () => {
    const user = userEvent.setup();
    const postSpy = vi.spyOn(apiClient, 'post');

    const mockEvidenceResponse = {
      evidence_id: 'ev-test-uuid-1',
      filename: 'salary_slip.pdf',
      uploaded_at: new Date().toISOString(),
      interpretation: {
        verified: true,
        confidence: 0.98,
        detected: [{ key: 'monthly_income', label: 'Monthly Income', display_value: '₹85,000' }],
        summary: 'Income verified successfully.',
        conflicts: [],
      },
      consequence_preview: {
        newly_satisfied: [{ key: 'monthly_income', label: 'Monthly Income' }],
        newly_unlocked: [{ action_id: 'SET_LOAN_TENURE', title: 'Set Loan Tenure' }],
        still_blocked: [],
        predicted_readiness: 'NOT_READY' as const,
        progress_before: { completed: 3, pending: 2, blockers: 2, total: 7 },
        progress_after: { completed: 4, pending: 2, blockers: 1, total: 7 },
      },
      diff_preview: {
        from_version: 1,
        to_version: 2,
        fields_changed: [
          {
            key: 'monthly_income',
            label: 'Monthly Income',
            from_status: 'BLOCKED' as const,
            to_status: 'SATISFIED' as const,
            display_value: '₹85,000',
          },
        ],
        actions_unlocked: ['SET_LOAN_TENURE'],
        actions_removed: ['UPLOAD_INCOME_PROOF'],
        readiness: { from: 'NOT_READY' as const, to: 'NOT_READY' as const },
        progress: {
          from: { completed: 3, pending: 2, blockers: 2, total: 7 },
          to: { completed: 4, pending: 2, blockers: 1, total: 7 },
        },
      },
      requires_review: false,
      proposed_action_id: 'UPLOAD_INCOME_PROOF',
    };

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter
          initialEntries={[
            {
              pathname: '/j/11111111-1111-1111-1111-111111111111/analysis',
              state: {
                evidenceResponse: mockEvidenceResponse,
                journeyId: '11111111-1111-1111-1111-111111111111',
                snapshotId: '11111111-1111-1111-1111-111111111111',
                actionId: 'UPLOAD_INCOME_PROOF',
              },
            },
          ]}
        >
          <Routes>
            <Route path="/j/:id/analysis" element={<Screen07AiAnalysis />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    const applyBtn = await screen.findByTestId('continue-apply-btn');
    expect(applyBtn).toBeInTheDocument();

    // Trigger rapid clicks
    await Promise.all([
      user.click(applyBtn),
      user.click(applyBtn),
    ]);

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledTimes(1);
    });

    const [endpoint, payload] = postSpy.mock.calls[0];
    expect(endpoint).toBe('/journeys/11111111-1111-1111-1111-111111111111/actions');
    expect(payload).toMatchObject({
      action_id: 'UPLOAD_INCOME_PROOF',
      expected_snapshot_id: '11111111-1111-1111-1111-111111111111',
      input: {
        evidence_id: 'ev-test-uuid-1',
      },
    });

    // Verify UUID format for idempotency_key
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
    expect((payload as Record<string, unknown> | undefined)?.idempotency_key).toMatch(uuidRegex);
  });

  it('FormActionModal: Rapid double-click on Submit Changes fires exactly ONE mutation with idempotency_key', async () => {
    const user = userEvent.setup();
    const postSpy = vi.spyOn(apiClient, 'post');

    const mockAction: ActionOption = {
      action_id: 'SET_LOAN_TENURE',
      title: 'Choose Repayment Tenure',
      kind: 'FORM',
      why: 'Select loan tenure in months.',
      unlocks: [],
      input_schema: [
        {
          key: 'tenure_months',
          type: 'number',
          label: 'Tenure (Months)',
          required: true,
          min: 12,
          max: 60,
        },
      ],
    };

    function ModalWrapper() {
      const [isOpen, setIsOpen] = useState(true);
      return (
        <FormActionModal
          isOpen={isOpen}
          onClose={() => setIsOpen(false)}
          action={mockAction}
          journeyId="11111111-1111-1111-1111-111111111111"
          expectedSnapshotId="11111111-1111-1111-1111-111111111111"
          defaultValues={{ tenure_months: 36 }}
        />
      );
    }

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ModalWrapper />
        </MemoryRouter>
      </QueryClientProvider>
    );

    const submitBtn = screen.getByRole('button', { name: /Submit Changes/i });
    expect(submitBtn).toBeInTheDocument();

    // Trigger rapid double click
    await user.dblClick(submitBtn);

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledTimes(1);
    });

    const [endpoint, payload] = postSpy.mock.calls[0];
    expect(endpoint).toBe('/journeys/11111111-1111-1111-1111-111111111111/actions');
    expect(payload).toMatchObject({
      action_id: 'SET_LOAN_TENURE',
      expected_snapshot_id: '11111111-1111-1111-1111-111111111111',
      input: {
        tenure_months: 36,
      },
    });
    expect((payload as Record<string, unknown> | undefined)?.idempotency_key).toBeDefined();
  });

  it('NeedsReviewCard: Rapid double-click on Submit Response fires exactly ONE clarification mutation', async () => {
    const user = userEvent.setup();
    const postSpy = vi.spyOn(apiClient, 'post');

    const mockField: FieldState = {
      key: 'monthly_income',
      label: 'Monthly Income',
      status: 'AMBIGUOUS',
      ambiguity: {
        ambiguity_id: 'INCOME_MISMATCH',
        question: 'Which declared monthly income is accurate?',
        reason: 'Bank statement indicates ₹90,000 while application says ₹85,000.',
        answer_type: 'CHOICE',
        choices: [
          { value: 85000, label: '₹85,000 (Declared)' },
          { value: 90000, label: '₹90,000 (Bank Statement)' },
        ],
      },
    };

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <NeedsReviewCard
            journeyId="11111111-1111-1111-1111-111111111111"
            snapshotId="11111111-1111-1111-1111-111111111111"
            field={mockField}
            onResolved={vi.fn()}
          />
        </MemoryRouter>
      </QueryClientProvider>
    );

    const firstChoice = screen.getByTestId('clarification-choice-0');
    await user.click(firstChoice);

    const submitBtn = screen.getByTestId('submit-clarification-btn');
    expect(submitBtn).not.toBeDisabled();

    // Trigger rapid clicks
    await Promise.all([
      user.click(submitBtn),
      user.click(submitBtn),
    ]);

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledTimes(1);
    });

    const [endpoint, payload] = postSpy.mock.calls[0];
    expect(endpoint).toBe('/journeys/11111111-1111-1111-1111-111111111111/clarifications');
    expect(payload).toEqual({
      ambiguity_id: 'INCOME_MISMATCH',
      field: 'monthly_income',
      answer: 85000,
      expected_snapshot_id: '11111111-1111-1111-1111-111111111111',
    });
  });
});
