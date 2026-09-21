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
// immediately); cumulative sum through entry N is how long attempt N+2 is
// delayed by. The original schedule summed to 71s before the final (8th)
// attempt — only 1s short of the single 72s cold-start observation, i.e.
// essentially no margin for ordinary run-to-run variance in how long a cold
// start actually takes. The final entry is widened by 5s (15s -> 20s) so
// the last attempt begins at 76s instead of 71s, giving a small buffer past
// that observation without touching any earlier retry timing:
//   2 + 4 + 8 + 12 + 15 + 15 + 20 = 76s
// Growth backs off quickly at first (to avoid hammering a backend that's
// still booting) then flattens to a steady cadence rather than continuing
// to grow unbounded — finite (8 attempts total), not a request storm, not
// an infinite retry loop. No individual attempt has its own timeout (see
// api/client.ts) — a request is allowed to complete naturally, however long
// the cold start actually takes, rather than being cut short by an
// arbitrary client-side limit shorter than that.
const BACKOFF_SCHEDULE_MS = [2000, 4000, 8000, 12000, 15000, 15000, 20000];
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
  | { kind: 'booting'; slow: boolean; backendReady: boolean }
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
  const [phase, setPhase] = useState<BootPhase>({ kind: 'booting', slow: false, backendReady: false });
  const [retryToken, setRetryToken] = useState(0);
  // A strictly-increasing boot-cycle id, not a boolean. A boolean
  // "cancelled" flag is shared mutable state: a NEW run() unconditionally
  // resets it to false at its start, which would silently "resurrect" an
  // OLDER, still-pending run's ability to act — if that older run's
  // `await bootApp()`/`await sleep()` settles afterwards, its stale result
  // could still overwrite a state a newer (or already-successful) cycle has
  // since reached. A generation id can't be reset out from under a stale
  // check like that: once a newer generation exists, `generationRef.current
  // !== myGeneration` for a stale run stays true forever, so it is
  // permanently barred from updating phase again, however it settles.
  const generationRef = useRef(0);

  const run = useCallback(async (myGeneration: number) => {
    setPhase({ kind: 'booting', slow: false, backendReady: false });

    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
      const slowTimer = setTimeout(() => {
        if (generationRef.current === myGeneration) {
          setPhase((prev) => (prev.kind === 'booting' ? { ...prev, slow: true } : prev));
        }
      }, SLOW_HINT_MS);

      const result = await bootApp({ skipWorkerSetup: attempt > 1 });
      clearTimeout(slowTimer);
      if (generationRef.current !== myGeneration) return; // superseded by a newer boot cycle — ignore

      if (!result.error) {
        // Don't cut straight to the success transition — the story keeps
        // playing until its current chapter reaches a natural stopping
        // point (see ConnectionExperience's onReadyToExit), so a viewer
        // mid-animation never sees an abrupt jump. `backendReady` is the
        // real signal; `success` is only entered once that boundary fires.
        // Once this fires, this generation is done — no later check in this
        // same generation can run again (the loop returns immediately
        // after), so a successful boot cycle can never be overwritten by
        // its own later work, only by an explicitly newer generation.
        setPhase((prev) => (prev.kind === 'booting' ? { ...prev, backendReady: true } : prev));
        return;
      }

      const isLastAttempt = attempt === MAX_ATTEMPTS;
      if (isLastAttempt || !isRetryableBootError(result.error)) {
        setPhase({ kind: 'failed' });
        return;
      }

      await sleep(BACKOFF_SCHEDULE_MS[attempt - 1]);
      if (generationRef.current !== myGeneration) return; // superseded while backing off — ignore
    }
  }, []);

  useEffect(() => {
    const myGeneration = generationRef.current + 1;
    generationRef.current = myGeneration;
    run(myGeneration);
    return () => {
      // Invalidate this generation on cleanup (a manual retry starting a
      // new one, or the component unmounting) so any work still in flight
      // from it can never act again — see generationRef's comment above.
      if (generationRef.current === myGeneration) {
        generationRef.current += 1;
      }
    };
  }, [run, retryToken]);

  const handleReadyToExit = useCallback(() => {
    setPhase({ kind: 'success' });
  }, []);

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

  return <ConnectionExperience slow={phase.slow} backendReady={phase.backendReady} onReadyToExit={handleReadyToExit} />;
}

export default BootGate;
