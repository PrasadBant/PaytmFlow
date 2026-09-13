import { Component, type ReactNode, type ErrorInfo } from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';
import { Button } from './primitives/Button';

export interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode | ((error: Error, reset: () => void) => ReactNode);
  onReset?: () => void;
}

export interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  public override state: ErrorBoundaryState = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  public override componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    if (process.env.NODE_ENV !== 'test') {
      console.error('Uncaught error caught by ErrorBoundary:', error, errorInfo);
    }
  }

  public resetErrorBoundary = (): void => {
    this.props.onReset?.();
    this.setState({ hasError: false, error: null });
  };

  public override render(): ReactNode {
    if (this.state.hasError && this.state.error) {
      if (typeof this.props.fallback === 'function') {
        return this.props.fallback(this.state.error, this.resetErrorBoundary);
      }
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
          role="alert"
          data-testid="error-boundary-fallback"
          className="min-h-[60vh] flex flex-col items-center justify-center p-6 text-center"
        >
          <div className="w-16 h-16 rounded-full bg-paytm-red-light text-paytm-red flex items-center justify-center mb-4">
            <AlertTriangle className="w-8 h-8" aria-hidden="true" />
          </div>
          <h1 className="text-2xl font-bold text-content-primary mb-2">Something went wrong</h1>
          <p className="text-content-secondary max-w-md mb-6 text-sm">
            {this.state.error.message || 'An unexpected error occurred while loading this page.'}
          </p>
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              onClick={this.resetErrorBoundary}
              data-testid="error-boundary-retry-btn"
            >
              <RefreshCw className="w-4 h-4 mr-2" aria-hidden="true" />
              Try Again
            </Button>
            <a href="/">
              <Button variant="primary" data-testid="error-boundary-home-btn">
                <Home className="w-4 h-4 mr-2" aria-hidden="true" />
                Go to Home
              </Button>
            </a>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
