import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import { Screen03GoalBasicInfo } from '@/screens/Screen03GoalBasicInfo';

function renderWithProviders(initialRoute = '/start/lending') {
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
          <Route path="/start" element={<div>Start Selection Screen</div>} />
          <Route path="/start/:type" element={<Screen03GoalBasicInfo />} />
          <Route path="/j/:id" element={<div data-testid="status-screen">Journey Status Screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Screen03GoalBasicInfo', () => {
  beforeEach(() => {
    // Reset any storage or session mocks if needed
  });

  it('renders correctly for LENDING pack with schema fields', async () => {
    renderWithProviders('/start/lending');

    await waitFor(() => {
      expect(screen.getByText('Loan / Lending')).toBeInTheDocument();
      expect(screen.getByText('Set Your Loan Goal')).toBeInTheDocument();
    });

    expect(
      screen.getByText('Provide your loan requirement to begin.')
    ).toBeInTheDocument();

    // Verify LENDING specific fields rendered by SchemaForm - matches the real
    // backend's actual goal_schema (loan_amount, loan_purpose, tenure_months only;
    // employment/income/PAN are state-schema fields collected later via actions,
    // not part of the initial goal).
    expect(screen.getByLabelText(/Loan Amount/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Purpose of Loan/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Tenure \(Months\)/i)).toBeInTheDocument();
  });

  it('renders correctly for INSURANCE pack with schema fields', async () => {
    renderWithProviders('/start/insurance');

    await waitFor(() => {
      expect(screen.getByText('Insurance')).toBeInTheDocument();
      expect(screen.getByText('Insurance Coverage Goal')).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/Desired Coverage/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Policy Type/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Tobacco or Nicotine Consumer/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Residential PIN Code/i)).toBeInTheDocument();
  });

  it('renders correctly for KYC pack', async () => {
    renderWithProviders('/start/kyc');

    await waitFor(() => {
      expect(screen.getByText('KYC / Onboarding')).toBeInTheDocument();
      expect(screen.getByText('Identity Verification Details')).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/Aadhaar Number/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Verification Purpose/i)).toBeInTheDocument();
  });

  it('renders correctly for CREDIT_CARD pack', async () => {
    renderWithProviders('/start/credit_card');

    await waitFor(() => {
      expect(screen.getByText('Credit Card')).toBeInTheDocument();
      expect(screen.getByText('Credit Card Preferences')).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/Estimated Monthly Spend/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Reward Preference/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Gross Annual Income/i)).toBeInTheDocument();
  });

  it('renders correctly for ACCOUNT_OPENING pack', async () => {
    renderWithProviders('/start/account_opening');

    await waitFor(() => {
      expect(screen.getByText('Account Opening')).toBeInTheDocument();
      expect(screen.getByText('Savings Account Options')).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/Account Type/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Add Nominee Now/i)).toBeInTheDocument();
  });

  it('renders correctly for INVESTMENT pack', async () => {
    renderWithProviders('/start/investment');

    await waitFor(() => {
      expect(screen.getByText('Investment / Wealth')).toBeInTheDocument();
      expect(screen.getByText('Investment Portfolio Goal')).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/Primary Objective/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Target Monthly SIP/i)).toBeInTheDocument();
  });

  it('toggles natural language progressive disclosure', async () => {
    const user = userEvent.setup();
    renderWithProviders('/start/lending');

    await waitFor(() => {
      expect(screen.getByText(/Describe in your own words/i)).toBeInTheDocument();
    });

    const toggleButton = screen.getByRole('button', { name: /Describe in your own words/i });
    expect(screen.queryByPlaceholderText(/Need a 5 lakh loan/i)).not.toBeInTheDocument();

    // Expand
    await user.click(toggleButton);
    expect(screen.getByPlaceholderText(/Need a 5 lakh loan/i)).toBeInTheDocument();

    // Type in description
    await user.type(
      screen.getByPlaceholderText(/Need a 5 lakh loan/i),
      'Looking for 500000 for medical expense'
    );

    // Collapse
    await user.click(toggleButton);
    expect(screen.queryByPlaceholderText(/Need a 5 lakh loan/i)).not.toBeInTheDocument();
  });

  it('submits form and navigates to the newly created journey status screen', async () => {
    const user = userEvent.setup();
    renderWithProviders('/start/kyc');

    await waitFor(() => {
      expect(screen.getByLabelText(/Aadhaar Number/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/Email for updates/i), 'customer@example.com');
    await user.type(screen.getByLabelText(/Aadhaar Number/i), '1234 5678 9012');
    await user.selectOptions(screen.getByLabelText(/Verification Purpose/i), 'Wallet Upgrade');

    await user.click(screen.getByRole('button', { name: /Continue →/i }));

    await waitFor(() => {
      expect(screen.getByTestId('status-screen')).toBeInTheDocument();
    });
  });

  it('renders the real pack display_name and description as static context without editable selector', async () => {
    renderWithProviders('/start/lending');
    await waitFor(() => {
      expect(screen.getByTestId('selected-journey-context')).toBeInTheDocument();
    });
    expect(screen.getByText('Loan / Lending')).toBeInTheDocument();
    expect(screen.queryByLabelText(/I want to/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId('goal-selector')).not.toBeInTheDocument();
  });

  it('renders insurance pack static context correctly', async () => {
    renderWithProviders('/start/insurance');
    await waitFor(() => {
      expect(screen.getByTestId('selected-journey-context')).toBeInTheDocument();
    });
    expect(screen.getByText('Insurance')).toBeInTheDocument();
    expect(screen.queryByLabelText(/I want to/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId('goal-selector')).not.toBeInTheDocument();
  });

  it('rejects an invalid email and does not submit the journey', async () => {
    const user = userEvent.setup();
    let requestReceived = false;
    server.use(
      http.post('*/api/v1/journeys', async () => {
        requestReceived = true;
        return HttpResponse.json({}, { status: 201 });
      })
    );

    renderWithProviders('/start/kyc');

    await waitFor(() => {
      expect(screen.getByLabelText(/Aadhaar Number/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/Email for updates/i), 'not-an-email');
    await user.type(screen.getByLabelText(/Aadhaar Number/i), '1234 5678 9012');
    await user.selectOptions(screen.getByLabelText(/Verification Purpose/i), 'Wallet Upgrade');
    await user.click(screen.getByRole('button', { name: /Continue →/i }));

    expect(await screen.findByText(/Enter a valid email address/i)).toBeInTheDocument();
    expect(requestReceived).toBe(false);
  });

  it('sends the required customer_email with the create-journey request', async () => {
    const user = userEvent.setup();
    let capturedBody: Record<string, unknown> | undefined;
    server.use(
      http.post('*/api/v1/journeys', async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { journey_id: 'test-journey-id', journey_type: 'KYC' },
          { status: 201 }
        );
      })
    );

    renderWithProviders('/start/kyc');

    await waitFor(() => {
      expect(screen.getByLabelText(/Aadhaar Number/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/Email for updates/i), 'customer@example.com');
    await user.type(screen.getByLabelText(/Aadhaar Number/i), '1234 5678 9012');
    await user.selectOptions(screen.getByLabelText(/Verification Purpose/i), 'Wallet Upgrade');
    await user.click(screen.getByRole('button', { name: /Continue →/i }));

    await waitFor(() => {
      expect(capturedBody?.customer_email).toBe('customer@example.com');
    });
  });

  it('requires an email and blocks submission when left blank', async () => {
    const user = userEvent.setup();
    let requestReceived = false;
    server.use(
      http.post('*/api/v1/journeys', async () => {
        requestReceived = true;
        return HttpResponse.json({}, { status: 201 });
      })
    );

    renderWithProviders('/start/kyc');

    await waitFor(() => {
      expect(screen.getByLabelText(/Aadhaar Number/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/Aadhaar Number/i), '1234 5678 9012');
    await user.selectOptions(screen.getByLabelText(/Verification Purpose/i), 'Wallet Upgrade');
    await user.click(screen.getByRole('button', { name: /Continue →/i }));

    expect(await screen.findByText(/Email is required/i)).toBeInTheDocument();
    expect(requestReceived).toBe(false);
  });

  it('contains no prohibited words or claims', async () => {
    renderWithProviders('/start/lending');

    await waitFor(() => {
      expect(screen.getByText('Loan / Lending')).toBeInTheDocument();
    });

    const bodyText = document.body.textContent || '';
    expect(bodyText).not.toMatch(/\bscore\b/i);
    expect(bodyText).not.toMatch(/\bapproval\b/i);
    expect(bodyText).not.toMatch(/\bprobability\b/i);
    expect(bodyText).not.toMatch(/\beligibility\b/i);
    expect(bodyText).not.toMatch(/\bguaranteed\b/i);
  });
});
