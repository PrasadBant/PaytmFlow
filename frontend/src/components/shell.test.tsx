import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AppShell } from './AppShell';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { useUiStore } from '../state/ui';

describe('Application Shell Components Suite (F06)', () => {
  beforeEach(() => {
    // Reset Zustand store state before each test
    act(() => {
      useUiStore.setState({ isSidebarOpen: false });
    });
  });

  describe('AppShell', () => {
    it('renders Header, Sidebar, and the main Outlet content area', () => {
      render(
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="/" element={<div data-testid="test-child-page">Child Page Content</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      );

      expect(screen.getByTestId('app-shell')).toBeInTheDocument();
      expect(screen.getByTestId('sidebar-container')).toBeInTheDocument();
      expect(screen.getByRole('banner')).toBeInTheDocument();
      expect(screen.getByTestId('app-shell-main')).toBeInTheDocument();
      expect(screen.getByTestId('test-child-page')).toHaveTextContent('Child Page Content');
    });
  });

  describe('Header', () => {
    it('contains PaytmFlow wordmark, notification bell with status dot, and user avatar', () => {
      render(
        <MemoryRouter>
          <Header />
        </MemoryRouter>
      );

      // Wordmark verification
      const wordmark = screen.getByTestId('header-wordmark');
      expect(wordmark).toBeInTheDocument();
      expect(wordmark).toHaveTextContent(/Paytm.*Flow/i);

      // Notification bell with status dot
      const bellBtn = screen.getByRole('button', { name: 'Notifications' });
      expect(bellBtn).toBeInTheDocument();
      expect(screen.getByTestId('notification-status-dot')).toBeInTheDocument();

      // User avatar
      const avatar = screen.getByTestId('user-avatar');
      expect(avatar).toBeInTheDocument();
      expect(avatar).toHaveAttribute('aria-label', 'User avatar');
    });

    it('has accessible mobile menu toggle that controls sidebar state', async () => {
      render(
        <MemoryRouter>
          <Header />
        </MemoryRouter>
      );

      const menuBtn = screen.getByRole('button', { name: 'Toggle menu' });
      expect(menuBtn).toBeInTheDocument();

      expect(useUiStore.getState().isSidebarOpen).toBe(false);
      await userEvent.click(menuBtn);
      expect(useUiStore.getState().isSidebarOpen).toBe(true);
      await userEvent.click(menuBtn);
      expect(useUiStore.getState().isSidebarOpen).toBe(false);
    });
  });

  describe('Sidebar', () => {
    it('renders all 4 navigation items with expected labels and targets', () => {
      render(
        <MemoryRouter initialEntries={['/']}>
          <Sidebar />
        </MemoryRouter>
      );

      const links = screen.getAllByRole('link');
      expect(links).toHaveLength(4);
      expect(links.map((l) => l.textContent?.trim())).toEqual([
        'Home',
        'Start Journey',
        'My Journeys',
        'Help',
      ]);

      expect(screen.getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/');
      expect(screen.getByRole('link', { name: 'Start Journey' })).toHaveAttribute('href', '/start');
      expect(screen.getByRole('link', { name: 'My Journeys' })).toHaveAttribute('href', '/my-journeys');
      expect(screen.getByRole('link', { name: 'Help' })).toHaveAttribute('href', '/help');
    });

    it('applies active styling to the current NavLink route', () => {
      render(
        <MemoryRouter initialEntries={['/start']}>
          <Sidebar />
        </MemoryRouter>
      );

      const startLink = screen.getByRole('link', { name: 'Start Journey' });
      const homeLink = screen.getByRole('link', { name: 'Home' });

      // Start Journey is active
      expect(startLink.className).toContain('text-paytm-blue-600');
      expect(startLink.className).toContain('bg-paytm-blue-50');

      // Home is inactive
      expect(homeLink.className).toContain('text-content-secondary');
    });

    it('closes the drawer when a navigation link is clicked', async () => {
      act(() => {
        useUiStore.setState({ isSidebarOpen: true });
      });

      render(
        <MemoryRouter initialEntries={['/']}>
          <Sidebar />
        </MemoryRouter>
      );

      expect(useUiStore.getState().isSidebarOpen).toBe(true);
      const journeysLink = screen.getByRole('link', { name: 'My Journeys' });
      await userEvent.click(journeysLink);
      expect(useUiStore.getState().isSidebarOpen).toBe(false);
    });

    it('handles mobile drawer open and close controls with backdrop', async () => {
      render(
        <MemoryRouter initialEntries={['/']}>
          <Sidebar />
        </MemoryRouter>
      );

      // Initially closed
      const sidebarContainer = screen.getByTestId('sidebar-container');
      expect(sidebarContainer.className).toContain('-translate-x-full');
      expect(screen.queryByTestId('sidebar-backdrop')).not.toBeInTheDocument();

      // Open sidebar
      act(() => {
        useUiStore.setState({ isSidebarOpen: true });
      });

      expect(sidebarContainer.className).toContain('translate-x-0');
      const backdrop = screen.getByTestId('sidebar-backdrop');
      expect(backdrop).toBeInTheDocument();

      // Click close button
      const closeBtn = screen.getByRole('button', { name: 'Close menu' });
      expect(closeBtn).toBeInTheDocument();
      await userEvent.click(closeBtn);
      expect(useUiStore.getState().isSidebarOpen).toBe(false);

      // Re-open and test backdrop click
      act(() => {
        useUiStore.setState({ isSidebarOpen: true });
      });

      const activeBackdrop = screen.getByTestId('sidebar-backdrop');
      await userEvent.click(activeBackdrop);
      expect(useUiStore.getState().isSidebarOpen).toBe(false);
    });

    it('contains responsive visibility classes for desktop and mobile', () => {
      render(
        <MemoryRouter initialEntries={['/']}>
          <Sidebar />
        </MemoryRouter>
      );

      const sidebarContainer = screen.getByTestId('sidebar-container');
      expect(sidebarContainer.className).toContain('md:static');
      expect(sidebarContainer.className).toContain('md:translate-x-0');

      const desktopWordmark = screen.getByTestId('sidebar-desktop-wordmark');
      expect(desktopWordmark.parentElement?.className).toContain('hidden md:flex');

      const mobileWordmark = screen.getByTestId('sidebar-mobile-wordmark');
      expect(mobileWordmark.parentElement?.className).toContain('md:hidden');
    });
  });
});
