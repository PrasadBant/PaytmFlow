import type { ReactElement } from 'react';
import { AppProviders } from './app/providers';
import { AppRouter } from './app/router';
import { BootGate } from './app/BootGate';

export function App(): ReactElement {
  return (
    <AppProviders>
      <BootGate>
        <AppRouter />
      </BootGate>
    </AppProviders>
  );
}

export default App;
