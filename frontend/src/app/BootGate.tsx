import { useCallback, useEffect, useRef, useState, type ReactElement, type ReactNode } from 'react';
import { RefreshCw, Wifi } from 'lucide-react';
import { bootApp } from './boot';
import { ApiError } from '../api/errors';
import { Button } from '../components/primitives/Button';
import { ConnectionExperience } from './connection/ConnectionExperience';
import { ConnectionSuccessTransition } from './connection/SuccessTransition';

// Render's free tier can take ~70s to wake a sleeping instance (observed
// directly against the live backend: a cold health check took 72s before
// the first byte, then responded immediately on every request after). The
// schedule below is the wait *before* each retry (attempt 1 fires
// immediately); its sum is the total time the last attempt can be delayed
// by, and is sized to comfortably clear that ~72s cold start:
//   2 + 4 + 8 + 12 + 15 + 15 + 15 = 71s
// Growth backs off quickly at first (to avoid hammering a backend that's
// still booting) then flattens to a steady 15s cadence rather than
// continuing to grow unbounded — finite (8 attempts total), not a request
// storm, not an infinite retry loop. No individual attempt has its own
// timeout (see api/client.ts) — a request is allowed to complete naturally,
// however long the cold start actually takes, rather than being cut short
// by an arbitrary client-side limit shorter than that.
const BACKOFF_SCHEDULE_MS = [2000, 4000, 8000, 12000, 15000, 15000, 15000];
const MAX_ATTEMPTS = BACKOFF_SCHEDULE_MS.length + 1;
const SLOW_HINT_MS = 3500;

/**
 * Only retry failures that are plausibly transient (network drop, gateway
 * timeout, backend cold-starting behind a proxy that 5xx's while waiting).
 * Client errors (400/401/403/etc.) mean the request itself is wrong and
 * retrying identically will never help.
 */
function isRetryableBootError(error: Error | undefined): boolean {
  if (!error) return false;
  if (error instanceof ApiError) {
    return error.status === 0 || error.status >= 500;
  }
  return true;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

type BootPhase =
  | { kind: 'booting'; slow: boolean }
  | { kind: 'success' }
  | { kind: 'ready' }
  | { kind: 'failed' };

export interface BootGateProps {
  children: ReactNode;
}

/**
 * Renders the app shell immediately and gates the real app behind the
 * session-boot sequence, so a cold/slow backend shows a loading state
 * instead of a blank screen. Retries transient failures with backoff.
 */
export function BootGate({ children }: BootGateProps): ReactElement {
  const [phase, setPhase] = useState<BootPhase>({ kind: 'booting', slow: false });
  const [retryToken, setRetryToken] = useState(0);
  const cancelledRef = useRef(false);

  const run = useCallback(async () => {
    cancelledRef.current = false;
    setPhase({ kind: 'booting', slow: false });

    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
      const slowTimer = setTimeout(() => {
        if (!cancelledRef.current) setPhase({ kind: 'booting', slow: true });
      }, SLOW_HINT_MS);

      const result = await bootApp({ skipWorkerSetup: attempt > 1 });
      clearTimeout(slowTimer);
      if (cancelledRef.current) return;

      if (!result.error) {
        setPhase({ kind: 'success' });
        return;
      }

      const isLastAttempt = attempt === MAX_ATTEMPTS;
      if (isLastAttempt || !isRetryableBootError(result.error)) {
        setPhase({ kind: 'failed' });
        return;
      }

      await sleep(BACKOFF_SCHEDULE_MS[attempt - 1]);
      if (cancelledRef.current) return;
    }
  }, []);

  useEffect(() => {
    run();
    return () => {
      cancelledRef.current = true;
    };
  }, [run, retryToken]);

  if (phase.kind === 'ready') {
    return <>{children}</>;
  }

  if (phase.kind === 'success') {
    return <ConnectionSuccessTransition onComplete={() => setPhase({ kind: 'ready' })} />;
  }

  if (phase.kind === 'failed') {
    return (
      <div
        role="alert"
        data-testid="boot-gate-error"
        className="min-h-screen flex flex-col items-center justify-center p-6 text-center animate-pf-copy-in motion-reduce:animate-none"
      >
        <div className="w-16 h-16 rounded-full bg-paytm-red-light text-paytm-red flex items-center justify-center mb-4">
          <Wifi className="w-8 h-8" aria-hidden="true" />
        </div>
        <h1 className="text-2xl font-bold text-content-primary mb-2">Something didn&apos;t connect</h1>
        <p className="text-content-secondary max-w-md mb-6 text-sm">
          Let&apos;s try that again — check your connection and retry.
        </p>
        <Button
          variant="primary"
          data-testid="boot-gate-retry-btn"
          onClick={() => setRetryToken((t) => t + 1)}
        >
          <RefreshCw className="w-4 h-4 mr-2" aria-hidden="true" />
          Try again
        </Button>
      </div>
    );
  }

  return <ConnectionExperience slow={phase.slow} />;
}

export default BootGate;
