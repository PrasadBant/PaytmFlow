import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { BlockerCard, type FieldState } from './BlockerCard';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge (F13)', () => {
  it('renders status using both icon and text (never color alone)', () => {
    const { rerender } = render(<StatusBadge status="SATISFIED" />);
    expect(screen.getByText('Satisfied')).toBeInTheDocument();
    expect(screen.getByTestId('status-badge')).toBeInTheDocument();

    rerender(<StatusBadge status="BLOCKED" />);
    expect(screen.getByText('Blocked')).toBeInTheDocument();

    rerender(<StatusBadge status="AMBIGUOUS" />);
    expect(screen.getByText('Needs Review')).toBeInTheDocument();

    rerender(<StatusBadge status="PENDING" />);
    expect(screen.getByText('Pending')).toBeInTheDocument();
  });

  it('allows custom label override', () => {
    render(<StatusBadge status="SATISFIED" label="Verified by OCR" />);
    expect(screen.getByText('Verified by OCR')).toBeInTheDocument();
  });
});

describe('BlockerCard (F13)', () => {
  const blockedField: FieldState = {
    key: 'monthly_income',
    label: 'Income Verification',
    status: 'BLOCKED',
    display_value: '₹85,000',
    explanation: 'Salary slip or bank statement is required to verify declared monthly income.',
    resolve_action_id: 'UPLOAD_INCOME_PROOF',
  };

  const satisfiedField: FieldState = {
    key: 'pan_number',
    label: 'PAN Verification',
    status: 'SATISFIED',
    display_value: 'ABCDE1234F',
    explanation: 'PAN details verified against government database.',
  };

  it('renders blocker field label, display value, explanation, and status badge', () => {
    render(
      <MemoryRouter>
        <BlockerCard field={blockedField} />
      </MemoryRouter>
    );

    expect(screen.getByText('Income Verification')).toBeInTheDocument();
    expect(screen.getByText('₹85,000')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Salary slip or bank statement is required to verify declared monthly income.'
      )
    ).toBeInTheDocument();
    expect(screen.getByText('Blocked')).toBeInTheDocument();
  });

  it('renders Resolve button with accessible name when resolve_action_id is present', () => {
    render(
      <MemoryRouter>
        <BlockerCard field={blockedField} />
      </MemoryRouter>
    );

    const resolveBtn = screen.getByRole('button', {
      name: /Resolve Income Verification/i,
    });
    expect(resolveBtn).toBeInTheDocument();
    expect(resolveBtn).toHaveTextContent('Resolve →');
  });

  it('fires onResolve callback when Resolve button is clicked', async () => {
    const user = userEvent.setup();
    const handleResolve = vi.fn();

    render(
      <MemoryRouter>
        <BlockerCard field={blockedField} onResolve={handleResolve} />
      </MemoryRouter>
    );

    const resolveBtn = screen.getByRole('button', {
      name: /Resolve Income Verification/i,
    });
    await user.click(resolveBtn);

    expect(handleResolve).toHaveBeenCalledTimes(1);
    expect(handleResolve).toHaveBeenCalledWith('UPLOAD_INCOME_PROOF', blockedField);
  });

  it('does NOT render Resolve button when field is SATISFIED', () => {
    render(
      <MemoryRouter>
        <BlockerCard field={satisfiedField} />
      </MemoryRouter>
    );

    expect(screen.getByText('PAN Verification')).toBeInTheDocument();
    expect(screen.getByText('Satisfied')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Resolve/i })).not.toBeInTheDocument();
  });

  it('renders resolveHref as a link when provided', () => {
    render(
      <MemoryRouter>
        <BlockerCard
          field={blockedField}
          resolveHref="/j/journey-1/act/UPLOAD_INCOME_PROOF"
        />
      </MemoryRouter>
    );

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/j/journey-1/act/UPLOAD_INCOME_PROOF');
  });

  it('strictly contains no prohibited words or claims', () => {
    const { container } = render(
      <MemoryRouter>
        <BlockerCard field={blockedField} />
      </MemoryRouter>
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
