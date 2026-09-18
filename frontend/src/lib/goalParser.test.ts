import { describe, it, expect } from 'vitest';
import { parseGoalFromNaturalLanguage } from './goalParser';
import type { components } from '@/api/types.gen';

type GoalFieldSpec = components['schemas']['GoalFieldSpec'];

describe('parseGoalFromNaturalLanguage', () => {
  it('returns empty object for empty or missing input', () => {
    expect(parseGoalFromNaturalLanguage('', [])).toEqual({});
    expect(
      parseGoalFromNaturalLanguage('   ', [
        { key: 'amount', type: 'money', label: 'Amount', required: true },
      ])
    ).toEqual({});
  });

  it('parses loan amounts with commas and tenure correctly for LENDING', () => {
    const schema: GoalFieldSpec[] = [
      {
        key: 'loan_amount',
        type: 'money',
        label: 'Loan Amount',
        required: true,
        min: 50000,
        max: 500000,
      },
      {
        key: 'tenure_months',
        type: 'number',
        label: 'Tenure (months)',
        required: true,
        min: 6,
        max: 60,
      },
      {
        key: 'loan_purpose',
        type: 'enum',
        label: 'Loan Purpose',
        required: true,
        options: [
          { value: 'HOME_RENOVATION', label: 'Home Renovation' },
          { value: 'MEDICAL_EXPENSES', label: 'Medical Expenses' },
          { value: 'EDUCATION', label: 'Higher Education' },
          { value: 'DEBT_CONSOLIDATION', label: 'Debt Consolidation' },
        ],
      },
    ];

    const parsed1 = parseGoalFromNaturalLanguage(
      'Need a 5 lakh loan for home renovation, tenure 24 months',
      schema
    );
    expect(parsed1.loan_amount).toBe(500000);
    expect(parsed1.tenure_months).toBe(24);
    expect(parsed1.loan_purpose).toBe('HOME_RENOVATION');

    const parsed2 = parseGoalFromNaturalLanguage(
      'I need 2,50,000 personal loan for medical emergency for 3 years',
      schema
    );
    expect(parsed2.loan_amount).toBe(250000);
    expect(parsed2.tenure_months).toBe(36);
    expect(parsed2.loan_purpose).toBe('MEDICAL_EXPENSES');
  });

  it('parses credit limit and card variant for CREDIT_CARD', () => {
    const schema: GoalFieldSpec[] = [
      {
        key: 'card_variant',
        type: 'enum',
        label: 'Card Variant',
        required: true,
        options: [
          { value: 'CASHBACK', label: 'Paytm Cashback Pro' },
          { value: 'REWARDS', label: 'Paytm Rewards Max' },
          { value: 'TRAVEL', label: 'Paytm Travel Elite' },
        ],
      },
      {
        key: 'credit_limit_preference',
        type: 'money',
        label: 'Desired Limit',
        required: false,
        min: 25000,
        max: 1000000,
      },
    ];

    const parsed = parseGoalFromNaturalLanguage(
      'Want a cashback credit card with 2 lakh limit',
      schema
    );
    expect(parsed.card_variant).toBe('CASHBACK');
    expect(parsed.credit_limit_preference).toBe(200000);

    const parsedTravel = parseGoalFromNaturalLanguage(
      'Travel card with 50,000 credit limit',
      schema
    );
    expect(parsedTravel.card_variant).toBe('TRAVEL');
    expect(parsedTravel.credit_limit_preference).toBe(50000);
  });

  it('parses sum insured and policy type for INSURANCE', () => {
    const schema: GoalFieldSpec[] = [
      {
        key: 'sum_insured',
        type: 'money',
        label: 'Sum Insured',
        required: true,
        min: 300000,
        max: 5000000,
      },
      {
        key: 'policy_type',
        type: 'enum',
        label: 'Policy Type',
        required: true,
        options: [
          { value: 'INDIVIDUAL', label: 'Individual Cover' },
          { value: 'FAMILY_FLOATER', label: 'Family Floater' },
          { value: 'GROUP', label: 'Group Cover' },
        ],
      },
    ];

    const parsed = parseGoalFromNaturalLanguage(
      'Looking for 5 lakh individual health cover',
      schema
    );
    expect(parsed.sum_insured).toBe(500000);
    expect(parsed.policy_type).toBe('INDIVIDUAL');

    const parsedFamily = parseGoalFromNaturalLanguage(
      '10 lakh family floater policy for parents',
      schema
    );
    expect(parsedFamily.sum_insured).toBe(1000000);
    expect(parsedFamily.policy_type).toBe('FAMILY_FLOATER');
  });

  it('parses investment mode and target amount for INVESTMENT', () => {
    const schema: GoalFieldSpec[] = [
      {
        key: 'investment_mode',
        type: 'enum',
        label: 'Investment Mode',
        required: true,
        options: [
          { value: 'MONTHLY_SIP', label: 'Monthly Systematic Investment (SIP)' },
          { value: 'ONE_TIME_LUMPSUM', label: 'One-Time Lump Sum' },
        ],
      },
      {
        key: 'target_amount',
        type: 'money',
        label: 'Investment Amount',
        required: true,
        min: 500,
        max: 1000000,
      },
    ];

    const parsed = parseGoalFromNaturalLanguage(
      'Monthly SIP investment of 25000',
      schema
    );
    expect(parsed.investment_mode).toBe('MONTHLY_SIP');
    expect(parsed.target_amount).toBe(25000);

    const parsedLump = parseGoalFromNaturalLanguage(
      'One time lumpsum investment 1 lakh',
      schema
    );
    expect(parsedLump.investment_mode).toBe('ONE_TIME_LUMPSUM');
    expect(parsedLump.target_amount).toBe(100000);
  });

  it('parses purpose for KYC', () => {
    const schema: GoalFieldSpec[] = [
      {
        key: 'kyc_purpose',
        type: 'enum',
        label: 'Purpose',
        required: true,
        options: [
          { value: 'PERIODIC_UPDATE', label: 'Periodic Re-KYC Update' },
          { value: 'LIMIT_UPGRADE', label: 'Wallet Limit Upgrade' },
          { value: 'ADDRESS_CHANGE', label: 'Communication Address Change' },
        ],
      },
    ];

    const parsed = parseGoalFromNaturalLanguage(
      'Periodic re-kyc update for account',
      schema
    );
    expect(parsed.kyc_purpose).toBe('PERIODIC_UPDATE');

    const parsedUpgrade = parseGoalFromNaturalLanguage(
      'Need wallet limit upgrade',
      schema
    );
    expect(parsedUpgrade.kyc_purpose).toBe('LIMIT_UPGRADE');
  });

  it('parses account type and initial deposit for ACCOUNT_OPENING', () => {
    const schema: GoalFieldSpec[] = [
      {
        key: 'account_type',
        type: 'enum',
        label: 'Account Type',
        required: true,
        options: [
          { value: 'DIGITAL_SAVINGS', label: 'Digital Savings Account' },
          { value: 'SALARY_ACCOUNT', label: 'Corporate Salary Account' },
        ],
      },
      {
        key: 'initial_deposit',
        type: 'money',
        label: 'Initial Deposit',
        required: false,
        min: 0,
        max: 100000,
      },
    ];

    const parsed = parseGoalFromNaturalLanguage(
      'Digital savings account with 10000 initial deposit',
      schema
    );
    expect(parsed.account_type).toBe('DIGITAL_SAVINGS');
    expect(parsed.initial_deposit).toBe(10000);
  });
});
