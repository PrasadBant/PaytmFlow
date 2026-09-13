import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Screen04CurrentStatus } from '@/screens/Screen04CurrentStatus';

function renderWithProviders(initialRoute = '/j/11111111-1111-1111-1111-111111111111') {
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
          <Route path="/j/:id" element={<Screen04CurrentStatus />} />
          <Route path="/j/:id/next" element={<div data-testid="next-screen">Recommendation Screen</div>} />
          <Route path="/j/:id/act/:actionId" element={<div data-testid="act-screen">Action Screen</div>} />
          <Route path="/my-journeys" element={<div data-testid="my-journeys-screen">My Journeys</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Screen04CurrentStatus (F14)', () => {
  it('renders heading, progress ring, and legend breakdown', async () => {
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Your Current Status')).toBeInTheDocument();
    });

    // Verify Progress Ring
    expect(screen.getByTestId('progress-ring')).toBeInTheDocument();
    expect(screen.getByTestId('progress-ring-count')).toHaveTextContent('3/7');
    expect(screen.getByTestId('progress-ring-label')).toHaveTextContent('Completed');

    // Verify Legend
    expect(screen.getByText('3 Completed')).toBeInTheDocument();
    expect(screen.getByText('3 Pending')).toBeInTheDocument();
    expect(screen.getByText('1 Blocker')).toBeInTheDocument();
  });

  it('renders blocked items with Resolve buttons', async () => {
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText(/Blocked Items/i)).toBeInTheDocument();
    });

    expect(screen.getByText('Verified Monthly Income')).toBeInTheDocument();
    expect(screen.getByText('Salary Account Verification')).toBeInTheDocument();
    expect(screen.getByText('PAN Card Verification')).toBeInTheDocument();
    expect(screen.getByText('Current Residential Address')).toBeInTheDocument();

    const resolveButtons = screen.getAllByRole('button', { name: /Resolve/i });
    expect(resolveButtons.length).toBeGreaterThan(0);
  });

  it('navigates to action route when Resolve button is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Verified Monthly Income')).toBeInTheDocument();
    });

    const incomeResolveBtn = screen.getByRole('button', {
      name: /Resolve Verified Monthly Income/i,
    });
    await user.click(incomeResolveBtn);

    await waitFor(() => {
      expect(screen.getByTestId('act-screen')).toBeInTheDocument();
    });
  });

  it('navigates to recommendation screen when Recommended Next Step is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Your Current Status')).toBeInTheDocument();
    });

    const nextStepBtn = screen.getByRole('button', {
      name: /Recommended Next Step/i,
    });
    await user.click(nextStepBtn);

    await waitFor(() => {
      expect(screen.getByTestId('next-screen')).toBeInTheDocument();
    });
  });

  it('toggles completed requirements disclosure', async () => {
    const user = userEvent.setup();
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText(/Completed Requirements/i)).toBeInTheDocument();
    });

    const toggleButton = screen.getByRole('button', { name: /Completed Requirements/i });

    // Expand
    await user.click(toggleButton);
    expect(screen.getByText('Loan Amount')).toBeInTheDocument();
    expect(screen.getByText('Repayment Tenure')).toBeInTheDocument();
    expect(screen.getByText('Employment Classification')).toBeInTheDocument();

    // Collapse
    await user.click(toggleButton);
    expect(screen.queryByText('Repayment Tenure')).not.toBeInTheDocument();
  });

  it('strictly asserts absence of prohibited words and % character', async () => {
    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Your Current Status')).toBeInTheDocument();
    });

    const bodyText = document.body.textContent || '';
    const bodyHtml = document.body.innerHTML || '';

    // No % symbol in text/html
    expect(bodyText).not.toContain('%');
    expect(bodyHtml).not.toContain('%');

    // No prohibited words
    expect(bodyText).not.toMatch(/\bscore\b/i);
    expect(bodyText).not.toMatch(/\bapproval\b/i);
    expect(bodyText).not.toMatch(/\bprobability\b/i);
    expect(bodyText).not.toMatch(/\beligibility\b/i);
    expect(bodyText).not.toMatch(/\bguaranteed\b/i);
  });
});
