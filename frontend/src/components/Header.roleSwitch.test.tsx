import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import { Header } from './Header';

function renderHeader() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Header />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Header reviewer role switch errors', () => {
  afterEach(() => vi.restoreAllMocks());

  it('tells a rate-limited user to wait instead of blaming the code', async () => {
    server.use(
      http.post('*/api/v1/review/role', () =>
        HttpResponse.json(
          {
            error: {
              code: 'RATE_LIMITED',
              message: 'Too many requests. Please wait a moment and try again.',
            },
          },
          { status: 429, headers: { 'Retry-After': '42' } }
        )
      )
    );
    vi.spyOn(window, 'prompt').mockReturnValue('some-code');
    const alert = vi.spyOn(window, 'alert').mockImplementation(() => {});

    renderHeader();
    await userEvent.click(screen.getByTestId('prototype-role-switch'));

    await waitFor(() =>
      expect(alert).toHaveBeenCalledWith('Too many requests. Please wait a moment and try again.')
    );
  });

  it('keeps the wrong-code message for a rejected code', async () => {
    server.use(
      http.post('*/api/v1/review/role', () =>
        HttpResponse.json(
          { error: { code: 'FORBIDDEN', message: 'Invalid reviewer access code.' } },
          { status: 403 }
        )
      )
    );
    vi.spyOn(window, 'prompt').mockReturnValue('wrong-code');
    const alert = vi.spyOn(window, 'alert').mockImplementation(() => {});

    renderHeader();
    await userEvent.click(screen.getByTestId('prototype-role-switch'));

    await waitFor(() =>
      expect(alert).toHaveBeenCalledWith(
        'That access code was not accepted. Check it and try again.'
      )
    );
  });
});
