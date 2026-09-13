import { type ReactElement, type ReactNode, type KeyboardEvent } from 'react';
import { cn } from '@/lib/utils';

export interface TabItem {
  id: string;
  label: string;
  icon?: ReactNode;
  badge?: ReactNode;
  disabled?: boolean;
}

export interface TabsProps {
  tabs: TabItem[];
  activeTab: string;
  onChange: (id: string) => void;
  className?: string;
  variant?: 'underline' | 'pills' | 'segmented';
  size?: 'sm' | 'md';
}

export function Tabs({
  tabs,
  activeTab,
  onChange,
  className,
  variant = 'underline',
  size = 'md',
}: TabsProps): ReactElement {
  const handleKeyDown = (e: KeyboardEvent<HTMLButtonElement>): void => {
    const currentIndex = tabs.findIndex((t) => t.id === activeTab);
    if (currentIndex === -1) return;

    let nextIndex = currentIndex;
    if (e.key === 'ArrowRight') {
      nextIndex = (currentIndex + 1) % tabs.length;
    } else if (e.key === 'ArrowLeft') {
      nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    } else if (e.key === 'Home') {
      nextIndex = 0;
    } else if (e.key === 'End') {
      nextIndex = tabs.length - 1;
    } else {
      return;
    }

    e.preventDefault();
    if (!tabs[nextIndex].disabled) {
      onChange(tabs[nextIndex].id);
      // Focus the newly active tab button
      const nextBtn = document.getElementById(`tab-${tabs[nextIndex].id}`);
      nextBtn?.focus();
    }
  };

  const variantContainerStyles = {
    underline: 'flex border-b border-surface-border gap-6',
    pills: 'flex gap-2 p-1 bg-surface-subtle rounded-card border border-surface-border',
    segmented: 'grid grid-cols-2 p-1 bg-surface-subtle rounded-card border border-surface-border',
  };

  return (
    <div
      role="tablist"
      aria-orientation="horizontal"
      className={cn(variantContainerStyles[variant], className)}
    >
      {tabs.map((tab) => {
        const isActive = tab.id === activeTab;

        let tabStyles = '';
        if (variant === 'underline') {
          tabStyles = cn(
            'inline-flex items-center gap-2 font-semibold pb-3 -mb-px border-b-2 text-sm transition-colors duration-150',
            isActive
              ? 'border-paytm-blue text-paytm-blue'
              : 'border-transparent text-content-secondary hover:text-content-primary hover:border-slate-300',
            tab.disabled && 'opacity-40 cursor-not-allowed'
          );
        } else if (variant === 'pills') {
          tabStyles = cn(
            'inline-flex items-center justify-center gap-2 font-medium px-4 py-2 rounded-button text-sm transition-all duration-150',
            isActive
              ? 'bg-paytm-blue text-white shadow-xs'
              : 'text-content-secondary hover:text-content-primary hover:bg-surface',
            tab.disabled && 'opacity-40 cursor-not-allowed'
          );
        } else if (variant === 'segmented') {
          tabStyles = cn(
            'inline-flex items-center justify-center gap-2 font-medium px-4 py-2 rounded-button text-sm transition-all duration-150 text-center',
            isActive
              ? 'bg-white text-content-primary shadow-sm font-semibold'
              : 'text-content-secondary hover:text-content-primary',
            tab.disabled && 'opacity-40 cursor-not-allowed'
          );
        }

        if (size === 'sm') {
          tabStyles = cn(tabStyles, 'text-xs py-1.5 px-3');
        }

        return (
          <button
            key={tab.id}
            role="tab"
            type="button"
            id={`tab-${tab.id}`}
            aria-selected={isActive}
            aria-controls={`tabpanel-${tab.id}`}
            tabIndex={isActive ? 0 : -1}
            disabled={tab.disabled}
            onClick={() => !tab.disabled && onChange(tab.id)}
            onKeyDown={handleKeyDown}
            className={tabStyles}
          >
            {tab.icon && <span className="shrink-0">{tab.icon}</span>}
            <span>{tab.label}</span>
            {tab.badge}
          </button>
        );
      })}
    </div>
  );
}

export default Tabs;
