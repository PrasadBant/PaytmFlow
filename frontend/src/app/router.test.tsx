import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { routes } from './routes';
import { AppProviders } from './providers';

function renderWithRouter(initialEntry: string) {
  const testRouter = createMemoryRouter(routes, {
    initialEntries: [initialEntry],
  });

  return render(
    <AppProviders>
      <RouterProvider router={testRouter} />
    </AppProviders>
  );
}

describe('Router & Route Map Suite (F07)', () => {
  it('renders Screen 1 Home by default at /', () => {
    renderWithRouter('/');
    expect(screen.getByTestId('screen-01-home')).toBeInTheDocument();
    expect(screen.getByText(/Your Financial Journey/i)).toBeInTheDocument();
  });

  it('renders Screen 2 Journey Selection on "/start"', async () => {
    renderWithRouter('/start');
    await waitFor(() => {
      expect(screen.getByTestId('screen-02-journey-selection')).toBeInTheDocument();
      expect(screen.getByText('Choose Your Financial Journey')).toBeInTheDocument();
    });
  });

  it('renders Screen 3 Goal & Basic Info with route param on "/start/:type"', async () => {
    renderWithRouter('/start/LENDING');
    await waitFor(() => {
      expect(screen.getByTestId('screen-03-goal-basic-info')).toBeInTheDocument();
      expect(screen.getByText('Personal Loan')).toBeInTheDocument();
    });
  });

  it('renders Screen 4 Current Status with route param on "/j/:id"', async () => {
    renderWithRouter('/j/journey-123');
    await waitFor(() => {
      expect(screen.getByTestId('screen-04-current-status')).toBeInTheDocument();
      expect(screen.getByText('Your Current Status')).toBeInTheDocument();
    });
  });

  it('renders Screen 5 Recommendation with route param on "/j/:id/next"', async () => {
    renderWithRouter('/j/journey-123/next');
    await waitFor(() => {
      expect(screen.getByTestId('screen-05-recommendation')).toBeInTheDocument();
      expect(screen.getByText('Recommended Next Step')).toBeInTheDocument();
    });
  });

  it('renders Screen 6 Upload Evidence with route params on "/j/:id/act/:actionId"', async () => {
    renderWithRouter('/j/journey-123/act/action-456');
    await waitFor(() => {
      expect(screen.getByTestId('screen-06-upload-evidence')).toBeInTheDocument();
    });
  });

  it('renders Screen 7 AI Analysis with route param on "/j/:id/analysis"', async () => {
    renderWithRouter('/j/journey-123/analysis');
    await waitFor(() => {
      expect(screen.getByTestId('screen-07-ai-analysis')).toBeInTheDocument();
    });
  });

  it('renders Screen 8 Updated Status with route param on "/j/:id/updated"', async () => {
    renderWithRouter('/j/journey-123/updated');
    await waitFor(() => {
      expect(screen.getByTestId('screen-08-updated-status')).toBeInTheDocument();
    });
  });

  it('renders Screen 9 Complete with route param on "/j/:id/complete"', async () => {
    renderWithRouter('/j/journey-123/complete');
    await waitFor(() => {
      expect(screen.getByTestId('screen-09-complete-journey')).toBeInTheDocument();
    });
  });

  it('renders Screen 10 My Journeys with query param support on "/my-journeys"', () => {
    renderWithRouter('/my-journeys?tab=IN_PROGRESS');
    expect(screen.getByTestId('screen-10-my-journeys')).toBeInTheDocument();
    expect(screen.getByTestId('active-tab')).toHaveTextContent('IN_PROGRESS');
  });

  it('renders KitchenSink showcase on "/dev/kitchen-sink"', () => {
    renderWithRouter('/dev/kitchen-sink');
    expect(screen.getByText(/Primitives Kitchen Sink/i)).toBeInTheDocument();
  });

  it('renders 404 NotFoundScreen on unknown routes', () => {
    renderWithRouter('/non-existent-route/xyz');
    expect(screen.getByTestId('screen-404')).toBeInTheDocument();
    expect(screen.getByText('Page Not Found')).toBeInTheDocument();
  });
});
