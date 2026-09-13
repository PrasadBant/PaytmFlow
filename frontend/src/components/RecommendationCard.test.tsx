import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { RecommendationCard, type ActionOption } from './RecommendationCard';
import { ActionList } from './ActionList';
import { AssistantHelpCard } from './AssistantHelpCard';

describe('RecommendationCard (F15)', () => {
  const sampleAction: ActionOption = {
    action_id: 'UPLOAD_INCOME_PROOF',
    title: 'Upload Salary Slip',
    kind: 'EVIDENCE',
    why: 'Uploading your latest salary slip verifies your net monthly income and unlocks loan limit calculation.',
    unlocks: ['monthly_income', 'bank_statement'],
    accepts: ['application/pdf', 'image/jpeg', 'image/png'],
  };

  it('renders title, explanation, and an accessible (non-visual) kind label', () => {
    // The reference design has no "Recommended Next Action" / "Document Upload"
    // badges and no "unlocks" pill row - just an icon, title, and description.
    // The kind is still available to assistive tech via sr-only text.
    render(<RecommendationCard action={sampleAction} onSelect={vi.fn()} />);

    expect(screen.getByText('Upload Salary Slip')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Uploading your latest salary slip verifies your net monthly income and unlocks loan limit calculation.'
      )
    ).toBeInTheDocument();
    expect(screen.queryByText('Recommended Next Action')).not.toBeInTheDocument();
    expect(screen.getByText('Document Upload')).toHaveClass('sr-only');
    expect(screen.queryByText('monthly income')).not.toBeInTheDocument();
    expect(screen.queryByText('bank statement')).not.toBeInTheDocument();
  });

  it('fires onSelect when CTA button is clicked', async () => {
    const user = userEvent.setup();
    const handleSelect = vi.fn();

    render(<RecommendationCard action={sampleAction} onSelect={handleSelect} />);

    const ctaBtn = screen.getByRole('button', {
      name: /Take action: Upload Salary Slip/i,
    });
    await user.click(ctaBtn);

    expect(handleSelect).toHaveBeenCalledTimes(1);
    expect(handleSelect).toHaveBeenCalledWith(sampleAction);
  });
});

describe('ActionList (F15)', () => {
  const alternatives: ActionOption[] = [
    {
      action_id: 'SET_LOAN_TENURE',
      title: 'Adjust Loan Tenure',
      kind: 'FORM',
      why: 'Modify repayment tenure to adjust monthly EMI projections.',
      unlocks: ['tenure_months'],
    },
    {
      action_id: 'ADD_EMPLOYMENT_DETAILS',
      title: 'Update Employer Details',
      kind: 'FORM',
      why: 'Add employer name and work experience for faster credit assessment.',
      unlocks: ['employment_type'],
    },
  ];

  it('renders all alternatives dynamically from array as compact rows in one container', () => {
    // The reference shows compact single-line rows (icon + title + chevron) inside
    // one bordered container, not separate cards with a description line each.
    const { container } = render(<ActionList alternatives={alternatives} onSelect={vi.fn()} />);

    expect(screen.getByText('Alternative Options (2)')).toBeInTheDocument();
    expect(screen.getByText('Adjust Loan Tenure')).toBeInTheDocument();
    expect(screen.getByText('Update Employer Details')).toBeInTheDocument();
    // Only one outer container card, not one per alternative.
    expect(container.querySelectorAll('[data-testid^="action-option-"]')).toHaveLength(2);
  });

  it('calls onSelect with chosen alternative', async () => {
    const user = userEvent.setup();
    const handleSelect = vi.fn();

    render(<ActionList alternatives={alternatives} onSelect={handleSelect} />);

    const selectBtn = screen.getByRole('button', {
      name: /Select alternative action: Adjust Loan Tenure/i,
    });
    await user.click(selectBtn);

    expect(handleSelect).toHaveBeenCalledTimes(1);
    expect(handleSelect).toHaveBeenCalledWith(alternatives[0]);
  });

  it('renders null when alternatives array is empty', () => {
    const { container } = render(<ActionList alternatives={[]} onSelect={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('AssistantHelpCard (F15)', () => {
  it('renders guidance title, description, and tips', () => {
    render(
      <AssistantHelpCard
        title="Verification Assistance"
        description="Tips for fast automated verification."
        tips={['Upload clear PDF documents.', 'Check matching PAN records.']}
      />
    );

    expect(screen.getByText('Verification Assistance')).toBeInTheDocument();
    expect(screen.getByText('Tips for fast automated verification.')).toBeInTheDocument();
    expect(screen.getByText('Upload clear PDF documents.')).toBeInTheDocument();
    expect(screen.getByText('Check matching PAN records.')).toBeInTheDocument();
  });

  it('strictly asserts absence of prohibited words in all F15 components', () => {
    const sampleAction: ActionOption = {
      action_id: 'ACT_1',
      title: 'Verify Income',
      kind: 'EVIDENCE',
      why: 'Provides necessary income record for processing.',
      unlocks: ['income'],
    };

    const { container } = render(
      <div>
        <RecommendationCard action={sampleAction} onSelect={vi.fn()} />
        <ActionList alternatives={[sampleAction]} onSelect={vi.fn()} />
        <AssistantHelpCard />
      </div>
    );

    const html = container.innerHTML;
    expect(html).not.toContain('%');
    expect(html).not.toMatch(/\bscore\b/i);
    expect(html).not.toMatch(/\bapproval\b/i);
    expect(html).not.toMatch(/\bprobability\b/i);
    expect(html).not.toMatch(/\beligibility\b/i);
    expect(html).not.toMatch(/\bguaranteed\b/i);
  });
});
