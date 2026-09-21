import type React from 'react';
import { lazy, Suspense } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';

// Code-split out of the main bundle: the assistant's own chat/voice/
// translate code has zero business being in the critical initial-load path
// (per PaytmFlow's chat-must-never-block-boot rule). It already renders
// `null` while closed and fires no network requests until the user acts, so
// the only remaining win here is keeping its JS out of the eagerly-loaded
// bundle too.
const AssistantModal = lazy(() =>
  import('./AssistantModal').then((m) => ({ default: m.AssistantModal }))
);

export const AppShell: React.FC = () => {
  const location = useLocation();
  const isLanding = location.pathname === '/';

  return (
    <div className="flex h-screen w-full bg-surface-subtle overflow-hidden" data-testid="app-shell">
      <Sidebar hideOnDesktop={isLanding} />
      <div className="flex flex-col flex-1 min-w-0">
        <Header />
        <main className="flex-1 overflow-y-auto relative" data-testid="app-shell-main">
          <Outlet />
        </main>
      </div>
      <Suspense fallback={null}>
        <AssistantModal />
      </Suspense>
    </div>
  );
};
