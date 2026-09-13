import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FormActionModal, type ActionOption } from './FormActionModal';

function renderModal(props: Partial<React.ComponentProps<typeof FormActionModal>> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  const defaultAction: ActionOption = {
    action_id: 'SET_LOAN_TENURE',
    title: 'Adjust Loan Tenure',
    kind: 'FORM',
    why: 'Modify repayment tenure to adjust monthly EMI projections.',
    unlocks: ['tenure_months'],
    input_schema: [
      {
        key: 'tenure_months',
        type: 'number',
        label: 'Tenure in Months',
        required: true,
        min: 6,
        max: 84,
      },
    ],
  };

  return render(
    <QueryClientProvider client={queryClient}>
      <FormActionModal
        isOpen={true}
        onClose={vi.fn()}
        action={defaultAction}
        journeyId="11111111-1111-1111-1111-111111111111"
        expectedSnapshotId="aaaaaaaa-1111-1111-1111-111111111111"
        {...props}
      />
    </QueryClientProvider>
  );
}

describe('FormActionModal (F17)', () => {
  it('renders SET_LOAN_TENURE schema form dynamically', () => {
    renderModal();

    expect(screen.getByText('Adjust Loan Tenure')).toBeInTheDocument();
    expect(
      screen.getByText('Modify repayment tenure to adjust monthly EMI projections.')
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Tenure in Months/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Submit Changes →/i })).toBeInTheDocument();
  });

  it('renders ADD_EMPLOYMENT_DETAILS schema form dynamically with zero bespoke code', () => {
    const employmentAction: ActionOption = {
      action_id: 'ADD_EMPLOYMENT_DETAILS',
      title: 'Update Employer Details',
      kind: 'FORM',
      why: 'Add employer name and work experience for assessment.',
      unlocks: ['employment_type'],
      input_schema: [
        {
          key: 'employer_name',
          type: 'text',
          label: 'Company / Employer Name',
          required: true,
        },
        {
          key: 'experience_years',
          type: 'number',
          label: 'Total Work Experience (Years)',
          required: true,
          min: 0,
          max: 40,
        },
      ],
    };

    renderModal({ action: employmentAction });

    expect(screen.getByText('Update Employer Details')).toBeInTheDocument();
    expect(screen.getByLabelText(/Company \/ Employer Name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Total Work Experience/i)).toBeInTheDocument();
  });

  it('submits form action and calls onSuccess callback', async () => {
    const user = userEvent.setup();
    const handleSuccess = vi.fn();
    const handleClose = vi.fn();

    renderModal({ onSuccess: handleSuccess, onClose: handleClose });

    const tenureInput = screen.getByLabelText(/Tenure in Months/i);
    await user.type(tenureInput, '36');

    await user.click(screen.getByRole('button', { name: /Submit Changes →/i }));

    await waitFor(() => {
      expect(handleClose).toHaveBeenCalled();
      expect(handleSuccess).toHaveBeenCalled();
    });
  });

  it('validates min/max bounds and prevents submission when invalid', async () => {
    const user = userEvent.setup();
    const handleSuccess = vi.fn();

    renderModal({ onSuccess: handleSuccess });

    const tenureInput = screen.getByLabelText(/Tenure in Months/i);
    await user.type(tenureInput, '2'); // Below min 6

    await user.click(screen.getByRole('button', { name: /Submit Changes →/i }));

    await waitFor(() => {
      expect(screen.getByText(/must be at least 6/i)).toBeInTheDocument();
    });

    expect(handleSuccess).not.toHaveBeenCalled();
  });

  it('does not render when isOpen is false', () => {
    const { container } = renderModal({ isOpen: false });
    expect(container).toBeEmptyDOMElement();
  });

  it('strictly contains no prohibited words or claims', () => {
    const { container } = renderModal();
    const html = container.innerHTML;

    expect(html).not.toContain('%');
    expect(html).not.toMatch(/\bscore\b/i);
    expect(html).not.toMatch(/\bapproval\b/i);
    expect(html).not.toMatch(/\bprobability\b/i);
    expect(html).not.toMatch(/\beligibility\b/i);
    expect(html).not.toMatch(/\bguaranteed\b/i);
  });
});
