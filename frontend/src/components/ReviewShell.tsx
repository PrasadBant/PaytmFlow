import type React from 'react';
import { Outlet } from 'react-router-dom';
import { LayoutDashboard, ListChecks } from 'lucide-react';
import { Sidebar, type NavItem } from './Sidebar';
import { Header } from './Header';

const reviewerNavItems: NavItem[] = [
  { label: 'Dashboard', icon: LayoutDashboard, to: '/review' },
  { label: 'Review Queue', icon: ListChecks, to: '/review/queue' },
];

// Deliberately a second, sibling shell rather than branching AppShell on
// role - keeps the customer shell free of reviewer-only logic while
// sharing the same Header/Sidebar primitives and design tokens.
export const ReviewShell: React.FC = () => {
  return (
    <div
      className="flex h-screen w-full bg-surface-subtle overflow-hidden"
      data-testid="review-shell"
    >
      <Sidebar navItems={reviewerNavItems} />
      <div className="flex flex-col flex-1 min-w-0">
        <Header />
        <main className="flex-1 overflow-y-auto relative" data-testid="review-shell-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default ReviewShell;
