import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { StaleBanner } from './StaleBanner';
import { ErrorState } from './ErrorState';
import { EmptyState } from './EmptyState';
import { DeadEndState } from './DeadEndState';
import { ApiError, mapErrorToUxAction } from '@/api/errors';
import { Inbox } from 'lucide-react';

const mockedNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockedNavigate,
  };
});

describe('Phase F26: Error Surface and Recovery Components', () => {
  describe('<StaleBanner />', () => {
    it('renders default stale message and role=alert', () => {
      render(<StaleBanner />);
      const banner = screen.getByTestId('stale-banner');
      expect(banner).toBeInTheDocument();
      expect(banner).toHaveAttribute('role', 'alert');
      expect(
        screen.getByText('This journey has moved on — refreshing with latest state.')
      ).toBeInTheDocument();
      expect(screen.getByText('Outdated Snapshot Detected')).toBeInTheDocument();
    });

    it('renders custom message and triggers onRefresh', () => {
      const onRefresh = vi.fn();
      render(
        <StaleBanner
          message="Server state version mismatch. Please reload."
          onRefresh={onRefresh}
        />
      );

      expect(
        screen.getByText('Server state version mismatch. Please reload.')
      ).toBeInTheDocument();
      const refreshBtn = screen.getByTestId('stale-refresh-btn');
      expect(refreshBtn).toHaveTextContent('Refresh Now');

      fireEvent.click(refreshBtn);
      expect(onRefresh).toHaveBeenCalledTimes(1);
    });

    it('displays refreshing state and disables button when isRefreshing=true', () => {
      const onRefresh = vi.fn();
      render(<StaleBanner onRefresh={onRefresh} isRefreshing={true} />);

      const refreshBtn = screen.getByTestId('stale-refresh-btn');
      expect(refreshBtn).toBeDisabled();
      expect(refreshBtn).toHaveTextContent('Refreshing...');
    });
  });

  describe('<ErrorState />', () => {
    it('renders default title and message with role=alert', () => {
      render(<ErrorState />);
      const errorCard = screen.getByTestId('error-state');
      expect(errorCard).toBeInTheDocument();
      expect(errorCard).toHaveAttribute('role', 'alert');
      expect(screen.getByText('Unable to Load Data')).toBeInTheDocument();
      expect(
        screen.getByText('An unexpected error occurred while processing your request.')
      ).toBeInTheDocument();
    });

    it('renders custom title, message, and error code badge', () => {
      render(
        <ErrorState
          title="Custom Action Failure"
          message="Could not verify salary slip."
          errorCode="EVIDENCE_CONFLICT"
        />
      );

      expect(screen.getByText('Custom Action Failure')).toBeInTheDocument();
      expect(screen.getByText('Could not verify salary slip.')).toBeInTheDocument();
      expect(screen.getByText('Code: EVIDENCE_CONFLICT')).toBeInTheDocument();
    });

    it('handles retry callback and isRetrying loading state', () => {
      const onRetry = vi.fn();
      const { rerender } = render(
        <ErrorState onRetry={onRetry} retryLabel="Retry Request" />
      );

      const retryBtn = screen.getByTestId('error-retry-btn');
      expect(retryBtn).toHaveTextContent('Retry Request');
      expect(retryBtn).not.toBeDisabled();

      fireEvent.click(retryBtn);
      expect(onRetry).toHaveBeenCalledTimes(1);

      rerender(<ErrorState onRetry={onRetry} isRetrying={true} />);
      expect(screen.getByTestId('error-retry-btn')).toBeDisabled();
      expect(screen.getByTestId('error-retry-btn')).toHaveTextContent('Retrying...');
    });

    it('renders secondary action button and calls action.onClick', () => {
      const onActionClick = vi.fn();
      render(
        <ErrorState
          action={{
            label: 'Go to Selection',
            onClick: onActionClick,
            variant: 'secondary',
          }}
        />
      );

      const actionBtn = screen.getByTestId('error-action-btn');
      expect(actionBtn).toHaveTextContent('Go to Selection');

      fireEvent.click(actionBtn);
      expect(onActionClick).toHaveBeenCalledTimes(1);
    });

    it('renders optional children content', () => {
      render(
        <ErrorState>
          <div data-testid="error-extra-details">Diagnostic details: socket timeout</div>
        </ErrorState>
      );
      expect(screen.getByTestId('error-extra-details')).toBeInTheDocument();
    });
  });

  describe('<EmptyState />', () => {
    it('renders default empty message and icon', () => {
      render(<EmptyState />);
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
      expect(screen.getByText('No Records Found')).toBeInTheDocument();
      expect(
        screen.getByText('There are no items to display at this time.')
      ).toBeInTheDocument();
    });

    it('renders custom title, description, and custom icon', () => {
      render(
        <EmptyState
          title="No Active Applications"
          description="You do not have any pending journeys."
          icon={Inbox}
        />
      );
      expect(screen.getByText('No Active Applications')).toBeInTheDocument();
      expect(screen.getByText('You do not have any pending journeys.')).toBeInTheDocument();
    });

    it('renders action button and handles click', () => {
      const onAction = vi.fn();
      render(
        <EmptyState
          action={{
            label: 'Start Application',
            onClick: onAction,
          }}
        />
      );

      const btn = screen.getByTestId('empty-state-action-btn');
      expect(btn).toHaveTextContent('Start Application');
      fireEvent.click(btn);
      expect(onAction).toHaveBeenCalledTimes(1);
    });
  });

  describe('<DeadEndState />', () => {
    it('renders dead-end information and guidance', () => {
      render(
        <MemoryRouter>
          <DeadEndState journeyId="j-dead-1" />
        </MemoryRouter>
      );

      expect(screen.getByTestId('dead-end-state')).toBeInTheDocument();
      expect(screen.getByText('No Automated Action Available')).toBeInTheDocument();
      expect(
        screen.getByText(
          'Based on the provided information, no further automated actions can resolve the current requirements.'
        )
      ).toBeInTheDocument();
      expect(screen.getByText('What can you do next?')).toBeInTheDocument();
    });

    it('navigates to journey status or start screen', () => {
      mockedNavigate.mockReset();
      render(
        <MemoryRouter>
          <DeadEndState journeyId="j-dead-1" />
        </MemoryRouter>
      );

      const backBtn = screen.getByText('Back to Status');
      fireEvent.click(backBtn);
      expect(mockedNavigate).toHaveBeenCalledWith('/j/j-dead-1');

      const exploreBtn = screen.getByText('Explore Other Journeys');
      fireEvent.click(exploreBtn);
      expect(mockedNavigate).toHaveBeenCalledWith('/start');
    });
  });

  describe('Contract §5.1 Error Code to UX Action Mapping', () => {
    it('maps 400 VALIDATION_ERROR to INLINE_FIELD_ERRORS with field details', () => {
      const err = new ApiError({
        status: 400,
        code: 'VALIDATION_ERROR',
        message: 'Invalid form input',
        details: { monthly_income: 'Minimum income is ₹15,000' },
      });

      const ux = mapErrorToUxAction(err);
      expect(ux.type).toBe('INLINE_FIELD_ERRORS');
      expect(ux.canRetry).toBe(false);
      expect(ux.refetchRecommended).toBe(false);
      expect(ux.fieldErrors).toEqual({ monthly_income: 'Minimum income is ₹15,000' });
    });

    it('maps 400 INVALID_JOURNEY_TYPE to NAVIGATE_SELECTION_ERROR', () => {
      const err = new ApiError({
        status: 400,
        code: 'INVALID_JOURNEY_TYPE',
        message: 'Journey type CRYPTO is not supported',
      });

      const ux = mapErrorToUxAction(err);
      expect(ux.type).toBe('NAVIGATE_SELECTION_ERROR');
      expect(ux.canRetry).toBe(false);
      expect(ux.refetchRecommended).toBe(true);
    });

    it('maps 404 to JOURNEY_NOT_FOUND', () => {
      const err = new ApiError({
        status: 404,
        message: 'Not found',
      });

      const ux = mapErrorToUxAction(err);
      expect(ux.type).toBe('JOURNEY_NOT_FOUND');
      expect(ux.message).toBe("This journey isn't available.");
      expect(ux.canRetry).toBe(false);
      expect(ux.refetchRecommended).toBe(true);
    });

    it('maps 409 ACTION_STALE to ACTION_STALE_BANNER with currentSnapshotId', () => {
      const err = new ApiError({
        status: 409,
        code: 'ACTION_STALE',
        currentSnapshotId: 'snap-v3-new',
      });

      const ux = mapErrorToUxAction(err);
      expect(ux.type).toBe('ACTION_STALE_BANNER');
      expect(ux.message).toContain('This journey has moved on — refreshing');
      expect(ux.currentSnapshotId).toBe('snap-v3-new');
      expect(ux.canRetry).toBe(false);
      expect(ux.refetchRecommended).toBe(true);
    });

    it('maps 422 ACTION_INVALID to ACTION_INVALID_STATE', () => {
      const err = new ApiError({
        status: 422,
        code: 'ACTION_INVALID',
        message: 'Income proof already uploaded',
      });

      const ux = mapErrorToUxAction(err);
      expect(ux.type).toBe('ACTION_INVALID_STATE');
      expect(ux.message).toBe('Income proof already uploaded');
      expect(ux.canRetry).toBe(false);
      expect(ux.refetchRecommended).toBe(true);
    });

    it('maps 413 Payload Too Large to FILE_TOO_LARGE', () => {
      const err = new ApiError({
        status: 413,
      });

      const ux = mapErrorToUxAction(err);
      expect(ux.type).toBe('FILE_TOO_LARGE');
      expect(ux.message).toBe('That file is over 10MB.');
      expect(ux.canRetry).toBe(true);
      expect(ux.refetchRecommended).toBe(false);
    });

    it('maps 500 / 5xx Server Errors to RETRYABLE_ERROR', () => {
      const err = new ApiError({
        status: 500,
        message: 'Internal engine error',
      });

      const ux = mapErrorToUxAction(err);
      expect(ux.type).toBe('RETRYABLE_ERROR');
      expect(ux.canRetry).toBe(true);
      expect(ux.refetchRecommended).toBe(false);
    });

    it('maps network errors or generic JS Error to RETRYABLE_ERROR', () => {
      const netErr = new Error('Failed to fetch');
      const ux = mapErrorToUxAction(netErr);
      expect(ux.type).toBe('RETRYABLE_ERROR');
      expect(ux.message).toBe('Failed to fetch');
      expect(ux.canRetry).toBe(true);
      expect(ux.refetchRecommended).toBe(false);
    });
  });
});
