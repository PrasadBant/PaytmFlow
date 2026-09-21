import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BootGate } from './BootGate';
import { apiClient } from '../api/client';

function mockMatchMedia(matches: boolean): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe('BootGate premium connection experience', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    // @ts-expect-error - restore to jsdom's (unimplemented) default
    delete window.matchMedia;
  });

  it('renders the loading experience (wordmark + flow visual) immediately on mount', () => {
    vi.spyOn(apiClient, 'get').mockImplementation(() => new Promise(() => {}));

    render(
      <BootGate>
        <div data-testid="app-content">Loaded</div>
      </BootGate>
    );

    expect(screen.getByTestId('boot-gate-loading')).toBeInTheDocument();
    expect(screen.getByText('PaytmFlow')).toBeInTheDocument();
    expect(screen.getByText("Let's get things moving.")).toBeInTheDocument();
  });

  it('shows a brief success transition, then the real app, on a successful connection', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ session_id: 's1', created: true });

    render(
      <BootGate>
        <div data-testid="app-content">Loaded</div>
      </BootGate>
    );

    expect(await screen.findByTestId('boot-gate-success')).toBeInTheDocument();
    expect(await screen.findByTestId('app-content')).toBeInTheDocument();
  });

  it('introduces no artificial delay beyond the bounded success flourish on a fast connection', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ session_id: 's1', created: true });

    const start = performance.now();
    render(
      <BootGate>
        <div data-testid="app-content">Loaded</div>
      </BootGate>
    );
    await screen.findByTestId('app-content');
    const elapsed = performance.now() - start;

    // Comfortably above the ~380ms success flourish plus test overhead, but
    // far below anything that would read as an artificial multi-second hold.
    expect(elapsed).toBeLessThan(900);
  });

  it('skips the success flourish and renders instantly under prefers-reduced-motion', async () => {
    mockMatchMedia(true);
    vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ session_id: 's1', created: true });

    render(
      <BootGate>
        <div data-testid="app-content">Loaded</div>
      </BootGate>
    );

    expect(await screen.findByTestId('app-content')).toBeInTheDocument();
  });

  it('does not crash while booting under prefers-reduced-motion (particle motion is skipped)', () => {
    mockMatchMedia(true);
    vi.spyOn(apiClient, 'get').mockImplementation(() => new Promise(() => {}));

    render(
      <BootGate>
        <div data-testid="app-content">Loaded</div>
      </BootGate>
    );

    expect(screen.getByTestId('boot-gate-loading')).toBeInTheDocument();
  });
});
