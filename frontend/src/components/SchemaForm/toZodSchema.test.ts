import { describe, it, expect } from 'vitest';
import { toZodSchema } from './toZodSchema';
import type { GoalFieldSpec } from './toZodSchema';

describe('Phase F30: toZodSchema & Runtime Validation Rules', () => {
  it('builds enum schema validating choices and required constraints', () => {
    const fields: GoalFieldSpec[] = [
      {
        key: 'loan_purpose',
        type: 'enum',
        label: 'Loan Purpose',
        required: true,
        options: [
          { value: 'HOME_RENOVATION', label: 'Home Renovation' },
          { value: 'MEDICAL_EMERGENCY', label: 'Medical Emergency' },
        ],
      },
    ];

    const schema = toZodSchema(fields);

    expect(schema.safeParse({ loan_purpose: 'HOME_RENOVATION' }).success).toBe(true);
    expect(schema.safeParse({ loan_purpose: 'INVALID_CHOICE' }).success).toBe(false);
    expect(schema.safeParse({ loan_purpose: '' }).success).toBe(false);
  });

  it('builds money/number schema validating min and max bounds', () => {
    const fields: GoalFieldSpec[] = [
      {
        key: 'amount',
        type: 'money',
        label: 'Loan Amount',
        required: true,
        min: 50000,
        max: 1000000,
      },
    ];

    const schema = toZodSchema(fields);

    expect(schema.safeParse({ amount: 500000 }).success).toBe(true);
    expect(schema.safeParse({ amount: '500000' }).success).toBe(true); // Preprocessing string to number
    expect(schema.safeParse({ amount: 10000 }).success).toBe(false); // Below min
    expect(schema.safeParse({ amount: 2000000 }).success).toBe(false); // Above max
  });

  it('builds date, boolean, and text schemas with required and optional flags', () => {
    const fields: GoalFieldSpec[] = [
      {
        key: 'full_name',
        type: 'text',
        label: 'Full Legal Name',
        required: true,
      },
      {
        key: 'dob',
        type: 'date',
        label: 'Date of Birth',
        required: false,
      },
      {
        key: 'consent',
        type: 'boolean',
        label: 'Terms Consent',
        required: true,
      },
    ];

    const schema = toZodSchema(fields);

    // Valid
    const valid = schema.safeParse({
      full_name: 'Rahul Sharma',
      dob: '1990-05-15',
      consent: true,
    });
    expect(valid.success).toBe(true);

    // Missing required full_name
    const invalid = schema.safeParse({
      full_name: '   ',
      dob: '',
      consent: true,
    });
    expect(invalid.success).toBe(false);

    // Missing required boolean consent
    const invalidBool = schema.safeParse({
      full_name: 'Rahul Sharma',
      consent: 'not_a_bool',
    });
    expect(invalidBool.success).toBe(false);
  });
});
