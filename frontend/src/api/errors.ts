import type { components } from './types.gen';

export type ErrorCode = components['schemas']['ErrorCode'];
export type ErrorEnvelope = components['schemas']['ErrorEnvelope'];

export interface ApiErrorOptions {
  status: number;
  code?: ErrorCode | string;
  message?: string;
  details?: Record<string, unknown>;
  currentSnapshotId?: string;
  rawResponse?: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: ErrorCode | string;
  readonly details?: Record<string, unknown>;
  readonly currentSnapshotId?: string;
  readonly rawResponse?: unknown;

  constructor(options: ApiErrorOptions) {
    const message = options.message || `API request failed with status ${options.status}`;
    super(message);
    this.name = 'ApiError';
    this.status = options.status;
    this.code = options.code || 'UNKNOWN_ERROR';
    this.details = options.details;
    this.currentSnapshotId = options.currentSnapshotId;
    this.rawResponse = options.rawResponse;

    // Maintain proper prototype chain for instanceof checks
    Object.setPrototypeOf(this, ApiError.prototype);
  }

  get isStale(): boolean {
    return this.status === 409 || this.code === 'ACTION_STALE';
  }

  get isInvalidAction(): boolean {
    return this.status === 422 || this.code === 'ACTION_INVALID';
  }

  get isValidationError(): boolean {
    return this.status === 400 && this.code === 'VALIDATION_ERROR';
  }

  get isInvalidJourneyType(): boolean {
    return this.status === 400 && this.code === 'INVALID_JOURNEY_TYPE';
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isPayloadTooLarge(): boolean {
    return this.status === 413;
  }

  get isServerError(): boolean {
    return this.status >= 500 && this.status <= 599;
  }

  /**
   * Extracts typed field errors if present in details (e.g. { field: "message" })
   */
  get fieldErrors(): Record<string, string> {
    if (!this.details || typeof this.details !== 'object') {
      return {};
    }
    const result: Record<string, string> = {};
    for (const [key, value] of Object.entries(this.details)) {
      if (typeof value === 'string') {
        result[key] = value;
      } else if (value && typeof value === 'object' && 'message' in value) {
        result[key] = String((value as { message: unknown }).message);
      }
    }
    return result;
  }
}

export type UxActionType =
  | 'INLINE_FIELD_ERRORS'
  | 'NAVIGATE_SELECTION_ERROR'
  | 'JOURNEY_NOT_FOUND'
  | 'ACTION_STALE_BANNER'
  | 'ACTION_INVALID_STATE'
  | 'FILE_TOO_LARGE'
  | 'RETRYABLE_ERROR'
  | 'GENERIC_ERROR';

export interface UxAction {
  type: UxActionType;
  message: string;
  fieldErrors?: Record<string, string>;
  currentSnapshotId?: string;
  canRetry: boolean;
  refetchRecommended: boolean;
}

/**
 * Maps contract API errors to precise UX actions specified in 00_SHARED_CONTRACT.md §5.1
 */
export function mapErrorToUxAction(error: unknown): UxAction {
  if (error instanceof ApiError) {
    if (error.isValidationError) {
      return {
        type: 'INLINE_FIELD_ERRORS',
        message: error.message || 'Please correct the errors in the form.',
        fieldErrors: error.fieldErrors,
        canRetry: false,
        refetchRecommended: false,
      };
    }

    if (error.isInvalidJourneyType) {
      return {
        type: 'NAVIGATE_SELECTION_ERROR',
        message: error.message || 'Selected journey type is invalid or not supported.',
        canRetry: false,
        refetchRecommended: true,
      };
    }

    if (error.isNotFound) {
      return {
        type: 'JOURNEY_NOT_FOUND',
        message: "This journey isn't available.",
        canRetry: false,
        refetchRecommended: true,
      };
    }

    if (error.isStale) {
      return {
        type: 'ACTION_STALE_BANNER',
        message: 'This journey has moved on — refreshing',
        currentSnapshotId: error.currentSnapshotId,
        canRetry: false,
        refetchRecommended: true,
      };
    }

    if (error.isInvalidAction) {
      return {
        type: 'ACTION_INVALID_STATE',
        message: error.message || 'This action is no longer valid for the current journey state.',
        canRetry: false,
        refetchRecommended: true,
      };
    }

    if (error.isPayloadTooLarge) {
      return {
        type: 'FILE_TOO_LARGE',
        message: 'That file is over 10MB.',
        canRetry: true,
        refetchRecommended: false,
      };
    }

    if (error.isServerError) {
      return {
        type: 'RETRYABLE_ERROR',
        message: error.message || 'Server error occurred. Please try again.',
        canRetry: true,
        refetchRecommended: false,
      };
    }
  }

  // Network errors or generic unknown exceptions
  const message = error instanceof Error ? error.message : 'A network error occurred.';
  return {
    type: 'RETRYABLE_ERROR',
    message,
    canRetry: true,
    refetchRecommended: false,
  };
}
