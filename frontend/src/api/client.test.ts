import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiClient, buildUrl, apiFetch } from './client';
import { ApiError } from './errors';

describe('api/client — Fetch Wrapper & Contract Standards', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('buildUrl handles relative paths and query parameters', () => {
    const url1 = buildUrl('/session');
    expect(url1).toBe('/api/v1/session');

    const url2 = buildUrl('journeys', { status: 'IN_PROGRESS', limit: 20 });
    expect(url2).toBe('/api/v1/journeys?status=IN_PROGRESS&limit=20');

    const url3 = buildUrl('http://external.test/api', { q: 'test' }, true);
    expect(url3).toBe('http://external.test/api?q=test');
  });

  it('includes credentials: "include" by default on all requests', async () => {
    let capturedInit: RequestInit | undefined;
    globalThis.fetch = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      capturedInit = init;
      return Promise.resolve(
        new Response(JSON.stringify({ session_id: 'sess_123', created: false }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );
    });

    const result = await apiClient.get<{ session_id: string }>('/session');
    expect(result.session_id).toBe('sess_123');
    expect(capturedInit?.credentials).toBe('include');
  });

  it('sends JSON body with application/json header on POST', async () => {
    let capturedInit: RequestInit | undefined;
    globalThis.fetch = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      capturedInit = init;
      return Promise.resolve(
        new Response(JSON.stringify({ journey_id: 'j_1', version_number: 1 }), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        })
      );
    });

    const payload = { journey_type: 'LENDING', goal: { loan_amount: 500000 } };
    await apiClient.post('/journeys', payload);

    expect(capturedInit?.method).toBe('POST');
    expect(capturedInit?.body).toBe(JSON.stringify(payload));
    const headers = capturedInit?.headers as Headers;
    expect(headers.get('Content-Type')).toBe('application/json');
    expect(capturedInit?.credentials).toBe('include');
  });

  it('sends FormData without forcing Content-Type header on postForm', async () => {
    let capturedInit: RequestInit | undefined;
    globalThis.fetch = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      capturedInit = init;
      return Promise.resolve(
        new Response(JSON.stringify({ evidence_id: 'ev_123', requires_review: false }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      );
    });

    const formData = new FormData();
    formData.append('doc_type', 'SALARY_SLIP');
    formData.append('expected_snapshot_id', 'snap_1');

    await apiClient.postForm('/journeys/j_1/evidence', formData);

    expect(capturedInit?.method).toBe('POST');
    expect(capturedInit?.body).toBe(formData);
    const headers = capturedInit?.headers as Headers;
    expect(headers.has('Content-Type')).toBe(false);
  });

  it('parses contract ErrorEnvelope into ApiError on non-2xx status', async () => {
    const errorPayload = {
      error: {
        code: 'ACTION_STALE',
        message: 'This journey has moved on',
        current_snapshot_id: 'snapshot-v2-uuid',
      },
    };

    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(errorPayload), {
        status: 409,
        statusText: 'Conflict',
        headers: { 'Content-Type': 'application/json' },
      })
    );

    try {
      await apiClient.post('/journeys/j_1/actions', { action_id: 'UPLOAD_INCOME_PROOF' });
      expect.unreachable('Should have thrown ApiError');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(409);
      expect(apiErr.code).toBe('ACTION_STALE');
      expect(apiErr.message).toBe('This journey has moved on');
      expect(apiErr.currentSnapshotId).toBe('snapshot-v2-uuid');
      expect(apiErr.isStale).toBe(true);
    }
  });

  it('wraps network failures into ApiError with status 0 and NETWORK_ERROR code', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('Failed to fetch'));

    try {
      await apiFetch('/health');
      expect.unreachable('Should have thrown ApiError');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(0);
      expect(apiErr.code).toBe('NETWORK_ERROR');
      expect(apiErr.message).toBe('Failed to fetch');
    }
  });
});
