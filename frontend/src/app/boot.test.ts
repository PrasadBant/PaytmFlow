import { describe, it, expect, vi, beforeEach } from 'vitest';
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
