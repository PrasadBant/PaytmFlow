import type React from 'react';
import { Menu, Bell, User } from 'lucide-react';
import { useUiStore } from '../state/ui';
import { IconButton } from './primitives/IconButton';

export const Header: React.FC = () => {
  const toggleSidebar = useUiStore((state) => state.toggleSidebar);

  return (
    <header className="h-header bg-surface border-b border-surface-border flex items-center justify-between px-4 md:px-8 flex-shrink-0">
      <div className="flex items-center gap-4">
        <div className="md:hidden">
          <IconButton
            icon={<Menu className="w-5 h-5" />}
            onClick={toggleSidebar}
            aria-label="Toggle menu"
            data-testid="mobile-menu-toggle"
            variant="ghost"
          />
        </div>
        <div className="font-bold text-xl tracking-tight" data-testid="header-wordmark">
          <span className="text-paytm-blue">Paytm</span>
          <span className="text-content-primary">Flow</span>
        </div>
      </div>

      <div className="flex items-center gap-2 ml-auto">
        <div className="relative">
          <IconButton
            icon={<Bell className="w-5 h-5" />}
            aria-label="Notifications"
            variant="ghost"
          />
          <span
            data-testid="notification-status-dot"
            className="absolute top-2 right-2.5 w-2 h-2 bg-paytm-red rounded-full ring-2 ring-surface"
            aria-hidden="true"
          />
        </div>
        <div
          role="img"
          aria-label="User avatar"
          data-testid="user-avatar"
          className="w-8 h-8 rounded-full bg-paytm-blue text-white flex items-center justify-center font-bold text-xs shadow-xs ml-2 select-none"
        >
          <span>AS</span>
          <span className="sr-only">
            <User className="w-4 h-4" />
          </span>
        </div>
      </div>
    </header>
  );
};
