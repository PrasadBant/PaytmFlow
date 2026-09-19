import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AssistantModal } from './AssistantModal';
import { useUiStore } from '@/state/ui';
import { resetMockState } from '@/mocks/handlers';

const LENDING_JOURNEY_ID = '11111111-1111-1111-1111-111111111111';

function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function renderAssistant(initialEntry: string) {
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <AssistantModal />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

class MockMediaRecorder {
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(_stream: MediaStream) {}
  start(): void {
    this.ondataavailable?.({ data: new Blob(['fake-audio']) });
  }
  stop(): void {
    this.onstop?.();
  }
}

describe('AssistantModal - voice input (Sarvam speech-to-text)', () => {
  beforeEach(() => {
    resetMockState();
    Element.prototype.scrollIntoView = vi.fn();
    useUiStore.getState().openAssistant();
    vi.stubGlobal('MediaRecorder', MockMediaRecorder as unknown as typeof MediaRecorder);
    const fakeStream = { getTracks: () => [{ stop: vi.fn() }] } as unknown as MediaStream;
    Object.defineProperty(navigator, 'mediaDevices', {
      value: { getUserMedia: vi.fn().mockResolvedValue(fakeStream) },
      configurable: true,
    });
  });

  it('does not render the mic button when there is no active journey', () => {
    renderAssistant('/');
    expect(screen.queryByTestId('voice-record-btn')).not.toBeInTheDocument();
  });

  it('renders the mic button on a journey screen, records, and shows transcript + reply', async () => {
    const user = userEvent.setup();
    renderAssistant(`/j/${LENDING_JOURNEY_ID}`);

    const micButton = await screen.findByTestId('voice-record-btn');
    expect(micButton).toHaveAttribute('aria-pressed', 'false');

    await user.click(micButton);
    await waitFor(() => expect(micButton).toHaveAttribute('aria-pressed', 'true'));

    await act(async () => {
      await user.click(micButton);
    });

    await waitFor(() => {
      expect(screen.getByText(/\(Mock transcript\) What do I need to do next\?/i)).toBeInTheDocument();
    });
    expect(
      screen.getByText(/\(Mock mode\) I heard your question/i)
    ).toBeInTheDocument();
  });
});

describe('AssistantModal - reply translation (Sarvam Mayura)', () => {
  beforeEach(() => {
    resetMockState();
    Element.prototype.scrollIntoView = vi.fn();
    useUiStore.getState().openAssistant();
  });

  it('sends English replies through unchanged by default', async () => {
    const user = userEvent.setup();
    renderAssistant('/');

    const textbox = await screen.findByLabelText('Assistant question');
    await user.type(textbox, 'What documents are accepted?');
    await user.click(screen.getByRole('button', { name: 'Send message' }));

    await waitFor(() => {
      expect(screen.getByText(/\(Mock mode\) I received/i)).toBeInTheDocument();
    });
  });

  it('translates the reply when a non-English language is selected', async () => {
    const user = userEvent.setup();
    renderAssistant('/');

    await user.selectOptions(screen.getByTestId('assistant-language-select'), 'hi-IN');

    const textbox = await screen.findByLabelText('Assistant question');
    await user.type(textbox, 'What documents are accepted?');
    await user.click(screen.getByRole('button', { name: 'Send message' }));

    await waitFor(() => {
      expect(screen.getByText(/^\[hi-IN\] \(Mock mode\) I received/i)).toBeInTheDocument();
    });
  });
});
