import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { ConnectionExperience } from './ConnectionExperience';

describe('ConnectionExperience', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the intro wordmark, tagline, and an accessible connecting status', () => {
    render(<ConnectionExperience slow={false} />);

    expect(screen.getByText('PaytmFlow')).toBeInTheDocument();
    expect(screen.getByText("Let's get things moving.")).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Connecting to PaytmFlow.');
  });

  it('never renders a fake percentage or progress number', () => {
    render(<ConnectionExperience slow={false} />);
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it('never exposes infrastructure/technical wording', () => {
    render(<ConnectionExperience slow />);
    const bannedTerms = [/backend/i, /server/i, /database/i, /render\.com/i, /api error/i];
    for (const term of bannedTerms) {
      expect(screen.queryByText(term)).not.toBeInTheDocument();
    }
  });

  it('switches to the long-wait status announcement once slow is true', () => {
    render(<ConnectionExperience slow />);
    expect(screen.getByRole('status')).toHaveTextContent('Still connecting to PaytmFlow.');
  });
});

// Below the smallest timer this component schedules on its exit path, so a
// single advanceTimersByTimeAsync() call can't jump past a timeout that
// gets registered mid-jump (same reasoning as BootGate.test.tsx).
const ADVANCE_STEP_MS = 200;

async function advance(ms: number): Promise<void> {
  let remaining = ms;
  while (remaining > 0) {
    const step = Math.min(ADVANCE_STEP_MS, remaining);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(step);
    });
    remaining -= step;
  }
}

describe('ConnectionExperience — smooth backend-ready exit', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('exits almost immediately when the backend is already ready before the story begins (fast/warm connection)', async () => {
    const onReadyToExit = vi.fn();
    render(<ConnectionExperience slow={false} backendReady onReadyToExit={onReadyToExit} />);

    await advance(300);
    expect(onReadyToExit).toHaveBeenCalledTimes(1);
  });

  it('never exits while the backend has not signalled ready, no matter how long the story plays', async () => {
    const onReadyToExit = vi.fn();
    render(<ConnectionExperience slow backendReady={false} onReadyToExit={onReadyToExit} />);

    await advance(30_000);
    expect(onReadyToExit).not.toHaveBeenCalled();
  });

  it('lets the current chapter finish before exiting when the backend becomes ready mid-story, without waiting for the rest of the story', async () => {
    const onReadyToExit = vi.fn();
    const { rerender } = render(<ConnectionExperience slow backendReady={false} onReadyToExit={onReadyToExit} />);

    // 9s in: past the "assemble" chapter's start (8s) but still inside its
    // own entrance choreography — the "current transition" is still playing.
    await advance(9_000);
    rerender(<ConnectionExperience slow backendReady onReadyToExit={onReadyToExit} />);

    // Not an abrupt cut: exit must not fire the instant readiness arrives.
    await advance(200);
    expect(onReadyToExit).not.toHaveBeenCalled();

    // But it must fire well before the rest of the story would have played
    // out (the next chapter alone starts 14s later, and the full story
    // continues for well over a minute after that).
    await advance(3_000);
    expect(onReadyToExit).toHaveBeenCalledTimes(1);
  });

  it('navigates cleanly with a single exit when readiness arrives exactly at a chapter boundary', async () => {
    const onReadyToExit = vi.fn();
    const { rerender } = render(<ConnectionExperience slow backendReady={false} onReadyToExit={onReadyToExit} />);

    await advance(22_000); // exactly the "documents" chapter's start boundary
    rerender(<ConnectionExperience slow backendReady onReadyToExit={onReadyToExit} />);

    await advance(5_000);
    expect(onReadyToExit).toHaveBeenCalledTimes(1);
  });

  it('only ever exits once, even if backendReady is re-signalled or the component re-renders repeatedly', async () => {
    const onReadyToExit = vi.fn();
    const { rerender } = render(<ConnectionExperience slow backendReady onReadyToExit={onReadyToExit} />);

    for (let i = 0; i < 5; i += 1) {
      rerender(<ConnectionExperience slow backendReady onReadyToExit={onReadyToExit} />);
    }
    await advance(3_000);

    expect(onReadyToExit).toHaveBeenCalledTimes(1);
  });
});
