import { ApiError } from './errors';
import type { ErrorEnvelope } from './errors';

export interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined | null>;
  skipBaseUrl?: boolean;
}

const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE || '/api/v1';

/**
 * Builds full URL including query params and base path.
 */
export function buildUrl(endpoint: string, params?: RequestOptions['params'], skipBaseUrl = false): string {
  let urlStr = endpoint;
  if (!skipBaseUrl && !endpoint.startsWith('http://') && !endpoint.startsWith('https://')) {
    const base = DEFAULT_API_BASE.endsWith('/') ? DEFAULT_API_BASE.slice(0, -1) : DEFAULT_API_BASE;
    const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    urlStr = `${base}${path}`;
  }

  if (!params) {
    return urlStr;
  }

  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      searchParams.append(key, String(value));
    }
  }

  const queryString = searchParams.toString();
  if (queryString) {
    urlStr += (urlStr.includes('?') ? '&' : '?') + queryString;
  }

  return urlStr;
}

/**
 * Parses response body; if error status, creates typed ApiError.
 */
async function handleResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');

  if (response.ok) {
    if (response.status === 204) {
      return {} as T;
    }
    if (isJson) {
      return (await response.json()) as T;
    }
    return (await response.text()) as unknown as T;
  }

  let errorCode: string | undefined;
  let errorMessage: string | undefined;
  let errorDetails: Record<string, unknown> | undefined;
  let currentSnapshotId: string | undefined;
  let rawBody: unknown = undefined;

  if (isJson) {
    try {
      const data = (await response.json()) as ErrorEnvelope & Record<string, unknown>;
      rawBody = data;
      if (data && data.error && typeof data.error === 'object') {
        errorCode = data.error.code;
        errorMessage = data.error.message;
        errorDetails = data.error.details;
        currentSnapshotId = data.error.current_snapshot_id;
      } else if (typeof data.message === 'string') {
        errorMessage = data.message;
      }
    } catch {
      // JSON parse failed, fall back to status text
    }
  } else {
    try {
      rawBody = await response.text();
    } catch {
      // Read failed
    }
  }

  throw new ApiError({
    status: response.status,
    code: errorCode,
    message: errorMessage || response.statusText || `HTTP ${response.status}`,
    details: errorDetails,
    currentSnapshotId,
    rawResponse: rawBody,
  });
}

/**
 * Universal API client conforming to PaytmFlow Shared Contract (§4, §5).
 * Always attaches `credentials: 'include'` for anonymous session cookie.
 */
export async function apiFetch<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { params, skipBaseUrl, headers, ...restOptions } = options;
  const url = buildUrl(endpoint, params, skipBaseUrl);

  const mergedHeaders = new Headers(headers);

  // In browser runtime, if ?scenario= is in the page URL, attach x-scenario header for MSW
  if (typeof window !== 'undefined' && window.location?.search) {
    const sc = new URLSearchParams(window.location.search).get('scenario');
    if (sc && !mergedHeaders.has('x-scenario')) {
      mergedHeaders.set('x-scenario', sc);
    }
  }

  // Set credentials to 'include' by default for session cookie management (Contract §4)
  // Disable HTTP cache so back navigation (Screen 6 -> 4) always fetches fresh data (Error #5)
  const fetchConfig: RequestInit = {
    credentials: 'include',
    cache: 'no-store',
    ...restOptions,
    headers: mergedHeaders,
  };

  try {
    const response = await fetch(url, fetchConfig);
    return await handleResponse<T>(response);
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    // Network failures / connection refused
    throw new ApiError({
      status: 0,
      code: 'NETWORK_ERROR',
      message: error instanceof Error ? error.message : 'Network request failed',
      rawResponse: error,
    });
  }
}

export const apiClient = {
  get<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return apiFetch<T>(endpoint, { ...options, method: 'GET' });
  },

  post<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
    const headers = new Headers(options?.headers);
    if (!headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }

    return apiFetch<T>(endpoint, {
      ...options,
      method: 'POST',
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  },

  postForm<T>(endpoint: string, formData: FormData, options?: RequestOptions): Promise<T> {
    const headers = new Headers(options?.headers);
    // Note: Do NOT set Content-Type for FormData so browser computes boundary correctly
    if (headers.has('Content-Type')) {
      headers.delete('Content-Type');
    }

    return apiFetch<T>(endpoint, {
      ...options,
      method: 'POST',
      headers,
      body: formData,
    });
  },

  put<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
    const headers = new Headers(options?.headers);
    if (!headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }

    return apiFetch<T>(endpoint, {
      ...options,
      method: 'PUT',
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  },

  delete<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return apiFetch<T>(endpoint, { ...options, method: 'DELETE' });
  },
};
