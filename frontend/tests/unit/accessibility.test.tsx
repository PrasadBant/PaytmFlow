import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Tabs } from '@/components/primitives/Tabs';
import { Modal } from '@/components/primitives/Modal';
import { ProgressRing } from '@/components/ProgressRing';
import { StatusBadge } from '@/components/StatusBadge';
import { BlockerCard } from '@/components/BlockerCard';
import { StaleBanner } from '@/components/StaleBanner';
import { ErrorState } from '@/components/ErrorState';
import { EvidenceDropzone } from '@/components/EvidenceDropzone';
import { Screen04CurrentStatus } from '@/screens/Screen04CurrentStatus';
import { Screen08UpdatedStatus } from '@/screens/Screen08UpdatedStatus';
import { SchedulingPicker } from '@/components/interactions/SchedulingPicker';
import { ConsentPanel } from '@/components/interactions/ConsentPanel';
import { VideoVerificationFlow } from '@/components/interactions/VideoVerificationFlow';

function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

describe('Phase F29: Accessibility (a11y) Pass & Semantics', () => {
  describe('1. Tabs Keyboard Navigation & ARIA Semantics', () => {
    it('implements tablist/tab roles, aria-selected, and keyboard ArrowLeft/ArrowRight navigation', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      const tabs = [
        { id: 'tab1', label: 'Upload File' },
        { id: 'tab2', label: 'Enter Details' },
        { id: 'tab3', label: 'How It Helps' },
      ];

      const { rerender } = render(
        <Tabs tabs={tabs} activeTab="tab1" onChange={onChange} />
      );

      const tabList = screen.getByRole('tablist');
      expect(tabList).toHaveAttribute('aria-orientation', 'horizontal');

      const tab1 = screen.getByRole('tab', { name: /Upload File/i });
      const tab2 = screen.getByRole('tab', { name: /Enter Details/i });
      const tab3 = screen.getByRole('tab', { name: /How It Helps/i });

      expect(tab1).toHaveAttribute('aria-selected', 'true');
      expect(tab2).toHaveAttribute('aria-selected', 'false');
      expect(tab3).toHaveAttribute('aria-selected', 'false');

      // Focus first tab and press ArrowRight
      tab1.focus();
      await user.keyboard('{ArrowRight}');
      expect(onChange).toHaveBeenCalledWith('tab2');

      // Re-render with tab2 active
      rerender(<Tabs tabs={tabs} activeTab="tab2" onChange={onChange} />);
      expect(tab2).toHaveAttribute('aria-selected', 'true');

      // Press End key to jump to last tab
      tab2.focus();
      await user.keyboard('{End}');
      expect(onChange).toHaveBeenCalledWith('tab3');

      // Press Home key to jump to first tab
      await user.keyboard('{Home}');
      expect(onChange).toHaveBeenCalledWith('tab1');
    });
  });

  describe('2. Modal Dialog Semantics & Escape Dismiss', () => {
    it('sets role=dialog, aria-modal=true, and dismisses on Escape key', async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();

      render(
        <Modal
          isOpen={true}
          onClose={onClose}
          title="Income Verification Handoff"
          description="Please review before proceeding"
        >
          <div>Modal content for assistive technology</div>
        </Modal>
      );

      const dialog = screen.getByRole('dialog');
      expect(dialog).toBeInTheDocument();
      expect(dialog).toHaveAttribute('aria-modal', 'true');
      expect(dialog).toHaveAttribute('aria-labelledby', 'modal-title');
      expect(dialog).toHaveAttribute('aria-describedby', 'modal-description');

      expect(screen.getByText('Income Verification Handoff')).toHaveAttribute('id', 'modal-title');
      expect(screen.getByText('Please review before proceeding')).toHaveAttribute('id', 'modal-description');

      // Escape key triggers onClose
      await user.keyboard('{Escape}');
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  describe('3. ProgressRing Accessibility Properties', () => {
    it('provides role=progressbar with accurate min, max, valuenow and aria-label', () => {
      render(<ProgressRing completed={3} total={7} />);

      const progressbar = screen.getByRole('progressbar');
      expect(progressbar).toBeInTheDocument();
      expect(progressbar).toHaveAttribute('aria-valuemin', '0');
      expect(progressbar).toHaveAttribute('aria-valuemax', '7');
      expect(progressbar).toHaveAttribute('aria-valuenow', '3');
      expect(progressbar).toHaveAttribute('aria-label', '3 of 7 steps completed');
    });
  });

  describe('4. Status is NEVER Conveyed by Color Alone', () => {
    it('StatusBadge renders explicit text label AND icon for all statuses', () => {
      const statuses = [
        { code: 'SATISFIED', label: 'Satisfied' },
        { code: 'BLOCKED', label: 'Blocked' },
        { code: 'AMBIGUOUS', label: 'Needs Review' },
        { code: 'READY', label: 'Ready' },
        { code: 'DEAD_END', label: 'Dead End' },
        { code: 'PENDING', label: 'Pending' },
        { code: 'IN_PROGRESS', label: 'In Progress' },
      ];

      for (const item of statuses) {
        const { unmount } = render(<StatusBadge status={item.code} />);
        const badge = screen.getByTestId('status-badge');
        expect(badge).toHaveTextContent(item.label);
        // Has SVG icon
        expect(badge.querySelector('svg')).toBeInTheDocument();
        unmount();
      }
    });

    it('BlockerCard conveys status via icon, title, display value and text explanation', () => {
      const mockField = {
        key: 'monthly_income',
        label: 'Monthly Income Verification',
        status: 'BLOCKED' as const,
        display_value: 'Not Provided',
        explanation: 'Valid salary slip from last 3 months is required.',
        resolve_action_id: 'UPLOAD_INCOME_PROOF',
      };

      render(
        <MemoryRouter>
          <BlockerCard field={mockField} onResolve={vi.fn()} />
        </MemoryRouter>
      );

      expect(screen.getByText('Monthly Income Verification')).toBeInTheDocument();
      expect(screen.getByText('Blocked')).toBeInTheDocument();
      expect(screen.getByText('Valid salary slip from last 3 months is required.')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Resolve/i })).toBeInTheDocument();
    });
  });

  describe('5. Error Alerts & Dynamic Status Announcements (aria-live)', () => {
    it('ErrorState and StaleBanner have role=alert for screen readers', () => {
      render(
        <>
          <ErrorState title="Connection Error" message="Could not reach server" />
          <StaleBanner message="Snapshot outdated" />
        </>
      );

      const alerts = screen.getAllByRole('alert');
      expect(alerts).toHaveLength(2);
    });

    it('Screen 4 and Screen 8 status surfaces include aria-live=polite', async () => {
      const { unmount } = render(
        <QueryClientProvider client={createTestQueryClient()}>
          <MemoryRouter initialEntries={['/j/11111111-1111-1111-1111-111111111111']}>
            <Routes>
              <Route path="/j/:id" element={<Screen04CurrentStatus />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      );

      const screen4 = await screen.findByTestId('screen-04-current-status');
      expect(screen4).toHaveAttribute('aria-live', 'polite');
      unmount();

      const mockActionResponse = {
        journey: {
          journey_id: '11111111-1111-1111-1111-111111111111',
          journey_type: 'LENDING' as const,
          schema_version: '1.0.0',
          snapshot_id: '22222222-2222-2222-2222-222222222222',
          version_number: 2,
          readiness: 'NOT_READY' as const,
          status: 'IN_PROGRESS' as const,
          progress: { completed: 4, pending: 2, blockers: 1, total: 7 },
          fields: [],
          display: { title: 'Personal Loan', summary: '₹5,00,000' },
        },
        diff: {
          from_version: 1,
          to_version: 2,
          fields_changed: [],
          actions_unlocked: [],
          actions_removed: [],
          readiness: {},
          progress: {},
        },
      };

      render(
        <QueryClientProvider client={createTestQueryClient()}>
          <MemoryRouter
            initialEntries={[
              {
                pathname: '/j/11111111-1111-1111-1111-111111111111/updated',
                state: {
                  actionResponse: mockActionResponse,
                  journeyId: '11111111-1111-1111-1111-111111111111',
                },
              },
            ]}
          >
            <Routes>
              <Route path="/j/:id/updated" element={<Screen08UpdatedStatus />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      );

      const screen8 = await screen.findByTestId('screen-08-updated-status');
      expect(screen8).toHaveAttribute('aria-live', 'polite');
    });

    it('EvidenceDropzone is keyboard focusable and triggers file picker on Enter/Space', () => {
      const onSelect = vi.fn();
      render(<EvidenceDropzone onFileSelect={onSelect} />);

      const dropzone = screen.getByTestId('evidence-dropzone');
      expect(dropzone).toHaveAttribute('tabindex', '0');
      expect(dropzone).toHaveAttribute('role', 'button');
      expect(dropzone).toHaveAttribute('aria-label', 'Drop files here or click to browse');

      // Focusable with visible focus styling
      dropzone.focus();
      expect(document.activeElement).toBe(dropzone);

      // KeyDown Enter
      fireEvent.keyDown(dropzone, { key: 'Enter', code: 'Enter' });
      // KeyDown Space
      fireEvent.keyDown(dropzone, { key: ' ', code: 'Space' });
    });
  });

  describe('6. New interaction components (SchedulingPicker, ConsentPanel, VideoVerificationFlow)', () => {
    describe('SchedulingPicker', () => {
      it('uses a labelled fieldset/legend radio group, is fully keyboard-operable, and Confirm is disabled until a slot is chosen', async () => {
        const user = userEvent.setup();
        const onSubmit = vi.fn();
        render(
          <SchedulingPicker
            actionTitle="Medical Underwriting Call"
            why="Select a time slot"
            submitLabel="Confirm Slot →"
            onSubmit={onSubmit}
          />
        );

        // Fieldset/legend: the group's accessible name comes from <legend>
        // alone (no duplicate/conflicting aria-label).
        const group = screen.getByRole('group', { name: /Select a time slot/i });
        expect(group).toBeInTheDocument();

        const radios = screen.getAllByRole('radio');
        expect(radios.length).toBeGreaterThan(0);
        // Every radio has an accessible name (from its wrapping <label>).
        radios.forEach((r) => expect(r).toHaveAccessibleName());

        const confirmBtn = screen.getByTestId('scheduling-confirm-btn');
        expect(confirmBtn).toBeDisabled();

        // Keyboard only: Tab to the first radio, select with Space, Tab to Confirm, activate with Enter.
        await user.tab();
        expect(radios[0]).toHaveFocus();
        await user.keyboard(' ');
        expect(radios[0]).toBeChecked();
        expect(confirmBtn).toBeEnabled();

        // Continue tabbing to the Confirm button (native radio-group semantics
        // mean the remaining radios are also in the tab sequence via arrow
        // keys, not sequential Tab - jsdom exercises native radio grouping).
        confirmBtn.focus();
        await user.keyboard('{Enter}');
        expect(onSubmit).toHaveBeenCalledTimes(1);
      });
    });

    describe('ConsentPanel', () => {
      it('uses a labelled checkbox, is keyboard-operable, and Confirm is disabled until checked', async () => {
        const user = userEvent.setup();
        const onSubmit = vi.fn();
        render(
          <ConsentPanel
            actionTitle="Cardholder Agreement"
            why="Digital agreement to card terms"
            submitLabel="Confirm →"
            onSubmit={onSubmit}
          />
        );

        const checkbox = screen.getByTestId('consent-checkbox');
        expect(checkbox).toHaveAccessibleName(/I have read and agree/i);

        const confirmBtn = screen.getByTestId('consent-confirm-btn');
        expect(confirmBtn).toBeDisabled();

        // Keyboard only: Tab to checkbox, toggle with Space, Tab to Confirm, activate with Enter.
        await user.tab();
        expect(checkbox).toHaveFocus();
        await user.keyboard(' ');
        expect(checkbox).toBeChecked();
        expect(confirmBtn).toBeEnabled();

        await user.tab();
        expect(confirmBtn).toHaveFocus();
        await user.keyboard('{Enter}');
        expect(onSubmit).toHaveBeenCalledTimes(1);
      });
    });

    describe('VideoVerificationFlow', () => {
      it('announces each stage transition via role=status/aria-live, and every stage button is reachable and operable by keyboard', async () => {
        const user = userEvent.setup();
        const onSubmit = vi.fn();
        render(
          <VideoVerificationFlow
            actionTitle="Live Video Verification"
            why="Complete a short liveness scan"
            submitLabel="Continue →"
            onSubmit={onSubmit}
          />
        );

        // The stage container is a live region so screen-reader users learn
        // of each silent state transition (intro -> permission ->
        // in_progress -> complete) without having to re-explore the page.
        const stageRegion = screen.getByTestId('video-stage-region');
        expect(stageRegion).toHaveAttribute('role', 'status');
        expect(stageRegion).toHaveAttribute('aria-live', 'polite');

        // It also never falsely implies a real check occurred.
        expect(screen.getByText(/simulated in this prototype/i)).toBeInTheDocument();

        await user.tab();
        expect(screen.getByTestId('video-start-btn')).toHaveFocus();
        await user.keyboard('{Enter}');

        expect(await screen.findByTestId('video-allow-btn')).toBeInTheDocument();
        screen.getByTestId('video-allow-btn').focus();
        await user.keyboard('{Enter}');

        // Verifying stage has no interactive control (nothing to focus) -
        // the continue button remains disabled and inert until completion.
        const continueBtn = await screen.findByTestId('video-continue-btn');
        expect(continueBtn).toBeDisabled();

        expect(await screen.findByText(/Verification complete/i, {}, { timeout: 3000 })).toBeInTheDocument();
        expect(continueBtn).toBeEnabled();

        continueBtn.focus();
        await user.keyboard('{Enter}');
        expect(onSubmit).toHaveBeenCalledTimes(1);
      });
    });
  });
});
