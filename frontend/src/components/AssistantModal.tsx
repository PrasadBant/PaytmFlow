import { useState, useRef, useEffect, type ReactElement } from 'react';
import { Bot, Send, User } from 'lucide-react';
import { Modal } from '@/components/primitives/Modal';
import { Button } from '@/components/primitives/Button';
import { Spinner } from '@/components/primitives/Spinner';
import { useUiStore } from '@/state/ui';

interface Message {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
}

export function AssistantModal(): ReactElement | null {
  const isOpen = useUiStore((state) => state.isAssistantOpen);
  const closeAssistant = useUiStore((state) => state.closeAssistant);
  const journeyContext = useUiStore((state) => state.assistantJourneyContext);

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      sender: 'assistant',
      text: 'Hello! I am your PaytmFlow assistant. How can I help guide your application today?',
    },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  if (!isOpen) return null;

  const handleSend = async (): Promise<void> => {
    const question = input.trim();
    if (!question || isLoading) return;

    const userMsg: Message = {
      id: `u-${Date.now()}`,
      sender: 'user',
      text: question,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);
    setError(null);

    try {
      // Bounded local guidance generator based on prototype and journey context
      await new Promise((resolve) => setTimeout(resolve, 600));

      let reply =
        'Please proceed with the recommended verification step shown on your status dashboard. Each step helps satisfy prerequisites deterministically.';
      
      const q = question.toLowerCase();
      if (q.includes('document') || q.includes('upload') || q.includes('proof')) {
        reply =
          'Make sure your document is clear, complete, and uncropped. For income proof, recent salary slips or bank statements showing steady deposits are accepted.';
      } else if (q.includes('review') || q.includes('conflict')) {
        reply =
          'When an item shows "Needs Review", a manual verification or a simple clarification question will ensure the data matches accurately.';
      } else if (q.includes('pan') || q.includes('tax')) {
        reply =
          'Ensure your PAN number format is correct (10 characters: 5 letters, 4 numbers, 1 letter). We validate format and identity against official records.';
      } else if (q.includes('liveness') || q.includes('video') || q.includes('photo')) {
        reply =
          'Video and liveness checks verify that the applicant is present in real time. Simply follow the on-screen prompts to complete verification.';
      } else if (journeyContext) {
        reply = `For your current ${journeyContext} application, following the prioritized action list will guide you through all mandatory criteria smoothly.`;
      }

      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          sender: 'assistant',
          text: reply,
        },
      ]);
    } catch {
      setError('Failed to receive response from assistant. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={closeAssistant}
      title="PaytmFlow Assistant"
      description={
        journeyContext
          ? `Guiding your ${journeyContext} journey`
          : 'Ask any question about your application'
      }
      size="md"
    >
      <div className="flex flex-col h-[380px]" data-testid="assistant-modal">
        {/* Messages List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-3 bg-surface-subtle rounded-card border border-surface-border">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex items-start gap-2.5 ${
                msg.sender === 'user' ? 'flex-row-reverse' : ''
              }`}
            >
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs font-bold ${
                  msg.sender === 'user'
                    ? 'bg-paytm-blue text-white'
                    : 'bg-white text-paytm-blue border border-paytm-blue/20'
                }`}
              >
                {msg.sender === 'user' ? <User className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
              </div>
              <div
                className={`max-w-[80%] rounded-card p-3 text-xs leading-relaxed ${
                  msg.sender === 'user'
                    ? 'bg-paytm-blue text-white rounded-tr-none'
                    : 'bg-white text-content-primary border border-surface-border shadow-xs rounded-tl-none'
                }`}
              >
                {msg.text}
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex items-start gap-2.5">
              <div className="w-7 h-7 rounded-full bg-white text-paytm-blue border border-paytm-blue/20 flex items-center justify-center shrink-0">
                <Bot className="w-3.5 h-3.5" />
              </div>
              <div className="bg-white p-3 rounded-card border border-surface-border shadow-xs rounded-tl-none flex items-center gap-2 text-xs text-content-secondary">
                <Spinner size="sm" className="text-paytm-blue" />
                <span>Thinking...</span>
              </div>
            </div>
          )}

          {error && (
            <div className="p-2 rounded bg-paytm-red-light border border-paytm-red/20 text-xs text-paytm-red">
              {error}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void handleSend();
          }}
          className="mt-3 flex items-center gap-2"
        >
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about your steps..."
            disabled={isLoading}
            aria-label="Assistant question"
            className="flex-1 rounded-button bg-surface border border-surface-border px-3.5 py-2 text-sm text-content-primary placeholder:text-content-tertiary focus-visible:ring-2 focus-visible:ring-paytm-cyan focus-visible:outline-none"
          />
          <Button
            type="submit"
            variant="primary"
            disabled={!input.trim() || isLoading}
            className="px-4 py-2"
            aria-label="Send message"
          >
            <Send className="w-4 h-4" />
          </Button>
        </form>
      </div>
    </Modal>
  );
}

export default AssistantModal;
