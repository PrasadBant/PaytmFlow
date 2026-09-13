import type React from 'react';
import { NavLink } from 'react-router-dom';
import { Home, RotateCw, FileText, HelpCircle, X } from 'lucide-react';
import { useUiStore } from '../state/ui';
import { IconButton } from './primitives/IconButton';
import { cn } from '../lib/utils';

const navItems = [
  { label: 'Home', icon: Home, to: '/' },
  { label: 'Start Journey', icon: RotateCw, to: '/start' },
  { label: 'My Journeys', icon: FileText, to: '/my-journeys' },
  { label: 'Help', icon: HelpCircle, to: '/help' },
];

export interface SidebarProps {
  hideOnDesktop?: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({ hideOnDesktop = false }) => {
  const { isSidebarOpen, closeSidebar } = useUiStore();

  return (
    <>
      {/* Mobile Backdrop */}
      {isSidebarOpen && (
        <div
          data-testid="sidebar-backdrop"
          className="fixed inset-0 bg-content-primary/50 z-40 md:hidden"
          onClick={closeSidebar}
          aria-hidden="true"
        />
      )}

      {/* Sidebar Container */}
      <aside
        aria-label="Sidebar Navigation"
        data-testid="sidebar-container"
        className={cn(
          'fixed inset-y-0 left-0 z-50 w-sidebar bg-surface border-r border-surface-border flex flex-col transition-transform duration-200 ease-in-out',
          hideOnDesktop ? 'hidden' : 'md:static md:translate-x-0',
          isSidebarOpen ? 'translate-x-0 flex' : '-translate-x-full md:flex'
        )}
      >
        {/* Mobile Header (close button + mobile brand) */}
        <div className="h-header flex items-center justify-between px-4 border-b border-surface-border md:hidden">
          <div
            className="font-bold text-xl tracking-tight bg-gradient-to-r from-paytm-blue to-paytm-blue-action bg-clip-text text-transparent"
            data-testid="sidebar-mobile-wordmark"
          >
            <span>Paytm</span>
            <span>Flow</span>
          </div>
          <IconButton
            icon={<X className="w-5 h-5" />}
            onClick={closeSidebar}
            aria-label="Close menu"
            variant="ghost"
          />
        </div>

        {/* Desktop Wordmark Container */}
        <div className="h-header hidden md:flex items-center px-6 border-b border-surface-border">
          <div
            className="font-bold text-xl tracking-tight bg-gradient-to-r from-paytm-blue to-paytm-blue-action bg-clip-text text-transparent"
            data-testid="sidebar-desktop-wordmark"
          >
            <span>Paytm</span>
            <span>Flow</span>
          </div>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 overflow-y-auto py-6 px-4 flex flex-col gap-2" aria-label="Main Navigation">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={closeSidebar}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2.5 rounded-button text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-paytm-blue-action text-content-inverted font-semibold shadow-xs'
                    : 'text-content-secondary hover:bg-surface-hover hover:text-content-primary'
                )
              }
            >
              <item.icon className="w-5 h-5 flex-shrink-0" aria-hidden="true" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>
    </>
  );
};
