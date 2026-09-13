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
});
