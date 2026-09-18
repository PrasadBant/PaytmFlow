import { useState, useRef, useEffect, type ReactElement, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Bot,
  Send,
  User,
  Sparkles,
  FileCheck2,
  HelpCircle,
  PieChart,
  RotateCcw,
  Check,
  Copy,
  AlertCircle,
} from 'lucide-react';
import { Modal } from '@/components/primitives/Modal';
import { IconButton } from '@/components/primitives/IconButton';
import { useUiStore } from '@/state/ui';
import { useJourney } from '@/api/hooks/useJourney';
import { useChat, useGeneralChat } from '@/api/hooks/useChat';

interface Message {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  time: string;
}

const MAX_MESSAGE_LENGTH = 500;
const LENGTH_WARNING_THRESHOLD = 400;

const SUGGESTED_QUESTIONS: { text: string; icon: ReactNode }[] = [
  { text: "What's my next step?", icon: <Sparkles className="w-3 h-3" /> },
  { text: 'What documents are accepted?', icon: <FileCheck2 className="w-3 h-3" /> },
  { text: 'Why is this blocked?', icon: <HelpCircle className="w-3 h-3" /> },
  { text: 'How much have I completed?', icon: <PieChart className="w-3 h-3" /> },
];

function timeNow(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function extractJourneyId(pathname: string): string | undefined {
  const match = /^\/j\/([^/]+)/.exec(pathname);
  return match?.[1];
}

function welcomeMessageFor(journeyTitle: string | undefined, journeyContext: string | null): string {
  if (journeyTitle) {
    return `Hello! I'm here to help with your "${journeyTitle}" application. Ask me about your next step, required documents, or progress.`;
  }
  if (journeyContext) {
    return `Hello! Ask me anything about your ${journeyContext} application.`;
  }
  return "Hello! I'm your PaytmFlow assistant. Ask me anything about filling out an application, or start one and I can guide you step by step.";
}

export function AssistantModal(): ReactElement | null {
  const isOpen = useUiStore((state) => state.isAssistantOpen);
  const closeAssistant = useUiStore((state) => state.closeAssistant);
  const journeyContext = useUiStore((state) => state.assistantJourneyContext);

  const location = useLocation();
  const journeyId = extractJourneyId(location.pathname);
  const { data: journeyData } = useJourney(journeyId);
  const chatMutation = useChat();
  const generalChatMutation = useGeneralChat();

  const welcomeText = welcomeMessageFor(journeyData?.display.title, journeyContext);

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    { id: 'welcome', sender: 'assistant', text: welcomeText, time: timeNow() },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFailedQuestion, setLastFailedQuestion] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  // This component never unmounts (it just renders null while closed), so
  // the welcome text - which depends on which journey/screen the assistant
  // was opened from - must be refreshed on every fresh open, not just once
  // at first mount. Only replaces an untouched welcome-only conversation;
  // never wipes a conversation the user already started.
  useEffect(() => {
    if (isOpen) {
      setMessages((prev) =>
        prev.length <= 1
          ? [{ id: 'welcome', sender: 'assistant', text: welcomeText, time: timeNow() }]
          : prev
      );
    }
  }, [isOpen, welcomeText]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  if (!isOpen) return null;

  const performRequest = async (question: string): Promise<void> => {
    setIsLoading(true);
    setError(null);

    try {
      // Always a real backend call, never a client-side canned reply. On a
      // journey screen it re-derives the grounded context (journey state +
      // recommendation) server-side and routes through the AI provider
      // (real LLM / local ML, per AI_PROVIDER) - never trusting anything
      // the client sends about its own application status. Before a
      // journey exists (e.g. the goal-creation form) it falls to the
      // general, ungrounded chat endpoint - still the real model, just
      // with no application data to ground on yet.
      const reply = journeyId
        ? (await chatMutation.mutateAsync({ journeyId, message: question })).reply
        : (await generalChatMutation.mutateAsync(question)).reply;

      setMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, sender: 'assistant', text: reply, time: timeNow() },
      ]);
      setLastFailedQuestion(null);
    } catch {
      setError('Failed to receive a response.');
      setLastFailedQuestion(question);
    } finally {
      setIsLoading(false);
    }
  };

  const sendQuestion = async (question: string): Promise<void> => {
    if (!question || isLoading) return;

    setMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, sender: 'user', text: question, time: timeNow() },
    ]);
    setInput('');
    if (inputRef.current) inputRef.current.style.height = 'auto';
    await performRequest(question);
  };

  const handleSend = (): void => {
    void sendQuestion(input.trim());
  };

  const handleRetry = (): void => {
    if (lastFailedQuestion) void performRequest(lastFailedQuestion);
  };

  const handleResetChat = (): void => {
    setMessages([{ id: 'welcome', sender: 'assistant', text: welcomeText, time: timeNow() }]);
    setError(null);
    setLastFailedQuestion(null);
    inputRef.current?.focus();
  };

  const handleCopy = (msg: Message): void => {
    void navigator.clipboard
      ?.writeText(msg.text)
      .then(() => {
        setCopiedId(msg.id);
        setTimeout(() => setCopiedId((current) => (current === msg.id ? null : current)), 1500);
      })
      .catch(() => {});
  };

  const remainingChars = MAX_MESSAGE_LENGTH - input.length;

  return (
    <Modal
      isOpen={isOpen}
      onClose={closeAssistant}
      title="PaytmFlow Assistant"
      description={
        journeyData
          ? `Guiding your "${journeyData.display.title}" application`
          : journeyContext
            ? `Guiding your ${journeyContext} journey`
            : 'Ask any question about your application'
      }
      size="lg"
    >
      <div className="flex flex-col h-[540px]" data-testid="assistant-modal">
        {/* Status strip */}
        <div className="flex items-center justify-between pb-3 mb-1 border-b border-surface-border">
          <div className="flex items-center gap-2.5">
            <div className="relative">
              <div className="w-9 h-9 rounded-full bg-gradient-to-br from-paytm-blue to-paytm-blue-700 flex items-center justify-center shadow-sm">
                <Bot className="w-5 h-5 text-white" />
              </div>
              <span
                className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-paytm-green border-2 border-white"
                aria-hidden="true"
              />
            </div>
            <div>
              <p className="text-sm font-bold text-content-primary leading-tight">PaytmFlow AI</p>
              <p className="text-[11px] text-paytm-green-dark font-medium leading-tight">
                {journeyId ? 'Online · Grounded in your live status' : 'Online · Ready to help'}
              </p>
            </div>
          </div>
          <IconButton
            icon={<RotateCcw className="w-3.5 h-3.5" />}
            aria-label="Restart conversation"
            variant="ghost"
            size="sm"
            onClick={handleResetChat}
            disabled={isLoading || messages.length <= 1}
          />
        </div>

        {/* Messages List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-3 bg-surface-subtle rounded-card border border-surface-border">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex items-start gap-2.5 animate-chat-msg-in ${
                msg.sender === 'user' ? 'flex-row-reverse' : ''
              }`}
            >
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs font-bold ${
                  msg.sender === 'user'
                    ? 'bg-gradient-to-br from-paytm-blue to-paytm-blue-700 text-white'
                    : 'bg-white text-paytm-blue border border-paytm-blue/20'
                }`}
              >
                {msg.sender === 'user' ? <User className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
              </div>
              <div className={`max-w-[80%] flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
                <div
                  className={`rounded-card p-3 text-xs leading-relaxed whitespace-pre-wrap ${
                    msg.sender === 'user'
                      ? 'bg-gradient-to-br from-paytm-blue to-paytm-blue-700 text-white rounded-tr-none shadow-sm'
                      : 'bg-white text-content-primary border border-surface-border shadow-xs rounded-tl-none'
                  }`}
                >
                  {msg.text}
                </div>
                <div className="mt-1 flex items-center gap-2 px-1">
                  <span className="text-[10px] text-content-tertiary">{msg.time}</span>
                  {msg.sender === 'assistant' && msg.id !== 'welcome' && (
                    <button
                      type="button"
                      onClick={() => handleCopy(msg)}
                      aria-label="Copy reply"
                      className="text-content-tertiary hover:text-paytm-blue transition-colors"
                    >
                      {copiedId === msg.id ? (
                        <span className="flex items-center gap-1 text-[10px] text-paytm-green-dark">
                          <Check className="w-3 h-3" /> Copied
                        </span>
                      ) : (
                        <Copy className="w-3 h-3" />
                      )}
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex items-start gap-2.5 animate-chat-msg-in">
              <div className="w-7 h-7 rounded-full bg-white text-paytm-blue border border-paytm-blue/20 flex items-center justify-center shrink-0">
                <Bot className="w-3.5 h-3.5" />
              </div>
              <div
                className="bg-white p-3 rounded-card border border-surface-border shadow-xs rounded-tl-none flex items-center gap-1"
                aria-label="Assistant is typing"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-paytm-blue animate-typing-dot [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-paytm-blue animate-typing-dot [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-paytm-blue animate-typing-dot [animation-delay:300ms]" />
              </div>
            </div>
          )}

          {error && (
            <div className="flex items-center justify-between gap-3 p-2.5 rounded bg-paytm-red-light border border-paytm-red/20 text-xs text-paytm-red animate-chat-msg-in">
              <span className="flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                {error}
              </span>
              <button
                type="button"
                onClick={handleRetry}
                className="font-semibold underline shrink-0 hover:text-paytm-red-dark"
              >
                Retry
              </button>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Suggested questions */}
        {messages.length <= 1 && (
          <div className="mt-3 flex flex-wrap gap-1.5" data-testid="assistant-suggestions">
            {SUGGESTED_QUESTIONS.map((suggestion) => (
              <button
                key={suggestion.text}
                type="button"
                disabled={isLoading}
                onClick={() => void sendQuestion(suggestion.text)}
                className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-full bg-white border border-paytm-blue/20 text-paytm-blue hover:bg-paytm-blue hover:text-white hover:border-paytm-blue hover:shadow-sm active:scale-95 disabled:opacity-50 disabled:active:scale-100 transition-all duration-150"
              >
                {suggestion.icon}
                {suggestion.text}
              </button>
            ))}
          </div>
        )}

        {/* Input Bar */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="mt-3 flex items-end gap-2"
        >
          <div className="flex-1 relative">
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              maxLength={MAX_MESSAGE_LENGTH}
              onChange={(e) => {
                setInput(e.target.value);
                const el = e.target;
                el.style.height = 'auto';
                el.style.height = `${Math.min(el.scrollHeight, 96)}px`;
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Ask a question about your steps..."
              disabled={isLoading}
              aria-label="Assistant question"
              className="w-full resize-none rounded-card bg-surface border border-surface-border px-4 py-2.5 text-sm text-content-primary placeholder:text-content-tertiary focus-visible:ring-2 focus-visible:ring-paytm-cyan focus-visible:outline-none transition-shadow leading-relaxed"
            />
            {remainingChars <= MAX_MESSAGE_LENGTH - LENGTH_WARNING_THRESHOLD && (
              <span
                className={`absolute bottom-1.5 right-3 text-[10px] ${
                  remainingChars <= 20 ? 'text-paytm-red' : 'text-content-tertiary'
                }`}
              >
                {remainingChars}
              </span>
            )}
          </div>
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            aria-label="Send message"
            className="w-10 h-10 shrink-0 rounded-full bg-gradient-to-br from-paytm-blue to-paytm-blue-700 text-white flex items-center justify-center shadow-sm transition-transform duration-150 hover:scale-105 active:scale-95 disabled:opacity-40 disabled:hover:scale-100 focus-visible:ring-2 focus-visible:ring-paytm-cyan focus-visible:outline-none"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
        <p className="mt-2 text-center text-[10px] text-content-tertiary">
          AI responses may be inaccurate - always verify important details.
        </p>
      </div>
    </Modal>
  );
}

export default AssistantModal;
