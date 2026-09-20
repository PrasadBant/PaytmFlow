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

export interface BootOptions {
  /** Skip MSW worker start/stop — used when retrying just the session fetch. */
  skipWorkerSetup?: boolean;
}

/**
 * Executes the boot sequence:
 * 1. Initializes MSW in browser if in mock mode.
 * 2. Calls GET /session to establish anonymous session cookie before first paint.
 */
export async function bootApp(options: BootOptions = {}): Promise<BootResult> {
  const mode = import.meta.env.VITE_API_MODE === 'live' ? 'live' : 'mock';

  if (!options.skipWorkerSetup && typeof window !== 'undefined' && mode === 'mock') {
    try {
      const { worker } = await import('../mocks/browser');
      await worker.start({
        onUnhandledRequest: 'bypass',
        quiet: true,
      });
    } catch {
      // Mock worker setup bypassed or running in headless / test environment
    }
  } else if (!options.skipWorkerSetup && typeof window !== 'undefined' && mode === 'live') {
    try {
      const { worker } = await import('../mocks/browser');
      worker.stop();
    } catch {
      // Safe no-op if worker not registered
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
