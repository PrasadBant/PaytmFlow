import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { EvidenceCard } from './EvidenceCard';

describe('EvidenceCard (F20)', () => {
  const mockDetected = [
    { key: 'monthly_income', label: 'Net Monthly Income', display_value: '₹85,000' },
    { key: 'employer_name', label: 'Employer', display_value: 'Paytm Technologies Ltd' },
  ];

  it('renders filename, uploaded timestamp, and formatted size', () => {
    render(
      <EvidenceCard
        filename="salary_slip_aug_2026.pdf"
        uploadedAt="2026-09-12T10:05:00Z"
        sizeBytes={1428500}
        verified={true}
        detected={mockDetected}
      />
    );

    expect(screen.getByText('salary_slip_aug_2026.pdf')).toBeInTheDocument();
    expect(screen.getByText(/Uploaded/i)).toBeInTheDocument();
    expect(screen.getByText('1.36 MB')).toBeInTheDocument();
  });

  it('renders Verified badge when verified is true', () => {
    render(
      <EvidenceCard
        filename="doc.pdf"
        uploadedAt="2026-09-12T10:05:00Z"
        verified={true}
      />
    );

    expect(screen.getByTestId('evidence-badge-verified')).toHaveTextContent('Verified');
  });

  it('renders Review Needed badge when requiresReview is true', () => {
    render(
      <EvidenceCard
        filename="bank_statement.pdf"
        uploadedAt="2026-09-12T10:05:00Z"
        verified={false}
        requiresReview={true}
      />
    );

    expect(screen.getByTestId('evidence-badge-review')).toHaveTextContent('Review Needed');
  });

  it('renders extracted fields grid', () => {
    render(
      <EvidenceCard
        filename="salary.pdf"
        uploadedAt="2026-09-12T10:05:00Z"
        verified={true}
        detected={mockDetected}
      />
    );

    expect(screen.getByText('Net Monthly Income')).toBeInTheDocument();
    expect(screen.getByText('₹85,000')).toBeInTheDocument();
    expect(screen.getByText('Employer')).toBeInTheDocument();
    expect(screen.getByText('Paytm Technologies Ltd')).toBeInTheDocument();
  });

  it('never shows a hardcoded ₹85,000/Monthly Income headline for a document whose own detected field is unrelated to income (regression)', () => {
    // Root cause: this component used to render a fixed "₹ 85,000 / Monthly
    // Income Detected" headline unconditionally, regardless of `detected` -
    // so a Bank Statement, Address Proof, ITR, or any non-Lending pack's
    // evidence (PAN, FATCA, medical declaration, etc.) all showed the exact
    // same salary figure on Screen 7. The headline must always come from
    // THIS document's own first detected field.
    render(
      <EvidenceCard
        filename="itr_2025.pdf"
        uploadedAt="2026-09-12T10:05:00Z"
        verified={true}
        detected={[{ key: 'itr_verification', label: 'Income Tax Return (ITR)', display_value: 'Verified' }]}
      />
    );

    expect(screen.getByText('Verified', { selector: 'div.text-2xl' })).toBeInTheDocument();
    expect(screen.getByText('Income Tax Return (ITR)')).toBeInTheDocument();
    expect(screen.queryByText('₹ 85,000')).not.toBeInTheDocument();
    expect(screen.queryByText('Monthly Income Detected')).not.toBeInTheDocument();
  });

  it('renders no headline figure at all when nothing was detected, rather than fabricating one (regression)', () => {
    render(
      <EvidenceCard filename="unrelated_document.pdf" uploadedAt="2026-09-12T10:05:00Z" verified={false} detected={[]} />
    );

    expect(screen.queryByText('₹ 85,000')).not.toBeInTheDocument();
    expect(screen.queryByText(/Monthly Income Detected/)).not.toBeInTheDocument();
  });

  it('strictly contains no prohibited words', () => {
    const { container } = render(
      <EvidenceCard
        filename="salary.pdf"
        uploadedAt="2026-09-12T10:05:00Z"
        verified={true}
        detected={mockDetected}
      />
    );

    const html = container.innerHTML;
    expect(html).not.toMatch(/\bscore\b/i);
    expect(html).not.toMatch(/\bapproval\b/i);
    expect(html).not.toMatch(/\bprobability\b/i);
    expect(html).not.toMatch(/\beligibility\b/i);
    expect(html).not.toMatch(/\bguaranteed\b/i);
  });
});
