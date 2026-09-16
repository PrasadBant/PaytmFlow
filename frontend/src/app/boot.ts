import { apiClient } from '../api/client';

export interface SessionData {
  session_id: string;
  created: boolean;
}

export interface BootResult {
  session: SessionData | null;
  mode: 'mock' | 'live';
  initialized: boolean;
  error?: Error;
}

/**
 * Executes the boot sequence:
 * 1. Initializes MSW in browser if in mock mode.
 * 2. Calls GET /session to establish anonymous session cookie before first paint.
 */
export async function bootApp(): Promise<BootResult> {
  const mode = import.meta.env.VITE_API_MODE === 'live' ? 'live' : 'mock';

  // Start MSW worker in browser runtime when mocking is active
  if (typeof window !== 'undefined' && mode === 'mock') {
    try {
      const { worker } = await import('../mocks/browser');
      await worker.start({
        onUnhandledRequest: 'bypass',
        quiet: true,
      });
    } catch {
      // Mock worker setup bypassed or running in headless / test environment
    }
  } else if (typeof window !== 'undefined' && mode === 'live') {
    // Real-user QA finding: MSW's service worker, once registered by the
    // browser for this origin during an earlier mock-mode visit, persists
    // across page reloads AND dev-server restarts independently of the
    // current page's JS bundle - it intercepts /api/v1/* at the browser
    // network layer before this file's own mode check ever runs. A
    // browser that previously loaded this app in mock mode would keep
    // silently serving MSW's canned fixture responses even on a later
    // visit that is genuinely configured for live mode, making "live
    // mode" not actually live from that real browser's perspective.
    // Explicitly stopping/unregistering it here guarantees mode=live
    // actually reaches the real backend. Safe no-op if no worker was
    // ever registered in this browser.
    try {
      const { worker } = await import('../mocks/browser');
      await worker.stop();
    } catch {
      // No previously-registered service worker to stop, or running in an
      // environment (headless/test) where one was never started.
    }
  }

  try {
    const session = await apiClient.get<SessionData>('/session');
    return {
      session,
      mode,
      initialized: true,
    };
  } catch (err) {
    const error = err instanceof Error ? err : new Error('Failed to initialize session');
    return {
      session: null,
      mode,
      initialized: true,
      error,
    };
  }
}
