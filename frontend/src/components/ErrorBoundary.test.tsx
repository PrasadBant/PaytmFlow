import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ErrorBoundary } from './ErrorBoundary';

function ProblemComponent({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error('Test crash in component render');
  }
  return <div data-testid="healthy-component">All good!</div>;
}

describe('ErrorBoundary Suite (F07)', () => {
  const originalConsoleError = console.error;

  beforeEach(() => {
    // Silence console error logs during deliberate error boundary tests
    console.error = vi.fn();
  });

  afterEach(() => {
    console.error = originalConsoleError;
  });

  it('renders children normally when no error occurs', () => {
    render(
      <ErrorBoundary>
        <ProblemComponent shouldThrow={false} />
      </ErrorBoundary>
    );

    expect(screen.getByTestId('healthy-component')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('catches render errors and displays user-friendly fallback UI', () => {
    render(
      <ErrorBoundary>
        <ProblemComponent shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('Test crash in component render')).toBeInTheDocument();
    expect(screen.getByTestId('error-boundary-retry-btn')).toBeInTheDocument();
    expect(screen.getByTestId('error-boundary-home-btn')).toBeInTheDocument();
  });

  it('allows retrying and resetting error state', async () => {
    const onReset = vi.fn();
    const { rerender } = render(
      <ErrorBoundary onReset={onReset}>
        <ProblemComponent shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();

    // Rerender with healthy state before clicking retry
    rerender(
      <ErrorBoundary onReset={onReset}>
        <ProblemComponent shouldThrow={false} />
      </ErrorBoundary>
    );

    const retryBtn = screen.getByTestId('error-boundary-retry-btn');
    await userEvent.click(retryBtn);

    expect(onReset).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('healthy-component')).toBeInTheDocument();
  });

  it('renders custom fallback function when provided', () => {
    render(
      <ErrorBoundary
        fallback={(error, reset) => (
          <div data-testid="custom-fallback">
            <span>Custom: {error.message}</span>
            <button onClick={reset}>Custom Reset</button>
          </div>
        )}
      >
        <ProblemComponent shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByTestId('custom-fallback')).toBeInTheDocument();
    expect(screen.getByText('Custom: Test crash in component render')).toBeInTheDocument();
  });
});
