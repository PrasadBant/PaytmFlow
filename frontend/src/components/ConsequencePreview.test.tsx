import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ConsequencePreview } from './ConsequencePreview';

describe('ConsequencePreview (F20)', () => {
  const mockPreview = {
    newly_satisfied: [
      { key: 'monthly_income', label: 'Verified Monthly Income' },
    ],
    newly_unlocked: [
      { action_id: 'UPLOAD_BANK_STATEMENT', title: 'Upload Bank Statement' },
    ],
    still_blocked: [
      { key: 'pan_verification', label: 'PAN Card Verification' },
    ],
    predicted_readiness: 'NOT_READY' as const,
    progress_before: { completed: 3, pending: 3, blockers: 1, total: 7 },
    progress_after: { completed: 4, pending: 2, blockers: 1, total: 7 },
  };

  it('renders deterministic outcome header and items', () => {
    render(<ConsequencePreview preview={mockPreview} />);

    expect(screen.getByText('Expected Outcome')).toBeInTheDocument();
    expect(screen.getByText('Deterministic Preview')).toBeInTheDocument();

    expect(screen.getByText('Verified Monthly Income')).toBeInTheDocument();
    expect(screen.getByText('→ Completed')).toBeInTheDocument();

    expect(screen.getByText('Upload Bank Statement')).toBeInTheDocument();
    expect(screen.getByText('→ Unlocked')).toBeInTheDocument();

    expect(screen.getByText('PAN Card Verification')).toBeInTheDocument();
    expect(screen.getByText('→ Still Blocked')).toBeInTheDocument();
  });

  it('renders overall progress transition correctly without percentage', () => {
    render(<ConsequencePreview preview={mockPreview} />);

    expect(screen.getByTestId('predicted-progress')).toHaveTextContent('4/7 Completed');
  });

  it('strictly contains no percentage or prohibited claims', () => {
    const { container } = render(<ConsequencePreview preview={mockPreview} />);
    const html = container.innerHTML;

    expect(html).not.toContain('%');
    expect(html).not.toMatch(/\bscore\b/i);
    expect(html).not.toMatch(/\bapproval\b/i);
    expect(html).not.toMatch(/\bprobability\b/i);
    expect(html).not.toMatch(/\beligibility\b/i);
    expect(html).not.toMatch(/\bguaranteed\b/i);
  });

  it('regression: never fabricates a claim when the API reports nothing newly satisfied/unlocked', () => {
    // newly_satisfied/newly_unlocked are legitimately-empty-capable arrays per the
    // contract (e.g. an action that satisfies a field but unlocks no new action).
    // This component previously hardcoded a LENDING-specific "Income verification"
    // / "Loan eligibility calculation" fallback here regardless of pack or actual
    // API data - a fabricated claim and a journey-specific branching violation.
    const emptyPreview = {
      newly_satisfied: [],
      newly_unlocked: [],
      still_blocked: [],
      predicted_readiness: 'NOT_READY' as const,
      progress_before: { completed: 3, pending: 3, blockers: 1, total: 7 },
      progress_after: { completed: 3, pending: 3, blockers: 1, total: 7 },
    };
    render(<ConsequencePreview preview={emptyPreview} />);

    expect(screen.queryByText(/Income verification/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Loan eligibility calculation/i)).not.toBeInTheDocument();
    // The real, provided progress is shown - not a hardcoded fallback count.
    expect(screen.getByTestId('predicted-progress')).toHaveTextContent('3/7 Completed');
  });
});
