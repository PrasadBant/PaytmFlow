import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Screen06UploadEvidence } from '@/screens/Screen06UploadEvidence';

function renderScreen6(
  initialEntry = '/j/11111111-1111-1111-1111-111111111111/act/UPLOAD_INCOME_PROOF',
  locationState?: Record<string, unknown>
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[{ pathname: initialEntry, state: locationState }]}>
        <Routes>
          <Route path="/j/:id/act/:actionId" element={<Screen06UploadEvidence />} />
          <Route
            path="/j/:id/analysis"
            element={<div data-testid="screen-07-stub">AI Analysis Screen Stub</div>}
          />
          <Route
            path="/j/:id/next"
            element={<div data-testid="screen-05-stub">Recommendation Stub</div>}
          />
          <Route
            path="/j/:id"
            element={<div data-testid="screen-04-stub">Current Status Stub</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Screen06UploadEvidence (F19)', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('renders title, back button, and all 3 tabs', async () => {
    renderScreen6();

    expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument();
    expect(screen.getByTestId('back-to-rec-btn')).toBeInTheDocument();

    expect(screen.getByRole('tab', { name: /Upload File/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Enter Details/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /How it helps/i })).toBeInTheDocument();
  });

  it('uploads a file from Tab 1 and navigates to AI analysis screen', async () => {
    const user = userEvent.setup();
    renderScreen6();

    await screen.findByRole('heading', { level: 1 });

    const fileInput = screen.getByTestId('evidence-file-input');
    const validFile = new File(['dummy salary slip'], 'salary_aug_2026.pdf', {
      type: 'application/pdf',
    });

    fireEvent.change(fileInput, { target: { files: [validFile] } });

    expect(await screen.findByText('salary_aug_2026.pdf')).toBeInTheDocument();

    const submitBtn = screen.getByTestId('upload-submit-btn');
    expect(submitBtn).toBeEnabled();

    await user.click(submitBtn);

    expect(await screen.findByTestId('screen-07-stub')).toBeInTheDocument();
  });

  it('switches to Enter Details tab and submits manual schema form', async () => {
    const user = userEvent.setup();
    renderScreen6();

    await screen.findByRole('heading', { level: 1 });

    const manualTab = screen.getByRole('tab', { name: /Enter Details/i });
    await user.click(manualTab);

    expect(await screen.findByTestId('tabpanel-manual')).toBeInTheDocument();
    expect(screen.getByLabelText(/Net Monthly Income/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Employer or Organization Name/i)).toBeInTheDocument();

    const incomeInput = screen.getByLabelText(/Net Monthly Income/i);
    const employerInput = screen.getByLabelText(/Employer or Organization Name/i);

    await user.clear(incomeInput);
    await user.type(incomeInput, '85000');
    await user.type(employerInput, 'Paytm Technologies Ltd');

    const submitBtn = screen.getByRole('button', { name: /Submit Details/i });
    await user.click(submitBtn);

    expect(await screen.findByTestId('screen-07-stub')).toBeInTheDocument();
  });

  it('switches to How it helps tab and displays guidance copy', async () => {
    const user = userEvent.setup();
    renderScreen6();

    await screen.findByRole('heading', { level: 1 });

    const helpTab = screen.getByRole('tab', { name: /How it helps/i });
    await user.click(helpTab);

    expect(await screen.findByTestId('tabpanel-help')).toBeInTheDocument();
    expect(screen.getByText(/Why is this evidence requested\?/i)).toBeInTheDocument();
    expect(screen.getByText(/What we verify/i)).toBeInTheDocument();
    expect(screen.getByText(/Safe & Deterministic Processing/i)).toBeInTheDocument();
  });

  it('strictly contains no prohibited words or percentage indicators', async () => {
    const { container } = renderScreen6();

    await screen.findByRole('heading', { level: 1 });

    const html = container.innerHTML;
    expect(html).not.toContain('%');
    expect(html).not.toMatch(/\bscore\b/i);
    expect(html).not.toMatch(/\bapproval\b/i);
    expect(html).not.toMatch(/\bprobability\b/i);
    expect(html).not.toMatch(/\beligibility\b/i);
    expect(html).not.toMatch(/\bguaranteed\b/i);
  });

  describe('action-kind-aware rendering (regression)', () => {
    // This screen previously hardcoded "Upload Income Proof" and always showed all 3
    // evidence-oriented tabs, regardless of what resolve_action_id actually pointed to.
    // Every BLOCKED field's resolve_action_id - Employment Category, Current Employer,
    // Final Loan Agreement, etc. - opened this exact same upload UI. These tests prove
    // the rendered UI is now genuinely different per ActionOption.kind.

    it('EVIDENCE action: shows action title, and all 3 tabs including Upload File', async () => {
      renderScreen6('/j/11111111-1111-1111-1111-111111111111/act/UPLOAD_BANK_STATEMENT', {
        action: {
          action_id: 'UPLOAD_BANK_STATEMENT',
          title: 'Upload Bank Statement',
          kind: 'EVIDENCE',
          why: 'Required to verify salary credits.',
          unlocks: [],
          accepts: ['BANK_STATEMENT'],
        },
        snapshotId: '33333333-3333-3333-3333-333333333333',
      });

      const heading = await screen.findByRole('heading', { level: 1 });
      expect(heading).toHaveTextContent('Upload Bank Statement');
      expect(heading).not.toHaveTextContent('Upload Income Proof');

      expect(screen.getByRole('tab', { name: /Upload File/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /Enter Details/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /How it helps/i })).toBeInTheDocument();
      expect(screen.getByTestId('tabpanel-upload')).toBeInTheDocument();
      expect(screen.getByTestId('evidence-file-input')).toBeInTheDocument();
    });

    it('FORM action: shows action title, only 1 tab, and no upload UI at all', async () => {
      renderScreen6('/j/11111111-1111-1111-1111-111111111111/act/SUBMIT_EMPLOYMENT_INFO', {
        action: {
          action_id: 'SUBMIT_EMPLOYMENT_INFO',
          title: 'Confirm Employment Category',
          kind: 'FORM',
          why: 'We need your current employment category to proceed.',
          unlocks: [],
          input_schema: [
            {
              key: 'employment_category',
              type: 'text',
              label: 'Employment Category',
              required: true,
            },
          ],
        },
        snapshotId: '33333333-3333-3333-3333-333333333333',
      });

      const heading = await screen.findByRole('heading', { level: 1 });
      expect(heading).toHaveTextContent('Confirm Employment Category');
      expect(heading).not.toHaveTextContent('Upload Income Proof');

      // Only one tab is offered - no Upload File / How it helps for a FORM action.
      expect(screen.queryByRole('tab', { name: /Upload File/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('tab', { name: /How it helps/i })).not.toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /Enter Details/i })).toBeInTheDocument();

      // The manual-entry panel is shown by default (no click needed), using the
      // action's own input_schema, and with FORM-appropriate (non-upload) copy.
      expect(await screen.findByTestId('tabpanel-manual')).toBeInTheDocument();
      expect(screen.getByLabelText(/Employment Category/i)).toBeInTheDocument();
      expect(screen.queryByTestId('evidence-file-input')).not.toBeInTheDocument();
      expect(screen.queryByText(/Do not have the document handy/i)).not.toBeInTheDocument();
    });

    it('CLARIFICATION action: never renders the upload/form screen, redirects to Screen 4 instead', async () => {
      renderScreen6('/j/11111111-1111-1111-1111-111111111111/act/CLARIFY_MONTHLY_INCOME', {
        action: {
          action_id: 'CLARIFY_MONTHLY_INCOME',
          title: 'Clarify Monthly Income',
          kind: 'CLARIFICATION',
          why: 'Salary credit amount does not match the declared income.',
          unlocks: [],
        },
        snapshotId: '33333333-3333-3333-3333-333333333333',
      });

      // Never shows the upload/form screen for a clarification - it has no matching UI.
      expect(screen.queryByTestId('screen-06-upload-evidence')).not.toBeInTheDocument();
      expect(await screen.findByTestId('screen-04-stub')).toBeInTheDocument();
    });
  });
});
