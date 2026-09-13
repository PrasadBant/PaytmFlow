import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { JourneyDiff } from './JourneyDiff';
import type { components } from '@/api/types.gen';

type JourneyDiffType = components['schemas']['JourneyDiff'];

const mockDiff: JourneyDiffType = {
  from_version: 1,
  to_version: 2,
  fields_changed: [
    {
      key: 'monthly_income',
      label: 'Verified Monthly Income',
      from_status: 'BLOCKED',
      to_status: 'SATISFIED',
      display_value: '₹85,000',
      cause: 'ACTION:UPLOAD_INCOME_PROOF',
      cascaded: false,
    },
    {
      key: 'debt_to_income',
      label: 'Debt to Income Ratio',
      from_status: 'BLOCKED',
      to_status: 'SATISFIED',
      cause: 'CASCADE:INCOME_VERIFIED',
      cascaded: true,
    },
  ],
  actions_unlocked: ['UPLOAD_BANK_STATEMENT'],
  actions_removed: ['UPLOAD_INCOME_PROOF'],
  readiness: {
    from: 'NOT_READY',
    to: 'NOT_READY',
  },
  progress: {
    from: { completed: 3, pending: 3, blockers: 1, total: 7 },
    to: { completed: 4, pending: 2, blockers: 1, total: 7 },
  },
};

describe('JourneyDiff (F21)', () => {
  it('renders preview variant heading and badge', () => {
    render(<JourneyDiff diff={mockDiff} variant="preview" />);

    expect(screen.getByTestId('diff-heading')).toHaveTextContent('What will change');
    expect(screen.getByText('Preview')).toBeInTheDocument();
    expect(screen.getByTestId('version-badge')).toHaveTextContent('v1');
    expect(screen.getByTestId('version-badge')).toHaveTextContent('v2');
  });

  it('renders applied variant heading and badge', () => {
    render(<JourneyDiff diff={mockDiff} variant="applied" />);

    expect(screen.getByTestId('diff-heading')).toHaveTextContent('What changed');
    expect(screen.getByText('Applied')).toBeInTheDocument();
  });

  it('renders direct and cascaded field updates with values', () => {
    render(<JourneyDiff diff={mockDiff} variant="preview" />);

    expect(screen.getByText('Verified Monthly Income')).toBeInTheDocument();
    expect(screen.getByText('₹85,000')).toBeInTheDocument();

    expect(screen.getByText('Debt to Income Ratio')).toBeInTheDocument();
    expect(screen.getByTestId('cascaded-badge-debt_to_income')).toHaveTextContent('Cascaded');
  });

  it('renders unlocked actions and removed actions', () => {
    render(<JourneyDiff diff={mockDiff} variant="applied" />);

    expect(screen.getByTestId('unlocked-action-UPLOAD_BANK_STATEMENT')).toHaveTextContent('UPLOAD_BANK_STATEMENT');
    expect(screen.getByTestId('removed-action-UPLOAD_INCOME_PROOF')).toHaveTextContent('UPLOAD_INCOME_PROOF');
  });

  it('renders progress transition without percentages', () => {
    render(<JourneyDiff diff={mockDiff} variant="applied" />);

    expect(screen.getByTestId('diff-transitions')).toHaveTextContent('3/7');
    expect(screen.getByTestId('diff-transitions')).toHaveTextContent('4/7 Completed');
  });

  it('renders empty diff fallback message when there are no changes', () => {
    const emptyDiff: JourneyDiffType = {
      from_version: 1,
      to_version: 1,
      fields_changed: [],
      actions_unlocked: [],
      actions_removed: [],
      readiness: { from: 'NOT_READY', to: 'NOT_READY' },
      progress: {
        from: { completed: 3, pending: 3, blockers: 1, total: 7 },
        to: { completed: 3, pending: 3, blockers: 1, total: 7 },
      },
    };

    render(<JourneyDiff diff={emptyDiff} variant="applied" />);

    expect(screen.getByTestId('empty-diff-message')).toHaveTextContent('No state differences detected.');
  });

  it('strictly contains no percentage symbols or prohibited claims', () => {
    const { container } = render(<JourneyDiff diff={mockDiff} variant="preview" />);
    const html = container.innerHTML;

    expect(html).not.toContain('%');
    expect(html).not.toMatch(/\bscore\b/i);
    expect(html).not.toMatch(/\bapproval\b/i);
    expect(html).not.toMatch(/\bprobability\b/i);
    expect(html).not.toMatch(/\beligibility\b/i);
    expect(html).not.toMatch(/\bguaranteed\b/i);
  });
});
