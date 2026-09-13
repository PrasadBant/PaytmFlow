import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, afterEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Screen05Recommendation } from '@/screens/Screen05Recommendation';
import { setOverrideScenario } from '@/mocks/scenarios';

function renderWithProviders(initialRoute = '/j/11111111-1111-1111-1111-111111111111/next') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <Routes>
          <Route path="/j/:id" element={<div data-testid="status-screen">Status Screen</div>} />
          <Route path="/j/:id/next" element={<Screen05Recommendation />} />
          <Route path="/j/:id/act/:actionId" element={<div data-testid="act-screen">Action Screen</div>} />
          <Route path="/j/:id/complete" element={<div data-testid="complete-screen">Complete Screen</div>} />
          <Route path="/start" element={<div data-testid="start-screen">Start Screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Screen05Recommendation (F16)', () => {
  afterEach(() => {
    setOverrideScenario(null);
  });

  it('renders recommended next step card, alternatives list, and assistant help card', async () => {
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Recommended Next Step')).toBeInTheDocument();
    });

    // Recommendation card
    expect(screen.getByText('Upload Salary Slip')).toBeInTheDocument();
    expect(screen.getByText('Recommended Next Action')).toBeInTheDocument();

    // Alternatives list
    expect(screen.getByText(/Alternative Options/i)).toBeInTheDocument();
    expect(screen.getByText('Adjust Loan Tenure')).toBeInTheDocument();
    expect(screen.getByText('Update Employer Details')).toBeInTheDocument();

    // Assistant Card
    expect(screen.getByText('Need Help with this Step?')).toBeInTheDocument();
  });

  it('navigates to action route when primary action CTA is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Upload Salary Slip')).toBeInTheDocument();
    });

    const ctaBtn = screen.getByRole('button', {
      name: /Take action: Upload Salary Slip/i,
    });
    await user.click(ctaBtn);

    await waitFor(() => {
      expect(screen.getByTestId('act-screen')).toBeInTheDocument();
    });
  });

  it('navigates to action route when an alternative is selected', async () => {
    const user = userEvent.setup();
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Adjust Loan Tenure')).toBeInTheDocument();
    });

    const selectBtn = screen.getByRole('button', {
      name: /Select alternative action: Adjust Loan Tenure/i,
    });
    await user.click(selectBtn);

    await waitFor(() => {
      expect(screen.getByTestId('act-screen')).toBeInTheDocument();
    });
  });

  it('renders DeadEndState when scenario forces deadend', async () => {
    setOverrideScenario('deadend');
    renderWithProviders('/j/11111111-1111-1111-1111-111111111111/next');

    await waitFor(() => {
      expect(screen.getByTestId('dead-end-state')).toBeInTheDocument();
      expect(screen.getByText('No Automated Action Available')).toBeInTheDocument();
    });
  });

  it('strictly contains no prohibited words or claims', async () => {
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Recommended Next Step')).toBeInTheDocument();
    });

    const bodyText = document.body.textContent || '';
    const bodyHtml = document.body.innerHTML || '';

    expect(bodyText).not.toContain('%');
    expect(bodyHtml).not.toContain('%');
    expect(bodyText).not.toMatch(/\bscore\b/i);
    expect(bodyText).not.toMatch(/\bapproval\b/i);
    expect(bodyText).not.toMatch(/\bprobability\b/i);
    expect(bodyText).not.toMatch(/\beligibility\b/i);
    expect(bodyText).not.toMatch(/\bguaranteed\b/i);
  });
});
