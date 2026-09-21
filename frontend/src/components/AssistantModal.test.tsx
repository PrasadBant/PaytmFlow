import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import { AssistantModal } from './AssistantModal';
import { useUiStore } from '@/state/ui';
import { resetMockState } from '@/mocks/handlers';
import type { JourneyStateResponse } from '@/api/hooks/useJourney';

const LENDING_JOURNEY_ID = '11111111-1111-1111-1111-111111111111';

// A minimal, valid JourneyStateResponse for overriding the GET journey
// endpoint per test — only the fields the Journey Copilot's context logic
// actually reads are varied; everything else is realistic filler.
function makeJourneyState(overrides: Partial<JourneyStateResponse>): JourneyStateResponse {
  return {
    journey_id: LENDING_JOURNEY_ID,
    journey_type: 'LENDING',
    schema_version: '1.0.0',
    snapshot_id: '22222222-2222-2222-2222-222222222222',
    version_number: 1,
    readiness: 'NOT_READY',
    status: 'IN_PROGRESS',
    fields: [],
    progress: { total: 5, completed: 2, pending: 2, blockers: 1 },
    display: { title: 'Personal Loan', summary: '₹5,00,000 · Home Renovation' },
    ...overrides,
  } as JourneyStateResponse;
}

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

describe('AssistantModal - Journey Copilot context awareness', () => {
  beforeEach(() => {
    resetMockState();
    Element.prototype.scrollIntoView = vi.fn();
    useUiStore.getState().openAssistant();
  });

  it('greets with a READY-specific message and only READY-relevant quick actions', async () => {
    server.use(
      http.get('*/api/v1/journeys/:journey_id', () =>
        HttpResponse.json(makeJourneyState({ readiness: 'READY' }))
      )
    );

    renderAssistant(`/j/${LENDING_JOURNEY_ID}`);

    await waitFor(() => {
      expect(screen.getByText(/is ready\. Want me to explain what happens next\?/i)).toBeInTheDocument();
    });
    const suggestions = screen.getByTestId('assistant-suggestions');
    expect(suggestions).toHaveTextContent('Am I ready?');
    expect(suggestions).toHaveTextContent("What's next?");
    expect(suggestions).not.toHaveTextContent('Why is this under review?');
  });

  it('greets with a NEEDS_REVIEW-specific message and review-relevant quick actions', async () => {
    server.use(
      http.get('*/api/v1/journeys/:journey_id', () =>
        HttpResponse.json(makeJourneyState({ readiness: 'NEEDS_REVIEW' }))
      )
    );

    renderAssistant(`/j/${LENDING_JOURNEY_ID}`);

    await waitFor(() => {
      expect(screen.getByText(/needs a review\. I can explain what caused it/i)).toBeInTheDocument();
    });
    const suggestions = screen.getByTestId('assistant-suggestions');
    expect(suggestions).toHaveTextContent('Why is this under review?');
    expect(suggestions).toHaveTextContent('What do I need to fix?');
  });

  it('greets naming the actual blocked field and offers "why am I stuck" quick actions', async () => {
    server.use(
      http.get('*/api/v1/journeys/:journey_id', () =>
        HttpResponse.json(
          makeJourneyState({
            readiness: 'NOT_READY',
            fields: [
              {
                key: 'income_proof',
                label: 'Income proof',
                status: 'BLOCKED',
                explanation: 'Income proof is missing.',
              },
            ],
          })
        )
      )
    );

    renderAssistant(`/j/${LENDING_JOURNEY_ID}`);

    await waitFor(() => {
      expect(screen.getByText(/waiting on Income proof/i)).toBeInTheDocument();
    });
    const suggestions = screen.getByTestId('assistant-suggestions');
    expect(suggestions).toHaveTextContent('Why am I stuck?');
    expect(suggestions).toHaveTextContent('What is missing?');
  });
});

describe('AssistantModal - boot safety (lazy, no chat calls while closed)', () => {
  beforeEach(() => {
    resetMockState();
    useUiStore.getState().closeAssistant();
  });

  it('renders nothing and makes no chat or journey requests while the assistant has never been opened', async () => {
    let chatCalled = false;
    server.use(
      http.post('*/api/v1/chat', () => {
        chatCalled = true;
        return HttpResponse.json({ reply: 'unexpected' });
      }),
      http.post('*/api/v1/journeys/:journey_id/chat', () => {
        chatCalled = true;
        return HttpResponse.json({ reply: 'unexpected' });
      })
    );

    const { container } = renderAssistant(`/j/${LENDING_JOURNEY_ID}`);

    // Give any accidental on-mount effect a real chance to fire before
    // asserting it didn't.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(container).toBeEmptyDOMElement();
    expect(chatCalled).toBe(false);
  });
});
