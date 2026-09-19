import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import { resetMockState } from '@/mocks/handlers';
import { ReviewDashboard } from '@/screens/review/ReviewDashboard';
import { ReviewQueue } from '@/screens/review/ReviewQueue';
import { ReviewCaseDetail } from '@/screens/review/ReviewCaseDetail';
import { ReviewStatusCard } from '@/components/ReviewStatusCard';

function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

async function becomeReviewer(): Promise<void> {
  await fetch('/api/v1/review/role', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role: 'REVIEW_OFFICER' }),
  });
}

function renderWithProviders(ui: React.ReactElement, initialEntry: string) {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/review" element={ui} />
          <Route path="/review/queue" element={<ReviewQueue />} />
          <Route path="/review/case/:caseId" element={<ReviewCaseDetail />} />
          <Route path="/j/:id" element={<div data-testid="status-stub" />} />
          <Route path="/j/:id/next" element={<div data-testid="recommendation-stub" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const DEMO_CASE_ID = 'aaaaaaaa-1024-4000-8000-000000001024';

describe('Review Center (Human Review / Exception Resolution)', () => {
  beforeEach(async () => {
    resetMockState();
    await becomeReviewer();
  });

  it('dashboard shows real, non-fabricated metrics with no banned words', async () => {
    const { container } = renderWithProviders(<ReviewDashboard />, '/review');

    await screen.findByTestId('review-metric-grid');
    expect(screen.getByTestId('metric-pending_review')).toHaveTextContent('1');

    const html = container.innerHTML;
    expect(html).not.toContain('%');
    expect(html).not.toMatch(/\bscore\b/i);
    expect(html).not.toMatch(/\bapproval\b/i);
    expect(html).not.toMatch(/\bapproved\b/i);
    expect(html).not.toMatch(/\bguaranteed\b/i);
  });

  it('queue lists the demo case and filters by tab', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReviewQueue />, '/review/queue');

    await screen.findByTestId(`review-case-row-${DEMO_CASE_ID}`);

    const resolvedTab = screen.getByRole('tab', { name: /Resolved/i });
    await user.click(resolvedTab);

    await waitFor(() => {
      expect(screen.queryByTestId(`review-case-row-${DEMO_CASE_ID}`)).not.toBeInTheDocument();
    });
  });

  it('case detail shows why-flagged, AI findings evidence comparison, and journey context', async () => {
    server.use(
      http.get('*/api/v1/review/cases/:case_id', () => {
        return HttpResponse.json({
          case_id: DEMO_CASE_ID,
          case_number: 'PF-DEMO-1024',
          journey_id: '11111111-1111-1111-1111-111111111111',
          journey_type: 'LENDING',
          journey_display_name: 'Personal Loan',
          field_key: 'monthly_income',
          reason_code: 'INCOME_MISMATCH',
          reason_title: 'Bank statement credit differs from salary slip',
          reason_description: 'Salary Slip: ₹50,000. Bank Evidence: ₹35,000.',
          priority: 'MEDIUM',
          status: 'UNDER_REVIEW',
          case_version: 2,
          assigned_reviewer: 'Reviewer-mock',
          is_locked: true,
          resolution_type: null,
          resolution_reason: null,
          resolution_notes: null,
          requested_information: null,
          escalation_reason: null,
          created_at: '2026-09-19T04:00:00Z',
          updated_at: '2026-09-19T04:00:00Z',
          resolved_at: null,
          journey_context: {
            journey_id: '11111111-1111-1111-1111-111111111111',
            journey_type: 'LENDING',
            schema_version: '1.0.0',
            snapshot_id: '22222222-2222-2222-2222-222222222222',
            version_number: 2,
            readiness: 'NEEDS_REVIEW',
            status: 'NEEDS_REVIEW',
            fields: [
              { key: 'monthly_income', label: 'Monthly Net Income', status: 'AMBIGUOUS' },
            ],
            progress: { completed: 3, pending: 3, blockers: 1, total: 7 },
            display: { title: 'Personal Loan', summary: '₹2,00,000' },
            updated_at: '2026-09-19T04:00:00Z',
          },
          evidence: [
            {
              evidence_id: 'e1',
              doc_type: 'SALARY_SLIP',
              filename: 'slip.pdf',
              uploaded_at: '2026-09-19T03:58:00Z',
              verified: true,
              confidence: 0.91,
              extracted_values: { monthly_income: 50000 },
            },
            {
              evidence_id: 'e2',
              doc_type: 'BANK_STATEMENT',
              filename: 'bank.pdf',
              uploaded_at: '2026-09-19T03:59:00Z',
              verified: true,
              confidence: 0.88,
              extracted_values: { monthly_income: 35000 },
            },
          ],
        });
      })
    );

    renderWithProviders(<ReviewCaseDetail />, `/review/case/${DEMO_CASE_ID}`);

    await screen.findByTestId('review-case-detail');
    expect(screen.getByText(/Automation could not confidently resolve/i)).toBeInTheDocument();
    expect(screen.getByTestId('evidence-e1')).toBeInTheDocument();
    expect(screen.getByTestId('evidence-e2')).toBeInTheDocument();
    expect(screen.getByTestId('resolution-type-select')).toBeInTheDocument();
  });

  it('reviewer must claim before the resolution form is enabled', async () => {
    renderWithProviders(<ReviewCaseDetail />, `/review/case/${DEMO_CASE_ID}`);

    await screen.findByTestId('review-case-detail');
    expect(screen.getByText(/Claim this case to act on it/i)).toBeInTheDocument();
    expect(screen.queryByTestId('resolution-type-select')).not.toBeInTheDocument();
  });

  it('resolution requires a reason before submitting', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReviewCaseDetail />, `/review/case/${DEMO_CASE_ID}`);

    await screen.findByTestId('review-case-detail');
    const claimBtn = screen.getByRole('button', { name: /Claim Case/i });
    await user.click(claimBtn);

    const resolutionValueInput = await screen.findByTestId('resolution-value-input');
    await user.click(screen.getByTestId('submit-resolution-btn'));

    expect(await screen.findByTestId('resolution-form-error')).toBeInTheDocument();
    expect(resolutionValueInput).toBeInTheDocument();
  });

  it('handles REQUEST_ADDITIONAL_INFORMATION flow with doc tags and live customer preview', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReviewCaseDetail />, `/review/case/${DEMO_CASE_ID}`);

    await screen.findByTestId('review-case-detail');
    const claimBtn = screen.getByRole('button', { name: /Claim Case/i });
    await user.click(claimBtn);

    const select = await screen.findByTestId('resolution-type-select');
    await user.selectOptions(select, 'REQUEST_ADDITIONAL_INFORMATION');

    expect(await screen.findByTestId('requested-docs-input')).toBeInTheDocument();
    expect(screen.getByTestId('customer-message-input')).toBeInTheDocument();

    const docTag = screen.getByRole('button', { name: /\+ Bank Statement/i });
    await user.click(docTag);

    expect(screen.getByTestId('requested-docs-input')).toHaveValue('Bank Statement (PDF)');

    await user.type(screen.getByTestId('customer-message-input'), 'Please upload your latest bank statement.');

    expect(screen.getByText(/Live Customer Experience Preview/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Bank Statement \(PDF\)/i).length).toBeGreaterThanOrEqual(2);
  });

  it('handles ESCALATE_FOR_SPECIALIST_REVIEW flow with category and reason', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ReviewCaseDetail />, `/review/case/${DEMO_CASE_ID}`);

    await screen.findByTestId('review-case-detail');
    const claimBtn = screen.getByRole('button', { name: /Claim Case/i });
    await user.click(claimBtn);

    const select = await screen.findByTestId('resolution-type-select');
    await user.selectOptions(select, 'ESCALATE_FOR_SPECIALIST_REVIEW');

    expect(await screen.findByLabelText(/Escalation Category/i)).toBeInTheDocument();
    expect(screen.getByTestId('resolution-reason-input')).toBeInTheDocument();

    await user.type(screen.getByTestId('resolution-reason-input'), 'Income tax returns show conflicting gross turnover.');

    const submitBtn = screen.getByTestId('submit-resolution-btn');
    await user.click(submitBtn);

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Escalate Case to Underwriting Specialist/i)).toBeInTheDocument();
  });

  it('shows state-aware waiting for customer banner when status is ADDITIONAL_INFO_REQUIRED', async () => {
    server.use(
      http.get('*/api/v1/review/cases/:case_id', () => {
        return HttpResponse.json({
          case_id: DEMO_CASE_ID,
          case_number: 'PF-DEMO-1024',
          journey_id: '11111111-1111-1111-1111-111111111111',
          journey_type: 'LENDING',
          journey_display_name: 'Personal Loan',
          field_key: 'monthly_income',
          reason_code: 'INCOME_MISMATCH',
          reason_title: 'Bank statement credit differs from salary slip',
          reason_description: 'Salary Slip: ₹50,000. Bank Evidence: ₹35,000.',
          priority: 'HIGH',
          status: 'ADDITIONAL_INFO_REQUIRED',
          case_version: 3,
          assigned_reviewer: 'Reviewer-mock',
          is_locked: false,
          resolution_type: null,
          resolution_reason: null,
          resolution_notes: null,
          requested_information: {
            requested_docs: ['Latest 3-Month Salary Slip', 'Bank Statement'],
            customer_message: 'Please provide certified documents.',
          },
          escalation_reason: null,
          created_at: '2026-09-19T04:00:00Z',
          updated_at: '2026-09-19T04:30:00Z',
          resolved_at: null,
          journey_context: {
            journey_id: '11111111-1111-1111-1111-111111111111',
            journey_type: 'LENDING',
            schema_version: '1.0.0',
            snapshot_id: '22222222-2222-2222-2222-222222222222',
            version_number: 3,
            readiness: 'NEEDS_REVIEW',
            status: 'NEEDS_REVIEW',
            fields: [
              { key: 'monthly_income', label: 'Monthly Net Income', status: 'AMBIGUOUS' },
            ],
            progress: { completed: 3, pending: 3, blockers: 1, total: 7 },
            display: { title: 'Personal Loan', summary: '₹2,00,000' },
            updated_at: '2026-09-19T04:30:00Z',
          },
          evidence: [],
        });
      })
    );

    renderWithProviders(<ReviewCaseDetail />, `/review/case/${DEMO_CASE_ID}`);

    await screen.findByTestId('review-case-detail');
    expect(screen.getByText(/Waiting on Customer Response/i)).toBeInTheDocument();
    expect(screen.getByText(/Latest 3-Month Salary Slip, Bank Statement/i)).toBeInTheDocument();
    expect(screen.getByText(/Please provide certified documents/i)).toBeInTheDocument();
  });

  it('displays audit timeline with categorized actors and chronological events', async () => {
    server.use(
      http.get('*/api/v1/review/cases/:case_id/audit', () => {
        return HttpResponse.json({
          entries: [
            { event_type: 'CUSTOMER_EVIDENCE_UPLOADED', payload: {}, created_at: '2026-09-19T04:00:00Z' },
            { event_type: 'REVIEW_CASE_CREATED', payload: {}, created_at: '2026-09-19T04:01:00Z' },
            { event_type: 'AI_EXTRACTION_COMPLETED', payload: {}, created_at: '2026-09-19T04:02:00Z' },
            { event_type: 'REVIEWER_CLAIMED_CASE', payload: { reviewer: 'Officer-Anjali' }, created_at: '2026-09-19T04:05:00Z' },
          ],
        });
      })
    );

    renderWithProviders(<ReviewCaseDetail />, `/review/case/${DEMO_CASE_ID}`);

    await screen.findByTestId('review-case-detail');
    const timeline = await screen.findByTestId('audit-timeline');
    expect(timeline).toBeInTheDocument();
    expect(within(timeline).getByText('Customer')).toBeInTheDocument();
    expect(within(timeline).getByText('System')).toBeInTheDocument();
    expect(within(timeline).getByText('AI Model')).toBeInTheDocument();
    expect(within(timeline).getByText('Reviewer')).toBeInTheDocument();
    expect(within(timeline).getByText(/Officer-Anjali/i)).toBeInTheDocument();
  });

  it('customer-facing review status card shows customer-safe copy, no internal metadata', async () => {
    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter initialEntries={['/j/11111111-1111-1111-1111-111111111111']}>
          <Routes>
            <Route
              path="/j/:id"
              element={<ReviewStatusCard journeyId="11111111-1111-1111-1111-111111111111" />}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    const card = await screen.findByTestId('review-status-card');
    expect(card).toHaveTextContent('Additional verification required');
    expect(card.innerHTML).not.toContain(DEMO_CASE_ID);
    expect(card.innerHTML).not.toMatch(/reviewer/i);
  });
});
