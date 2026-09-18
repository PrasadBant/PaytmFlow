import type React from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { AssistantModal } from './AssistantModal';

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
      <AssistantModal />
    </div>
  );
};
