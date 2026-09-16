import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { bootApp } from './boot';
import { apiClient } from '../api/client';

describe('Boot Sequence Suite (F07)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('calls GET /session and returns session data successfully', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({
      session_id: 'session-test-uuid',
      created: true,
    });

    const result = await bootApp();

    expect(result.initialized).toBe(true);
    expect(result.session).toEqual({
      session_id: 'session-test-uuid',
      created: true,
    });
    expect(apiClient.get).toHaveBeenCalledWith('/session');
  });

  it('handles session initialization error gracefully without crashing', async () => {
    vi.spyOn(apiClient, 'get').mockRejectedValueOnce(new Error('Network error during boot'));

    const result = await bootApp();

    expect(result.initialized).toBe(true);
    expect(result.session).toBeNull();
    expect(result.error).toBeDefined();
    expect(result.error?.message).toBe('Network error during boot');
  });
});

describe('Boot Sequence - live mode stops any stale MSW service worker (regression)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('calls worker.stop() when VITE_API_MODE=live, so a service worker registered by an earlier mock-mode visit in the SAME browser cannot silently keep intercepting real requests', async () => {
    // Real-user-reported bug: MSW's service worker persists across page
    // reloads and dev-server restarts, independent of the current page's
    // JS. A browser that previously loaded this app in mock mode would
    // keep serving MSW's canned responses even when genuinely configured
    // for live mode, unless the live path explicitly stops it.
    vi.stubEnv('VITE_API_MODE', 'live');
    const stop = vi.fn().mockResolvedValue(undefined);
    const start = vi.fn().mockResolvedValue(undefined);
    vi.doMock('../mocks/browser', () => ({ worker: { start, stop } }));

    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({
      session_id: 'session-test-uuid',
      created: true,
    });

    const { bootApp: bootAppLive } = await import('./boot');
    const result = await bootAppLive();

    expect(result.mode).toBe('live');
    expect(stop).toHaveBeenCalledTimes(1);
    expect(start).not.toHaveBeenCalled();
  });

  it('calls worker.start(), not worker.stop(), when VITE_API_MODE is not live (mock mode unaffected)', async () => {
    vi.stubEnv('VITE_API_MODE', 'mock');
    const stop = vi.fn().mockResolvedValue(undefined);
    const start = vi.fn().mockResolvedValue(undefined);
    vi.doMock('../mocks/browser', () => ({ worker: { start, stop } }));

    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({
      session_id: 'session-test-uuid',
      created: true,
    });

    const { bootApp: bootAppMock } = await import('./boot');
    const result = await bootAppMock();

    expect(result.mode).toBe('mock');
    expect(start).toHaveBeenCalledTimes(1);
    expect(stop).not.toHaveBeenCalled();
  });
});
