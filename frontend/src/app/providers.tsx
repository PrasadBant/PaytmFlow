import { useState, type ReactNode, type ReactElement } from 'react';
import { type QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { createDefaultQueryClient } from './queryClient';

export interface AppProvidersProps {
  children: ReactNode;
  queryClient?: QueryClient;
}

export function AppProviders({ children, queryClient }: AppProvidersProps): ReactElement {
  const [client] = useState(() => queryClient ?? createDefaultQueryClient());

  return (
    <ErrorBoundary>
      <QueryClientProvider client={client}>
        {children}
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
