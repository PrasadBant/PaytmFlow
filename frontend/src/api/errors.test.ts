import { describe, it, expect } from 'vitest';
import { ApiError, mapErrorToUxAction } from './errors';

describe('api/errors — Contract §5.1 Error Mapping Matrix', () => {
  it('maps 400 VALIDATION_ERROR to INLINE_FIELD_ERRORS with field error details', () => {
    const error = new ApiError({
      status: 400,
      code: 'VALIDATION_ERROR',
      message: 'Validation failed for goal form',
      details: {
        loan_amount: 'Amount exceeds maximum allowed',
        tenure_months: 'Tenure must be at least 6 months',
      },
    });

    expect(error.isValidationError).toBe(true);
    expect(error.fieldErrors).toEqual({
      loan_amount: 'Amount exceeds maximum allowed',
      tenure_months: 'Tenure must be at least 6 months',
    });

    const uxAction = mapErrorToUxAction(error);
    expect(uxAction.type).toBe('INLINE_FIELD_ERRORS');
    expect(uxAction.fieldErrors).toEqual({
      loan_amount: 'Amount exceeds maximum allowed',
      tenure_months: 'Tenure must be at least 6 months',
    });
    expect(uxAction.canRetry).toBe(false);
  });

  it('maps 400 INVALID_JOURNEY_TYPE to NAVIGATE_SELECTION_ERROR', () => {
    const error = new ApiError({
      status: 400,
      code: 'INVALID_JOURNEY_TYPE',
      message: 'Unknown journey type: CRYPTO',
    });

    expect(error.isInvalidJourneyType).toBe(true);
    const uxAction = mapErrorToUxAction(error);
    expect(uxAction.type).toBe('NAVIGATE_SELECTION_ERROR');
    expect(uxAction.refetchRecommended).toBe(true);
  });

  it('maps 404 to JOURNEY_NOT_FOUND with exact contract message', () => {
    const error = new ApiError({
      status: 404,
      code: 'NOT_FOUND',
      message: 'Journey not found',
    });

    expect(error.isNotFound).toBe(true);
    const uxAction = mapErrorToUxAction(error);
    expect(uxAction.type).toBe('JOURNEY_NOT_FOUND');
    expect(uxAction.message).toBe("This journey isn't available.");
    expect(uxAction.refetchRecommended).toBe(true);
  });

  it('maps 409 ACTION_STALE to amber ACTION_STALE_BANNER with current_snapshot_id and no retry', () => {
    const error = new ApiError({
      status: 409,
      code: 'ACTION_STALE',
      message: 'Snapshot is stale',
      currentSnapshotId: 'uuid-current-snapshot-v3',
    });

    expect(error.isStale).toBe(true);
    expect(error.currentSnapshotId).toBe('uuid-current-snapshot-v3');

    const uxAction = mapErrorToUxAction(error);
    expect(uxAction.type).toBe('ACTION_STALE_BANNER');
    expect(uxAction.message).toBe('This journey has moved on — refreshing');
    expect(uxAction.currentSnapshotId).toBe('uuid-current-snapshot-v3');
    expect(uxAction.canRetry).toBe(false);
    expect(uxAction.refetchRecommended).toBe(true);
  });

  it('maps 422 ACTION_INVALID to ACTION_INVALID_STATE with refetch recommendation', () => {
    const error = new ApiError({
      status: 422,
      code: 'ACTION_INVALID',
      message: 'Action cannot be taken in current state',
    });

    expect(error.isInvalidAction).toBe(true);
    const uxAction = mapErrorToUxAction(error);
    expect(uxAction.type).toBe('ACTION_INVALID_STATE');
    expect(uxAction.canRetry).toBe(false);
    expect(uxAction.refetchRecommended).toBe(true);
  });

  it('maps 413 to FILE_TOO_LARGE with 10MB message', () => {
    const error = new ApiError({
      status: 413,
      code: 'PAYLOAD_TOO_LARGE',
      message: 'Payload Too Large',
    });

    expect(error.isPayloadTooLarge).toBe(true);
    const uxAction = mapErrorToUxAction(error);
    expect(uxAction.type).toBe('FILE_TOO_LARGE');
    expect(uxAction.message).toBe('That file is over 10MB.');
    expect(uxAction.canRetry).toBe(true);
  });

  it('maps 5xx server errors to RETRYABLE_ERROR', () => {
    const error = new ApiError({
      status: 500,
      code: 'INTERNAL_SERVER_ERROR',
      message: 'Internal server error occurred',
    });

    expect(error.isServerError).toBe(true);
    const uxAction = mapErrorToUxAction(error);
    expect(uxAction.type).toBe('RETRYABLE_ERROR');
    expect(uxAction.canRetry).toBe(true);
  });

  it('maps network failures (status 0 / Error) to RETRYABLE_ERROR', () => {
    const error = new ApiError({
      status: 0,
      code: 'NETWORK_ERROR',
      message: 'Failed to fetch',
    });

    const uxAction = mapErrorToUxAction(error);
    expect(uxAction.type).toBe('RETRYABLE_ERROR');
    expect(uxAction.canRetry).toBe(true);
  });

  it('handles non-ApiError exceptions gracefully', () => {
    const plainError = new Error('Generic connection error');
    const uxAction = mapErrorToUxAction(plainError);
    expect(uxAction.type).toBe('RETRYABLE_ERROR');
    expect(uxAction.message).toBe('Generic connection error');
  });
});
