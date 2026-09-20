import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BootGate } from './BootGate';
import { apiClient } from '../api/client';
import { ApiError } from '../api/errors';

describe('BootGate (initial loading / cold-start resilience)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('shows a loading state immediately, then renders children once the session boot succeeds', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ session_id: 's1', created: true });

    render(
      <BootGate>
        <div data-testid="app-content">Loaded</div>
      </BootGate>
    );

    expect(screen.getByTestId('boot-gate-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('app-content')).not.toBeInTheDocument();

    expect(await screen.findByTestId('app-content')).toBeInTheDocument();
  });

  it(
    'retries a persistent 503 with backoff, shows a connection error after exhausting retries, and recovers on manual retry',
    async () => {
      vi.spyOn(apiClient, 'get').mockRejectedValue(
        new ApiError({ status: 503, message: 'Service unavailable' })
      );

      render(
        <BootGate>
          <div data-testid="app-content">Loaded</div>
        </BootGate>
      );

      const errorAlert = await screen.findByTestId('boot-gate-error', undefined, { timeout: 12000 });
      expect(errorAlert).toBeInTheDocument();
      expect(screen.queryByTestId('app-content')).not.toBeInTheDocument();
      expect((apiClient.get as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(1);

      vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ session_id: 's1', created: true });
      await userEvent.click(screen.getByTestId('boot-gate-retry-btn'));

      expect(await screen.findByTestId('app-content')).toBeInTheDocument();
    },
    15000
  );

  it('does not retry a non-retryable client error (401) and fails after a single attempt', async () => {
    const getSpy = vi
      .spyOn(apiClient, 'get')
      .mockRejectedValue(new ApiError({ status: 401, message: 'Unauthorized' }));

    render(
      <BootGate>
        <div data-testid="app-content">Loaded</div>
      </BootGate>
    );

    expect(await screen.findByTestId('boot-gate-error')).toBeInTheDocument();
    expect(getSpy).toHaveBeenCalledTimes(1);
  });
});
