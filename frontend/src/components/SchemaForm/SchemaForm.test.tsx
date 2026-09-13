import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { SchemaForm } from './SchemaForm';
import { toZodSchema } from './toZodSchema';
import type { components } from '@/api/types.gen';

type GoalFieldSpec = components['schemas']['GoalFieldSpec'];

describe('toZodSchema', () => {
  it('validates required text fields', () => {
    const fields: GoalFieldSpec[] = [
      { key: 'full_name', type: 'text', label: 'Full Name', required: true },
    ];
    const schema = toZodSchema(fields);

    const validResult = schema.safeParse({ full_name: 'John Doe' });
    expect(validResult.success).toBe(true);

    const emptyResult = schema.safeParse({ full_name: '' });
    expect(emptyResult.success).toBe(false);

    const missingResult = schema.safeParse({});
    expect(missingResult.success).toBe(false);
  });

  it('validates optional text fields', () => {
    const fields: GoalFieldSpec[] = [
      { key: 'nickname', type: 'text', label: 'Nickname', required: false },
    ];
    const schema = toZodSchema(fields);

    expect(schema.safeParse({ nickname: '' }).success).toBe(true);
    expect(schema.safeParse({}).success).toBe(true);
    expect(schema.safeParse({ nickname: 'Johnny' }).success).toBe(true);
  });

  it('validates money and number min/max constraints', () => {
    const fields: GoalFieldSpec[] = [
      {
        key: 'loan_amount',
        type: 'money',
        label: 'Loan Amount',
        required: true,
        min: 10000,
        max: 500000,
      },
      {
        key: 'tenure',
        type: 'number',
        label: 'Tenure',
        required: true,
        min: 6,
        max: 60,
      },
    ];
    const schema = toZodSchema(fields);

    // Valid
    expect(schema.safeParse({ loan_amount: 50000, tenure: 24 }).success).toBe(true);

    // Below min
    expect(schema.safeParse({ loan_amount: 5000, tenure: 24 }).success).toBe(false);
    expect(schema.safeParse({ loan_amount: 50000, tenure: 3 }).success).toBe(false);

    // Above max
    expect(schema.safeParse({ loan_amount: 600000, tenure: 24 }).success).toBe(false);
    expect(schema.safeParse({ loan_amount: 50000, tenure: 72 }).success).toBe(false);
  });

  it('validates enum values', () => {
    const fields: GoalFieldSpec[] = [
      {
        key: 'employment',
        type: 'enum',
        label: 'Employment',
        required: true,
        options: [
          { value: 'SALARIED', label: 'Salaried' },
          { value: 'SELF_EMPLOYED', label: 'Self Employed' },
        ],
      },
    ];
    const schema = toZodSchema(fields);

    expect(schema.safeParse({ employment: 'SALARIED' }).success).toBe(true);
    expect(schema.safeParse({ employment: 'INVALID' }).success).toBe(false);
    expect(schema.safeParse({}).success).toBe(false);
  });

  it('validates boolean fields', () => {
    const fields: GoalFieldSpec[] = [
      { key: 'agree', type: 'boolean', label: 'Agree to terms', required: true },
    ];
    const schema = toZodSchema(fields);

    expect(schema.safeParse({ agree: true }).success).toBe(true);
    expect(schema.safeParse({ agree: false }).success).toBe(true);
  });
});

describe('SchemaForm Component', () => {
  const sampleSchema: GoalFieldSpec[] = [
    {
      key: 'loan_amount',
      type: 'money',
      label: 'Required Loan Amount',
      required: true,
      placeholder: 'e.g. 5,00,000',
      min: 10000,
      max: 10000000,
      help_text: 'Enter the amount you wish to borrow.',
    },
    {
      key: 'employment_type',
      type: 'enum',
      label: 'Employment Type',
      required: true,
      options: [
        { value: 'Salaried', label: 'Salaried' },
        { value: 'Self-Employed Professional', label: 'Self-Employed Professional' },
      ],
    },
    {
      key: 'pan_number',
      type: 'text',
      label: 'PAN Number',
      required: true,
      placeholder: 'ABCDE1234F',
    },
    {
      key: 'dob',
      type: 'date',
      label: 'Date of Birth',
      required: false,
    },
    {
      key: 'tobacco',
      type: 'boolean',
      label: 'Tobacco Consumer',
      required: false,
    },
  ];

  it('renders all form fields with labels and submit button', () => {
    render(
      <SchemaForm
        schema={sampleSchema}
        submitLabel="Continue to Verification"
        onSubmit={vi.fn()}
      />
    );

    expect(screen.getByLabelText(/Required Loan Amount/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Employment Type/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/PAN Number/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Date of Birth/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Tobacco Consumer/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Continue to Verification/i })).toBeInTheDocument();
  });

  it('shows required validation errors on empty submission', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn();

    render(
      <SchemaForm
        schema={sampleSchema}
        submitLabel="Submit"
        onSubmit={handleSubmit}
      />
    );

    await user.click(screen.getByRole('button', { name: /Submit/i }));

    await waitFor(() => {
      expect(screen.getByText(/Required Loan Amount is required/i)).toBeInTheDocument();
      expect(screen.getByText(/Employment Type is required/i)).toBeInTheDocument();
      expect(screen.getByText(/PAN Number is required/i)).toBeInTheDocument();
    });

    expect(handleSubmit).not.toHaveBeenCalled();
  });

  it('validates min and max on money inputs and formats Indian currency', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn();

    render(
      <SchemaForm
        schema={sampleSchema}
        submitLabel="Submit"
        onSubmit={handleSubmit}
      />
    );

    const moneyInput = screen.getByLabelText(/Required Loan Amount/i);

    // Enter amount below min (5000 < 10000)
    await user.type(moneyInput, '5000');
    await user.click(screen.getByRole('button', { name: /Submit/i }));

    await waitFor(() => {
      expect(screen.getByText(/Required Loan Amount must be at least ₹10,000/i)).toBeInTheDocument();
    });

    expect(handleSubmit).not.toHaveBeenCalled();
  });

  it('submits valid data correctly with raw numeric values in state and Indian grouping in display', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn();

    render(
      <SchemaForm
        schema={sampleSchema}
        submitLabel="Submit Goal"
        onSubmit={handleSubmit}
      />
    );

    const moneyInput = screen.getByLabelText(/Required Loan Amount/i);
    await user.type(moneyInput, '500000');
    // Money input formats Indian grouping in display
    expect(moneyInput).toHaveValue('5,00,000');

    const select = screen.getByLabelText(/Employment Type/i);
    await user.selectOptions(select, 'Salaried');

    const panInput = screen.getByLabelText(/PAN Number/i);
    await user.type(panInput, 'ABCDE1234F');

    const tobaccoCheckbox = screen.getByLabelText(/Tobacco Consumer/i);
    await user.click(tobaccoCheckbox);

    await user.click(screen.getByRole('button', { name: /Submit Goal/i }));

    await waitFor(() => {
      expect(handleSubmit).toHaveBeenCalledTimes(1);
    });

    expect(handleSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        loan_amount: 500000,
        employment_type: 'Salaried',
        pan_number: 'ABCDE1234F',
        tobacco: true,
      })
    );
  });

  it('injects server-side errors into the matching fields', async () => {
    const serverErrors = {
      pan_number: 'Invalid PAN card format from verification system',
    };

    render(
      <SchemaForm
        schema={sampleSchema}
        submitLabel="Submit"
        onSubmit={vi.fn()}
        serverErrors={serverErrors}
      />
    );

    expect(
      screen.getByText('Invalid PAN card format from verification system')
    ).toBeInTheDocument();
  });

  it('disables inputs and shows spinner when isSubmitting is true', () => {
    render(
      <SchemaForm
        schema={sampleSchema}
        submitLabel="Submitting..."
        onSubmit={vi.fn()}
        isSubmitting={true}
      />
    );

    expect(screen.getByRole('button', { name: /Submitting\.\.\./i })).toBeDisabled();
    expect(screen.getByLabelText(/Required Loan Amount/i)).toBeDisabled();
    expect(screen.getByLabelText(/Employment Type/i)).toBeDisabled();
    expect(screen.getByLabelText(/PAN Number/i)).toBeDisabled();
  });
});
