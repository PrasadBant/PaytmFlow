import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppShell } from '@/components/AppShell';
import { useUiStore } from '@/state/ui';
import { Screen02JourneySelection } from '@/screens/Screen02JourneySelection';
import { Screen04CurrentStatus } from '@/screens/Screen04CurrentStatus';
import { Screen07AiAnalysis } from '@/screens/Screen07AiAnalysis';
import { JourneyDiff } from '@/components/JourneyDiff';
import { ProgressRing } from '@/components/ProgressRing';
import { Modal } from '@/components/primitives/Modal';

function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

describe('Phase F28: Responsive Design & Layout Verification (375px / 768px / 1440px)', () => {
  beforeEach(() => {
    useUiStore.setState({ isSidebarOpen: false });
    window.sessionStorage.clear();
  });

  describe('1. Navigation, Sidebar & Mobile Drawer Behavior', () => {
    it('AppShell & Header render hamburger trigger on mobile and open/close drawer via state', () => {
      render(
        <MemoryRouter initialEntries={['/']}>
          <AppShell />
        </MemoryRouter>
      );

      const sidebarContainer = screen.getByTestId('sidebar-container');
      expect(sidebarContainer).toBeInTheDocument();
      // Off-canvas by default on mobile
      expect(sidebarContainer.className).toContain('-translate-x-full');
      expect(screen.queryByTestId('sidebar-backdrop')).not.toBeInTheDocument();

      // Open drawer via header button
      const toggleBtn = screen.getByRole('button', { name: /Toggle menu/i });
      expect(toggleBtn).toBeInTheDocument();
      fireEvent.click(toggleBtn);

      // Now drawer is open and backdrop exists
      expect(useUiStore.getState().isSidebarOpen).toBe(true);
      expect(sidebarContainer.className).toContain('translate-x-0');
      const backdrop = screen.getByTestId('sidebar-backdrop');
      expect(backdrop).toBeInTheDocument();

      // Clicking backdrop closes drawer
      fireEvent.click(backdrop);
      expect(useUiStore.getState().isSidebarOpen).toBe(false);
    });

    it('Mobile drawer close button dismisses sidebar navigation', () => {
      useUiStore.setState({ isSidebarOpen: true });
      render(
        <MemoryRouter initialEntries={['/']}>
          <AppShell />
        </MemoryRouter>
      );

      const closeBtn = screen.getByRole('button', { name: /Close menu/i });
      expect(closeBtn).toBeInTheDocument();

      fireEvent.click(closeBtn);
      expect(useUiStore.getState().isSidebarOpen).toBe(false);
    });
  });

  describe('2. Grid and Responsive Card Layouts', () => {
    it('Screen 2 Journey Selection renders responsive grid container with flagship badge', async () => {
      const { container } = render(
        <QueryClientProvider client={createTestQueryClient()}>
          <MemoryRouter initialEntries={['/start']}>
            <Routes>
              <Route path="/start" element={<Screen02JourneySelection />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      );

      await screen.findByTestId('pack-card-LENDING');

      // Check responsive grid class
      const grid = container.querySelector('.grid');
      expect(grid).toBeInTheDocument();
      expect(grid?.className).toContain('grid-cols-1');
      expect(grid?.className).toContain('md:grid-cols-2');

      const flagshipCard = screen.getByTestId('pack-card-LENDING');
      expect(flagshipCard).toHaveTextContent('Personal Loan');
      expect(flagshipCard).toHaveTextContent('Flagship Demo');
    });

    it('ProgressRing supports mobile and desktop scales (sm, md, lg)', () => {
      const { rerender } = render(<ProgressRing completed={3} total={7} size="sm" />);
      let ring = screen.getByTestId('progress-ring');
      expect(ring).toHaveStyle({ width: '88px', height: '88px' });
      expect(screen.getByTestId('progress-ring-count')).toHaveTextContent('3/7');

      rerender(<ProgressRing completed={4} total={7} size="lg" />);
      ring = screen.getByTestId('progress-ring');
      expect(ring).toHaveStyle({ width: '160px', height: '160px' });
      expect(screen.getByTestId('progress-ring-count')).toHaveTextContent('4/7');
    });

    it('Screen 4 Status Card stacks layout vertically on small screens and row on tablet/desktop', async () => {
      const { container } = render(
        <QueryClientProvider client={createTestQueryClient()}>
          <MemoryRouter initialEntries={['/j/11111111-1111-1111-1111-111111111111']}>
            <Routes>
              <Route path="/j/:id" element={<Screen04CurrentStatus />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      );

      await screen.findByTestId('screen-04-current-status');

      // Progress card inner container has flex-col on mobile and sm:flex-row on larger viewports
      const flexContainer = container.querySelector('.flex-col.sm\\:flex-row');
      expect(flexContainer).toBeInTheDocument();
    });
  });

  describe('3. JourneyDiff and State Preview Responsive Stacking', () => {
    it('JourneyDiff field diffs collapse to flex-col on mobile and sm:flex-row on tablet/desktop', () => {
      const mockDiff = {
        from_version: 1,
        to_version: 2,
        fields_changed: [
          {
            key: 'monthly_income',
            label: 'Net Monthly Income',
            from_status: 'BLOCKED' as const,
            to_status: 'SATISFIED' as const,
            display_value: '₹85,000',
            cascaded: true,
          },
        ],
        actions_unlocked: ['SET_LOAN_TENURE'],
        actions_removed: ['UPLOAD_INCOME_PROOF'],
        readiness: { from: 'NOT_READY' as const, to: 'NOT_READY' as const },
        progress: {
          from: { completed: 3, pending: 2, blockers: 2, total: 7 },
          to: { completed: 4, pending: 2, blockers: 1, total: 7 },
        },
      };

      render(<JourneyDiff diff={mockDiff} variant="preview" />);

      const fieldDiff = screen.getByTestId('diff-field-monthly_income');
      expect(fieldDiff).toBeInTheDocument();
      expect(fieldDiff.className).toContain('flex-col');
      expect(fieldDiff.className).toContain('sm:flex-row');
      expect(screen.getByTestId('cascaded-badge-monthly_income')).toBeInTheDocument();
    });

    it('Screen 7 AI Analysis footer CTAs stack full-width on mobile and inline on tablet/desktop', async () => {
      const mockEvidence = {
        evidence_id: 'ev-test-1',
        filename: 'salary.pdf',
        uploaded_at: new Date().toISOString(),
        interpretation: {
          verified: true,
          confidence: 0.95,
          detected: [{ key: 'monthly_income', label: 'Monthly Income', display_value: '₹85,000' }],
          summary: 'Verified salary slip.',
          conflicts: [],
        },
        consequence_preview: {
          newly_satisfied: [{ key: 'monthly_income', label: 'Monthly Income' }],
          newly_unlocked: [],
          still_blocked: [],
          predicted_readiness: 'NOT_READY' as const,
          progress_before: { completed: 3, pending: 2, blockers: 2, total: 7 },
          progress_after: { completed: 4, pending: 2, blockers: 1, total: 7 },
        },
        diff_preview: {
          from_version: 1,
          to_version: 2,
          fields_changed: [],
          actions_unlocked: [],
          actions_removed: [],
          readiness: {},
          progress: {},
        },
        requires_review: false,
      };

      const { container } = render(
        <QueryClientProvider client={createTestQueryClient()}>
          <MemoryRouter
            initialEntries={[
              {
                pathname: '/j/11111111-1111-1111-1111-111111111111/analysis',
                state: {
                  evidenceResponse: mockEvidence,
                  journeyId: '11111111-1111-1111-1111-111111111111',
                  snapshotId: '11111111-1111-1111-1111-111111111111',
                },
              },
            ]}
          >
            <Routes>
              <Route path="/j/:id/analysis" element={<Screen07AiAnalysis />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      );

      await screen.findByTestId('screen-07-ai-analysis');

      const footer = container.querySelector('.flex-col.sm\\:flex-row');
      expect(footer).toBeInTheDocument();

      const continueBtn = screen.getByTestId('continue-apply-btn');
      expect(continueBtn.className).toContain('w-full');
      expect(continueBtn.className).toContain('sm:w-auto');
    });
  });

  describe('4. Modals and Responsive Viewport Constraints', () => {
    it('Modal constrains width and handles max-height with scrolling on small screens', () => {
      render(
        <Modal
          isOpen={true}
          onClose={vi.fn()}
          title="Responsive Modal Test"
          description="Ensuring max-height and scrolling"
          size="md"
        >
          <div data-testid="modal-inner-content">Modal Content Body</div>
        </Modal>
      );

      const dialog = screen.getByRole('dialog');
      expect(dialog).toBeInTheDocument();
      expect(dialog.className).toContain('max-w-lg');
      expect(dialog.className).toContain('w-full');

      const scrollableBody = dialog.querySelector('.max-h-\\[75vh\\]');
      expect(scrollableBody).toBeInTheDocument();
      expect(scrollableBody?.className).toContain('overflow-y-auto');
    });
  });
});
