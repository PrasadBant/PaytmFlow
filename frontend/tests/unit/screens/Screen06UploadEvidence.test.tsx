import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
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
            path="/j/:id/updated"
            element={<div data-testid="screen-08-stub">Updated Status Stub</div>}
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
    server.resetHandlers();
  });

  it('renders title, back button, and active tabs', async () => {
    renderScreen6();

    expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument();
    expect(screen.getByTestId('back-to-rec-btn')).toBeInTheDocument();

    expect(screen.getByRole('tab', { name: /Upload File/i })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /Enter Details/i })).not.toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /How it helps/i })).toBeInTheDocument();
  });

  it('uploads a file from Tab 1 and navigates to AI analysis screen', async () => {
    server.use(
      http.post('*/api/v1/journeys/:journey_id/evidence', async () => {
        return HttpResponse.json({
          evidence_id: 'evi-upload-test',
          filename: 'salary_aug_2026.pdf',
          uploaded_at: new Date().toISOString(),
          size_bytes: 100,
          interpretation: {
            verified: true,
            confidence: 0.95,
            detected: [],
            summary: 'Salary slip verified',
            conflicts: [],
          },
          proposed_action_id: 'UPLOAD_INCOME_PROOF',
          consequence_preview: null,
          diff_preview: null,
          requires_review: false,
        });
      })
    );

    const user = userEvent.setup();
    renderScreen6('/j/11111111-1111-1111-1111-111111111111/act/UPLOAD_INCOME_PROOF', {
      action: {
        action_id: 'UPLOAD_INCOME_PROOF',
        title: 'Upload Salary Slip',
        kind: 'EVIDENCE',
        why: 'Uploading your latest salary slip verifies your net monthly income and unlocks your loan limit calculation.',
        unlocks: ['monthly_income', 'bank_statement'],
        accepts: ['SALARY_SLIP', 'BANK_STATEMENT'],
      },
      snapshotId: '11111111-1111-4111-8111-111111111111',
    });

    await screen.findByRole('heading', { level: 1 });

    const fileInput = screen.getByTestId('evidence-file-input');
    const validFile = new File(['dummy salary slip'], 'salary_aug_2026.pdf', {
      type: 'application/pdf',
    });

    fireEvent.change(fileInput, { target: { files: [validFile] } });

    expect(await screen.findByText('salary_aug_2026.pdf')).toBeInTheDocument();

    const submitBtn = screen.getByTestId('upload-submit-btn');
    const select = await screen.findByTestId('doc-type-select');
    await user.selectOptions(select, 'SALARY_SLIP');
    expect(submitBtn).toBeEnabled();

    await user.click(submitBtn);

    expect(await screen.findByTestId('screen-07-stub', {}, { timeout: 3000 })).toBeInTheDocument();
  });

  it('EVIDENCE action with no input_schema: Enter Details tab is omitted so dead-end placeholder is never rendered (Error 2 & 10)', async () => {
    // Error 2 & 10: If an action has no usable manual-entry/input_schema,
    // do NOT render Enter Details. Evidence-only actions should show only the
    // evidence interaction. Never render a dead-end manual form.
    renderScreen6();

    await screen.findByRole('heading', { level: 1 });

    // The Enter Details tab must NOT be rendered
    expect(screen.queryByRole('tab', { name: /Enter Details/i })).not.toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Upload File/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /How it helps/i })).toBeInTheDocument();

    // No invented fields anywhere on the panel.
    expect(screen.queryByLabelText(/Net Monthly Income/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Employer.*Organization Name/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/85,?000/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Submit Details/i })).not.toBeInTheDocument();
  });

  it('EVIDENCE action with a genuine input_schema: renders and submits that schema dynamically, never a substituted one (regression)', async () => {
    // The inverse of the above: when the contract DOES provide a real schema
    // for an EVIDENCE action, it must render and submit that schema - never
    // fall back to the generic message, and never substitute another
    // action's fields.
    const user = userEvent.setup();
    renderScreen6('/j/22222222-2222-2222-2222-222222222222/act/UPLOAD_MEDICAL_RECORDS', {
      action: {
        action_id: 'UPLOAD_MEDICAL_RECORDS',
        title: 'Pre-existing Disease Clearance',
        kind: 'EVIDENCE',
        why: 'Past hospitalization or treatment records required for underwriting',
        unlocks: [],
        accepts: ['MEDICAL_RECORDS'],
        input_schema: [
          {
            key: 'condition_summary',
            type: 'text',
            label: 'Condition Summary',
            required: true,
          },
        ],
      },
      snapshotId: '33333333-3333-3333-3333-333333333333',
    });

    await screen.findByRole('heading', { level: 1 });
    await user.click(screen.getByRole('tab', { name: /Enter Details/i }));

    expect(await screen.findByTestId('tabpanel-manual')).toBeInTheDocument();
    expect(screen.queryByTestId('manual-entry-unavailable')).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Condition Summary/i)).toBeInTheDocument();
    // Never the Lending fallback, and never another pack's field.
    expect(screen.queryByLabelText(/Net Monthly Income/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Employer.*Organization Name/i)).not.toBeInTheDocument();

    await user.type(screen.getByLabelText(/Condition Summary/i), 'Fully resolved, one-time event');
    await user.click(screen.getByRole('button', { name: /Submit Details/i }));

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
      // Error 2 & 10: actions without input_schema do NOT render Enter Details dead-end tab
      expect(screen.queryByRole('tab', { name: /Enter Details/i })).not.toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /How it helps/i })).toBeInTheDocument();
      expect(screen.getByTestId('tabpanel-upload')).toBeInTheDocument();
      expect(screen.getByTestId('evidence-file-input')).toBeInTheDocument();
    });

    it('EVIDENCE action with input_schema: shows both Upload File and Enter Details tabs', async () => {
      renderScreen6('/j/11111111-1111-1111-1111-111111111111/act/UPLOAD_BANK_STATEMENT', {
        action: {
          action_id: 'UPLOAD_BANK_STATEMENT',
          title: 'Upload Bank Statement',
          kind: 'EVIDENCE',
          why: 'Required to verify salary credits.',
          unlocks: [],
          accepts: ['BANK_STATEMENT'],
          input_schema: [
            {
              key: 'account_number',
              type: 'text',
              label: 'Account Number',
              required: true,
            },
          ],
        },
        snapshotId: '33333333-3333-3333-3333-333333333333',
      });

      const heading = await screen.findByRole('heading', { level: 1 });
      expect(heading).toHaveTextContent('Upload Bank Statement');

      expect(screen.getByRole('tab', { name: /Upload File/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /Enter Details/i })).toBeInTheDocument();
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

    it('FORM action with a missing input_schema (contract violation): shows the safe fallback state, never invented fields (defensive regression)', async () => {
      // A FORM action should always carry an input_schema per contract, but
      // if one is ever missing this must not silently render another
      // action's schema (or the old Lending-specific fallback) - it must
      // fail safely with the same generic "not available" state.
      renderScreen6('/j/44444444-4444-4444-4444-444444444444/act/VERIFY_EMPLOYMENT', {
        action: {
          action_id: 'VERIFY_EMPLOYMENT',
          title: 'Employment Verification',
          kind: 'FORM',
          why: 'Confirm current employer and employment type for underwriting',
          unlocks: [],
          input_schema: null,
        },
        snapshotId: '33333333-3333-3333-3333-333333333333',
      });

      expect(await screen.findByTestId('tabpanel-manual')).toBeInTheDocument();
      expect(await screen.findByTestId('manual-entry-unavailable')).toBeInTheDocument();
      expect(screen.getByText(/Details entry isn't available for this step yet\./i)).toBeInTheDocument();
      expect(screen.queryByLabelText(/Net Monthly Income/i)).not.toBeInTheDocument();
      expect(screen.queryByLabelText(/Employer.*Organization Name/i)).not.toBeInTheDocument();
      // No "Back to Upload" for a FORM action - there is no Upload tab to return to.
      expect(screen.queryByTestId('manual-unavailable-back-to-upload-btn')).not.toBeInTheDocument();
      expect(screen.getByTestId('manual-unavailable-return-btn')).toBeInTheDocument();
      expect(screen.getByTestId('manual-unavailable-cancel-btn')).toBeInTheDocument();
    });

    it('EVIDENCE action: "Why we need this?" shows the action\'s own `why`, never the hardcoded loan-repayment copy (regression)', async () => {
      // Bug: the Upload File tab's "Why we need this?" checklist was three
      // hardcoded lines ("Verify your repayment capacity", "Satisfy required
      // financial criteria", "Move to the next step") shown identically for
      // EVERY action on EVERY pack - e.g. a health-insurance medical-records
      // upload showed "repayment capacity" wording that has nothing to do
      // with insurance underwriting.
      renderScreen6('/j/22222222-2222-2222-2222-222222222222/act/UPLOAD_MEDICAL_RECORDS', {
        action: {
          action_id: 'UPLOAD_MEDICAL_RECORDS',
          title: 'Pre-existing Disease Clearance',
          kind: 'EVIDENCE',
          why: 'Past hospitalization or treatment records required for underwriting',
          unlocks: [],
          accepts: ['MEDICAL_RECORDS'],
        },
        snapshotId: '33333333-3333-3333-3333-333333333333',
      });

      await screen.findByRole('heading', { level: 1 });
      expect(
        screen.getByText('Past hospitalization or treatment records required for underwriting')
      ).toBeInTheDocument();
      expect(screen.queryByText(/repayment capacity/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/financial criteria/i)).not.toBeInTheDocument();
    });

    it('SCHEDULING-classified FORM action (SCHEDULE_*): renders a slot picker, never a blank text field, and submits the chosen slot', async () => {
      // Real financial workflows book a call rather than asking for a raw
      // string in an empty box. Insurance's real "Schedule Doctor
      // Underwriting Call" action (tele_underwriting_scheduled) exercises
      // this on the actual Insurance journey/fixture, not a synthetic one.
      const user = userEvent.setup();
      renderScreen6('/j/22222222-2222-2222-2222-222222222222/act/SCHEDULE_UNDERWRITING_CALL', {
        action: {
          action_id: 'SCHEDULE_UNDERWRITING_CALL',
          title: 'Medical Underwriting Call',
          kind: 'FORM',
          why: 'Select a time slot for the tele-medical consultation with the insurer’s doctor',
          unlocks: ['tele_underwriting_scheduled'],
        },
        snapshotId: 'ffffffff-1111-1111-1111-111111111111',
      });

      expect(await screen.findByTestId('scheduling-picker')).toBeInTheDocument();
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument();

      const confirmBtn = screen.getByTestId('scheduling-confirm-btn');
      expect(confirmBtn).toBeDisabled();

      const firstSlot = screen.getAllByRole('radio')[0];
      await user.click(firstSlot);
      expect(confirmBtn).toBeEnabled();

      await user.click(confirmBtn);
      expect(await screen.findByTestId('screen-08-stub')).toBeInTheDocument();
    });

    it('CONSENT-classified FORM action (SIGN_*/ACCEPT_*/MANDATE): renders an explicit consent checkbox, not a text field, and requires it before submitting', async () => {
      const user = userEvent.setup();
      renderScreen6('/j/44444444-4444-4444-4444-444444444444/act/SIGN_CARD_AGREEMENT', {
        action: {
          action_id: 'SIGN_CARD_AGREEMENT',
          title: 'Cardholder Agreement',
          kind: 'FORM',
          why: 'Digital agreement to card terms, fees and billing cycle required before dispatch',
          unlocks: ['card_agreement_signed'],
        },
        snapshotId: 'hhhhhhhh-1111-1111-1111-111111111111',
      });

      expect(await screen.findByTestId('consent-panel')).toBeInTheDocument();
      const confirmBtn = screen.getByTestId('consent-confirm-btn');
      expect(confirmBtn).toBeDisabled();

      await user.click(screen.getByTestId('consent-checkbox'));
      expect(confirmBtn).toBeEnabled();

      await user.click(confirmBtn);
      expect(await screen.findByTestId('screen-08-stub')).toBeInTheDocument();
    });

    it('CONSENT action WITH a declared input_schema submits the input_schema key, not unlocks[0] (regression, real-user-reported BUG-003)', async () => {
      // Real-user QA finding: ConsentPanel (and SchedulingPicker/
      // VideoVerificationFlow) used to always submit `{ [unlocks[0]]: true }`
      // as the action payload - the STATE FIELD the action satisfies (e.g.
      // Lending's real `loan_offer_accepted`), not the payload key the
      // backend's own `input_schema` requires (`accept_terms`). This exact
      // shape reproduces Lending's real ACCEPT_LOAN_TERMS action
      // (satisfies=['loan_offer_accepted'], input_schema=[{key:
      // 'accept_terms', ...}]) - the two are genuinely different keys, and
      // checking the box previously still produced a real backend 422
      // ("Required input field 'accept_terms' is missing"), confirmed via a
      // live browser session against the real backend.
      let capturedBody: unknown = null;
      server.use(
        http.post('*/api/v1/journeys/:journey_id/actions', async ({ request }) => {
          capturedBody = await request.json();
          return HttpResponse.json({
            journey: {
              journey_id: '55555555-5555-5555-5555-555555555555',
              journey_type: 'LENDING',
              status: 'IN_PROGRESS',
              readiness: 'READY',
              version_number: 2,
              fields: [],
              display: { title: 'Personal Loan', summary: '' },
              updated_at: new Date().toISOString(),
            },
            snapshot_id: '55555555-5555-5555-5555-555555555556',
            what_changed: {
              newly_satisfied: [],
              newly_unlocked: [],
              readiness_transition: null,
            },
          });
        })
      );

      const user = userEvent.setup();
      renderScreen6('/j/55555555-5555-5555-5555-555555555555/act/ACCEPT_LOAN_TERMS', {
        action: {
          action_id: 'ACCEPT_LOAN_TERMS',
          title: 'Accept Loan Agreement Terms',
          kind: 'FORM',
          why: 'Accept customized loan terms to finalize application',
          unlocks: ['loan_offer_accepted'],
          input_schema: [
            {
              key: 'accept_terms',
              type: 'boolean',
              label: 'I agree to the loan agreement and repayment terms',
              required: true,
            },
          ],
        },
        snapshotId: '55555555-5555-5555-5555-555555555555',
      });

      expect(await screen.findByTestId('consent-panel')).toBeInTheDocument();
      await user.click(screen.getByTestId('consent-checkbox'));
      await user.click(screen.getByTestId('consent-confirm-btn'));

      await screen.findByTestId('screen-08-stub');
      expect(capturedBody).toMatchObject({ input: { accept_terms: true } });
      expect((capturedBody as { input: Record<string, unknown> }).input).not.toHaveProperty(
        'loan_offer_accepted'
      );
    });

    it('VIDEO_VERIFICATION-classified FORM action (*VIDEO*/*LIVENESS*): renders the simulated video flow, never a document upload, and clearly labels it simulated', async () => {
      const user = userEvent.setup();
      renderScreen6('/j/33333333-3333-3333-3333-333333333333/act/START_VIDEO_KYC', {
        action: {
          action_id: 'START_VIDEO_KYC',
          title: 'Live Video Verification',
          kind: 'FORM',
          why: 'Complete a short agent-assisted video call or biometric liveness scan',
          unlocks: ['video_kyc'],
        },
        snapshotId: 'gggggggg-1111-1111-1111-111111111111',
      });

      expect(await screen.findByTestId('video-verification-flow')).toBeInTheDocument();
      expect(screen.queryByTestId('evidence-file-input')).not.toBeInTheDocument();
      expect(screen.getByText(/simulated in this prototype/i)).toBeInTheDocument();

      await user.click(screen.getByTestId('video-start-btn'));
      await user.click(screen.getByTestId('video-allow-btn'));

      const continueBtn = await screen.findByTestId('video-continue-btn');
      expect(continueBtn).toBeDisabled();

      // Simulated verification resolves on its own after a short delay.
      expect(await screen.findByText(/Verification complete/i, {}, { timeout: 3000 })).toBeInTheDocument();
      expect(continueBtn).toBeEnabled();

      await user.click(continueBtn);
      expect(await screen.findByTestId('screen-08-stub')).toBeInTheDocument();
    });

    it('single-accept EVIDENCE action: no doc-type selector shown, upload defaults to accepts[0] and is enabled once a file is chosen (regression, unchanged behavior)', async () => {
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

      await screen.findByRole('heading', { level: 1 });
      expect(screen.queryByTestId('doc-type-select')).not.toBeInTheDocument();

      const fileInput = screen.getByTestId('evidence-file-input');
      fireEvent.change(fileInput, {
        target: { files: [new File(['x'], 'statement.pdf', { type: 'application/pdf' })] },
      });

      expect(await screen.findByTestId('upload-submit-btn')).toBeEnabled();
    });

    it('multi-accept EVIDENCE action (regression, §14.5/Item 1 closure): frontend no longer silently declares accepts[0] - the Upload button stays disabled until the user explicitly picks a document type, and the chosen value (not a guess) is sent as doc_type', async () => {
      // This exact shape reproduces Lending's real UPLOAD_INCOME_PROOF action,
      // which accepts both SALARY_SLIP and BANK_STATEMENT (see original QA
      // report §5/§14.5). Before this fix, uploading a genuine bank statement
      // here always silently declared doc_type: "SALARY_SLIP" to the backend.
      // MSW's Request body can't reliably round-trip a FormData in this
      // jsdom test environment (request.text()/formData() both fail to
      // reconstruct it - a known environment limitation, not an app bug).
      // Spying on FormData.prototype.append instead captures the actual
      // value application code passes, independent of wire serialization.
      const appendSpy = vi.spyOn(FormData.prototype, 'append');
      server.use(
        http.post('*/api/v1/journeys/:journey_id/evidence', async () => {
          return HttpResponse.json({
            evidence_id: 'evi-multi-accept-test',
            filename: 'statement.pdf',
            uploaded_at: new Date().toISOString(),
            size_bytes: 100,
            interpretation: {
              verified: false,
              confidence: 0.5,
              detected: [],
              summary: 'test',
              conflicts: [],
            },
            proposed_action_id: 'UPLOAD_INCOME_PROOF',
            consequence_preview: null,
            diff_preview: null,
            requires_review: true,
          });
        })
      );

      const user = userEvent.setup();
      renderScreen6('/j/11111111-1111-1111-1111-111111111111/act/UPLOAD_INCOME_PROOF', {
        action: {
          action_id: 'UPLOAD_INCOME_PROOF',
          title: 'Upload Income Proof',
          kind: 'EVIDENCE',
          why: 'Verifying your monthly income unblocks loan offer calculation',
          unlocks: ['monthly_income'],
          accepts: ['SALARY_SLIP', 'BANK_STATEMENT'],
        },
        snapshotId: '33333333-3333-3333-3333-333333333333',
      });

      await screen.findByRole('heading', { level: 1 });

      // Selector is shown, offering both accepted types.
      const select = await screen.findByTestId('doc-type-select');
      expect(select).toBeInTheDocument();
      expect(screen.getByText(/Salary Slip/)).toBeInTheDocument();
      expect(screen.getByText(/Bank Statement/)).toBeInTheDocument();

      const fileInput = screen.getByTestId('evidence-file-input');
      fireEvent.change(fileInput, {
        target: { files: [new File(['x'], 'my_statement.pdf', { type: 'application/pdf' })] },
      });

      // File chosen but doc type NOT yet chosen - Upload must stay disabled
      // (never silently default to accepts[0]).
      expect(screen.getByTestId('upload-submit-btn')).toBeDisabled();

      // User explicitly picks the type that actually matches their file.
      await user.selectOptions(select, 'BANK_STATEMENT');
      expect(screen.getByTestId('upload-submit-btn')).toBeEnabled();

      await user.click(screen.getByTestId('upload-submit-btn'));

      await screen.findByTestId('screen-07-stub');
      // The explicit selection - not accepts[0] ("SALARY_SLIP") - is what was
      // actually appended to the request body.
      expect(appendSpy).toHaveBeenCalledWith('doc_type', 'BANK_STATEMENT');
      appendSpy.mockRestore();
    });

    it('multi-accept EVIDENCE action, manual-entry path: also requires an explicit doc-type choice before submit (regression)', async () => {
      // useUploadEvidence always sends multipart FormData (even for manual
      // entry, via apiClient.postForm) - see the append-spy note on the
      // upload-path test above for why this is asserted via FormData.append
      // rather than by reading the intercepted request body.
      const appendSpy = vi.spyOn(FormData.prototype, 'append');
      server.use(
        http.post('*/api/v1/journeys/:journey_id/evidence', async () => {
          return HttpResponse.json({
            evidence_id: 'evi-manual-multi-accept-test',
            filename: null,
            uploaded_at: new Date().toISOString(),
            size_bytes: 0,
            interpretation: {
              verified: false,
              confidence: 0.5,
              detected: [],
              summary: 'test',
              conflicts: [],
            },
            proposed_action_id: 'UPLOAD_INCOME_PROOF',
            consequence_preview: null,
            diff_preview: null,
            requires_review: true,
          });
        })
      );

      const user = userEvent.setup();
      renderScreen6('/j/11111111-1111-1111-1111-111111111111/act/UPLOAD_INCOME_PROOF', {
        action: {
          action_id: 'UPLOAD_INCOME_PROOF',
          title: 'Upload Income Proof',
          kind: 'EVIDENCE',
          why: 'Verifying your monthly income unblocks loan offer calculation',
          unlocks: ['monthly_income'],
          accepts: ['SALARY_SLIP', 'BANK_STATEMENT'],
          input_schema: [
            { key: 'monthly_income', type: 'number', label: 'Monthly Income', required: true },
          ],
        },
        snapshotId: '33333333-3333-3333-3333-333333333333',
      });

      await screen.findByRole('heading', { level: 1 });
      await user.click(screen.getByRole('tab', { name: /Enter Details/i }));

      const select = await screen.findByTestId('doc-type-select-manual');
      await user.selectOptions(select, 'SALARY_SLIP');
      await user.type(screen.getByLabelText(/Monthly Income/i), '50000');
      await user.click(screen.getByRole('button', { name: /Submit Details/i }));

      await screen.findByTestId('screen-07-stub');
      expect(appendSpy).toHaveBeenCalledWith('doc_type', 'SALARY_SLIP');
      appendSpy.mockRestore();
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
