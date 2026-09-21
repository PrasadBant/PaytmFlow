import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { BootGate } from './BootGate';
import { apiClient } from '../api/client';
import { ApiError } from '../api/errors';

// bootApp() dynamically imports the MSW browser worker to stop/start it
// around each attempt. That module's real (unmocked) dynamic import takes
// real wall-clock time to resolve/throw — time fake timers can't advance —
// which starves it out from under these retry-timing tests. It's irrelevant
// to what's under test here (BootGate's retry/backoff behavior), so it's
// stubbed out rather than exercised.
vi.mock('../mocks/browser', () => ({
  worker: { start: vi.fn().mockResolvedValue(undefined), stop: vi.fn() },
}));

// Mirrors BootGate's own schedule (see BootGate.tsx): waits before attempts
// 2..8 are 2s, 4s, 8s, 12s, 15s, 15s, 20s — sum 76s. Advancing fake timers
// by a value comfortably larger than this (e.g. 85s) lets every attempt in
// an 8-attempt sequence fire, without the test ever waiting in real time.
const FULL_SCHEDULE_MS = 85_000;

// Real wall-clock budget for tests that advance the full schedule (many
// small steps, each with real act()/microtask overhead) — comfortably
// above the observed run time, well under vitest's per-file limits.
const LONG_TEST_TIMEOUT_MS = 20_000;

// Must stay below the smallest real timer in play (SuccessTransition's
// 480ms flourish) — a single advanceTimersByTimeAsync() call can otherwise
// jump the fake clock past a timer that gets *registered* mid-jump (e.g. a
// React effect scheduling its own follow-up setTimeout while a resolved
// promise is still being flushed), scheduling it for a "due time" already
// behind the new clock position so it never fires within that call.
const ADVANCE_STEP_MS = 400;

/**
 * Advances fake timers in small steps rather than one large call. A single
 * large `advanceTimersByTimeAsync(ms)` can miss a timer that gets scheduled
 * *during* the advance itself (e.g. React committing a resolved-promise
 * state update and, in the same tick, a child effect scheduling its own
 * follow-up setTimeout) — stepping re-scans the timer queue frequently
 * enough that newly-registered timers are never missed.
 */
async function advance(ms: number): Promise<void> {
  let remaining = ms;
  while (remaining > 0) {
    const step = Math.min(ADVANCE_STEP_MS, remaining);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(step);
    });
    remaining -= step;
  }
}

// Generous fixed buffer for the success flourish (SUCCESS_HOLD_MS = 480ms)
// after a boot request resolves — covers both the flourish itself and the
// handful of real microtask hops (module resolution, mocked promises) that
// precede it, which can push the flourish's own timer registration later
// than a bare 480ms + tiny margin would assume.
const SUCCESS_FLOURISH_BUFFER_MS = 3_000;

function renderBootGate(): void {
  render(
    <BootGate>
      <div data-testid="app-content">Loaded</div>
    </BootGate>
  );
}

describe('BootGate (initial loading / cold-start resilience)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('1. boots immediately when the session request succeeds on the first attempt', async () => {
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ session_id: 's1', created: true });

    renderBootGate();
    expect(screen.getByTestId('boot-gate-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('app-content')).not.toBeInTheDocument();

    await advance(SUCCESS_FLOURISH_BUFFER_MS);
    expect(screen.getByTestId('app-content')).toBeInTheDocument();
    expect(getSpy).toHaveBeenCalledTimes(1);
  });

  it(
    '2. recovers after a single transient failure',
    async () => {
      const getSpy = vi
        .spyOn(apiClient, 'get')
        .mockRejectedValueOnce(new ApiError({ status: 503, message: 'Service unavailable' }))
        .mockResolvedValueOnce({ session_id: 's1', created: true });

      renderBootGate();
      await advance(FULL_SCHEDULE_MS);

      expect(screen.getByTestId('app-content')).toBeInTheDocument();
      expect(getSpy).toHaveBeenCalledTimes(2);
    },
    LONG_TEST_TIMEOUT_MS
  );

  it(
    '3. recovers after multiple transient failures',
    async () => {
      const getSpy = vi
        .spyOn(apiClient, 'get')
        .mockRejectedValueOnce(new ApiError({ status: 502, message: 'Bad gateway' }))
        .mockRejectedValueOnce(new ApiError({ status: 503, message: 'Service unavailable' }))
        .mockRejectedValueOnce(new ApiError({ status: 504, message: 'Gateway timeout' }))
        .mockRejectedValueOnce(new ApiError({ status: 0, message: 'Network request failed' }))
        .mockRejectedValueOnce(new ApiError({ status: 503, message: 'Service unavailable' }))
        .mockResolvedValueOnce({ session_id: 's1', created: true });

      renderBootGate();
      await advance(FULL_SCHEDULE_MS);

      expect(screen.getByTestId('app-content')).toBeInTheDocument();
      expect(getSpy).toHaveBeenCalledTimes(6);
    },
    LONG_TEST_TIMEOUT_MS
  );

  it(
    '4. recovers from a cold-start-like delay spanning almost the entire retry budget',
    async () => {
      const getSpy = vi.spyOn(apiClient, 'get').mockRejectedValue(new ApiError({ status: 503, message: 'Service unavailable' }));

      renderBootGate();

      // Let attempts 1-7 fail (each via the persistent mockRejectedValue),
      // then swap in a success right before the final attempt is due.
      await advance(70_000);
      getSpy.mockResolvedValueOnce({ session_id: 's1', created: true });
      await advance(10_000);

      expect(screen.getByTestId('app-content')).toBeInTheDocument();
      expect(getSpy).toHaveBeenCalledTimes(8);
    },
    LONG_TEST_TIMEOUT_MS
  );

  it.each([
    ['502', new ApiError({ status: 502, message: 'Bad gateway' })],
    ['503', new ApiError({ status: 503, message: 'Service unavailable' })],
    ['504', new ApiError({ status: 504, message: 'Gateway timeout' })],
    ['network failure (status 0)', new ApiError({ status: 0, message: 'Network request failed' })],
  ])(
    '5-8. retries a transient %s failure and recovers',
    async (_label, error) => {
      const getSpy = vi.spyOn(apiClient, 'get').mockRejectedValueOnce(error).mockResolvedValueOnce({ session_id: 's1', created: true });

      renderBootGate();
      await advance(FULL_SCHEDULE_MS);

      expect(screen.getByTestId('app-content')).toBeInTheDocument();
      expect(getSpy).toHaveBeenCalledTimes(2);
    },
    LONG_TEST_TIMEOUT_MS
  );

  it(
    '9. does not retry a non-retryable client error (401) and fails after a single attempt',
    async () => {
      const getSpy = vi.spyOn(apiClient, 'get').mockRejectedValue(new ApiError({ status: 401, message: 'Unauthorized' }));

      renderBootGate();
      await advance(FULL_SCHEDULE_MS);

      expect(screen.getByTestId('boot-gate-error')).toBeInTheDocument();
      expect(getSpy).toHaveBeenCalledTimes(1);
    },
    LONG_TEST_TIMEOUT_MS
  );

  it(
    '10. does not retry a non-retryable client error (403) and fails after a single attempt',
    async () => {
      const getSpy = vi.spyOn(apiClient, 'get').mockRejectedValue(new ApiError({ status: 403, message: 'Forbidden' }));

      renderBootGate();
      await advance(FULL_SCHEDULE_MS);

      expect(screen.getByTestId('boot-gate-error')).toBeInTheDocument();
      expect(getSpy).toHaveBeenCalledTimes(1);
    },
    LONG_TEST_TIMEOUT_MS
  );

  it(
    '11. shows the final error UI once the bounded retry budget is exhausted, with a finite number of attempts',
    async () => {
      const getSpy = vi.spyOn(apiClient, 'get').mockRejectedValue(new ApiError({ status: 503, message: 'Service unavailable' }));

      renderBootGate();
      await advance(FULL_SCHEDULE_MS);

      expect(screen.getByTestId('boot-gate-error')).toBeInTheDocument();
      // Exactly MAX_ATTEMPTS (8) — proves the retry budget is bounded, not an
      // infinite loop or an uncontrolled request storm.
      expect(getSpy).toHaveBeenCalledTimes(8);

      // Advancing further must not trigger any additional requests.
      await advance(FULL_SCHEDULE_MS);
      expect(getSpy).toHaveBeenCalledTimes(8);
    },
    LONG_TEST_TIMEOUT_MS * 2
  );

  it(
    '12. "Try again" resets the retry cycle and can recover',
    async () => {
      const getSpy = vi.spyOn(apiClient, 'get').mockRejectedValue(new ApiError({ status: 503, message: 'Service unavailable' }));

      renderBootGate();
      await advance(FULL_SCHEDULE_MS);
      expect(screen.getByTestId('boot-gate-error')).toBeInTheDocument();

      getSpy.mockReset();
      getSpy.mockResolvedValueOnce({ session_id: 's1', created: true });

      await act(async () => {
        fireEvent.click(screen.getByTestId('boot-gate-retry-btn'));
      });
      await advance(SUCCESS_FLOURISH_BUFFER_MS);

      expect(screen.getByTestId('app-content')).toBeInTheDocument();
      expect(getSpy).toHaveBeenCalledTimes(1);
    },
    LONG_TEST_TIMEOUT_MS
  );

  it(
    '13. successful recovery renders the real application (the children passed to BootGate), not a stand-in',
    async () => {
      vi.spyOn(apiClient, 'get')
        .mockRejectedValueOnce(new ApiError({ status: 503, message: 'Service unavailable' }))
        .mockRejectedValueOnce(new ApiError({ status: 503, message: 'Service unavailable' }))
        .mockResolvedValueOnce({ session_id: 's1', created: true });

      renderBootGate();
      await advance(FULL_SCHEDULE_MS);

      const content = screen.getByTestId('app-content');
      expect(content).toBeInTheDocument();
      expect(content).toHaveTextContent('Loaded');
    },
    LONG_TEST_TIMEOUT_MS
  );

  it(
    '14. never fabricates a success/session while retries are exhausted',
    async () => {
      vi.spyOn(apiClient, 'get').mockRejectedValue(new ApiError({ status: 503, message: 'Service unavailable' }));

      renderBootGate();
      await advance(FULL_SCHEDULE_MS);

      expect(screen.getByTestId('boot-gate-error')).toBeInTheDocument();
      expect(screen.queryByTestId('app-content')).not.toBeInTheDocument();
      expect(screen.queryByTestId('boot-gate-success')).not.toBeInTheDocument();
    },
    LONG_TEST_TIMEOUT_MS
  );

  it(
    '15. backend ready mid-story: the current chapter finishes (no abrupt cut), then Home — without waiting for the rest of the story',
    async () => {
      let resolveSession!: (value: { session_id: string; created: boolean }) => void;
      const pending = new Promise<{ session_id: string; created: boolean }>((resolve) => {
        resolveSession = resolve;
      });
      vi.spyOn(apiClient, 'get').mockReturnValueOnce(pending);

      renderBootGate();
      expect(screen.getByTestId('boot-gate-loading')).toBeInTheDocument();

      // 9s in: inside the "assemble" chapter's own entrance choreography
      // (assemble starts at 8s), not at a chapter boundary.
      await advance(9_000);
      expect(screen.getByTestId('boot-gate-loading')).toBeInTheDocument();

      resolveSession({ session_id: 's1', created: true });
      await advance(200); // let the resolution flush into React state

      // Not an abrupt jump — the current chapter's transition is still
      // finishing, so the story is still on screen a moment later.
      expect(screen.queryByTestId('app-content')).not.toBeInTheDocument();
      expect(screen.getByTestId('boot-gate-loading')).toBeInTheDocument();

      // But it must resolve to Home well before the remaining ~100+ seconds
      // of story would ever have played out — proving later chapters are
      // skipped, not merely deferred.
      await advance(3_500);
      expect(screen.getByTestId('app-content')).toBeInTheDocument();
    },
    LONG_TEST_TIMEOUT_MS
  );

  it(
    '16. backend ready exactly at a chapter boundary: one clean Home navigation',
    async () => {
      let resolveSession!: (value: { session_id: string; created: boolean }) => void;
      const pending = new Promise<{ session_id: string; created: boolean }>((resolve) => {
        resolveSession = resolve;
      });
      vi.spyOn(apiClient, 'get').mockReturnValueOnce(pending);

      renderBootGate();

      await advance(22_000); // exactly the "documents" chapter's start boundary
      resolveSession({ session_id: 's1', created: true });

      // Up to MAX_EXIT_WAIT_MS (2.5s) for the chapter boundary, plus the
      // success flourish and its own microtask overhead.
      await advance(6_000);
      expect(screen.getByTestId('app-content')).toBeInTheDocument();
      // A clean single transition — no duplicate success/error states left behind.
      expect(screen.queryByTestId('boot-gate-error')).not.toBeInTheDocument();
    },
    LONG_TEST_TIMEOUT_MS
  );

  it('17. a stale request that resolves after the component has unmounted never touches state (no error, no warning)', async () => {
    let resolveSession!: (value: { session_id: string; created: boolean }) => void;
    const pending = new Promise<{ session_id: string; created: boolean }>((resolve) => {
      resolveSession = resolve;
    });
    vi.spyOn(apiClient, 'get').mockReturnValueOnce(pending);

    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { unmount } = render(
      <BootGate>
        <div data-testid="app-content">Loaded</div>
      </BootGate>
    );

    unmount();
    // The in-flight request settles only *after* unmount — this must not
    // throw, warn about updating an unmounted component, or do anything
    // observable; the generation this belongs to is invalidated by then.
    await act(async () => {
      resolveSession({ session_id: 's1', created: true });
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it(
    '19. a response arriving near/just beyond the historical ~72s cold-start observation is still handled by the retry policy, not a premature failure',
    async () => {
      const getSpy = vi.spyOn(apiClient, 'get').mockRejectedValue(new ApiError({ status: 503, message: 'Service unavailable' }));

      renderBootGate();

      // 73s in — just past the single real ~72s cold-start observation this
      // schedule is sized against. The final (8th) attempt isn't due until
      // 76s (see BACKOFF_SCHEDULE_MS's cumulative sum in BootGate.tsx), so
      // at this point the retry policy must still be actively waiting, not
      // have already exhausted itself into the error screen.
      await advance(73_000);
      expect(screen.getByTestId('boot-gate-loading')).toBeInTheDocument();
      expect(screen.queryByTestId('boot-gate-error')).not.toBeInTheDocument();

      // The backend becomes ready right as that still-pending final attempt
      // fires — proving a cold start finishing around this mark succeeds
      // through the normal policy instead of being treated as exhausted.
      getSpy.mockResolvedValueOnce({ session_id: 's1', created: true });
      await advance(SUCCESS_FLOURISH_BUFFER_MS + 5_000);

      expect(screen.getByTestId('app-content')).toBeInTheDocument();
      expect(screen.queryByTestId('boot-gate-error')).not.toBeInTheDocument();
    },
    LONG_TEST_TIMEOUT_MS
  );

  it(
    '18. rapid double-click on "Try again" starts exactly one clean boot cycle, not duplicate/overlapping requests',
    async () => {
      const getSpy = vi.spyOn(apiClient, 'get').mockRejectedValue(new ApiError({ status: 503, message: 'Service unavailable' }));

      renderBootGate();
      await advance(FULL_SCHEDULE_MS);
      expect(screen.getByTestId('boot-gate-error')).toBeInTheDocument();
      expect(getSpy).toHaveBeenCalledTimes(8);

      getSpy.mockReset();
      getSpy.mockResolvedValueOnce({ session_id: 's1', created: true });

      // Two rapid clicks in the same synchronous block — React batches
      // both retryToken updates into a single re-render, so this must still
      // result in exactly one boot cycle (one request), not two.
      await act(async () => {
        const btn = screen.getByTestId('boot-gate-retry-btn');
        fireEvent.click(btn);
        fireEvent.click(btn);
      });
      await advance(SUCCESS_FLOURISH_BUFFER_MS);

      expect(screen.getByTestId('app-content')).toBeInTheDocument();
      expect(getSpy).toHaveBeenCalledTimes(1);
    },
    LONG_TEST_TIMEOUT_MS
  );
});
