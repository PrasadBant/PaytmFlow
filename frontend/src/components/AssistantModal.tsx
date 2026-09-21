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
  Mic,
  Square,
} from 'lucide-react';
import { Modal } from '@/components/primitives/Modal';
import { IconButton } from '@/components/primitives/IconButton';
import { useUiStore } from '@/state/ui';
import { useJourney } from '@/api/hooks/useJourney';
import type { JourneyStateResponse } from '@/api/hooks/useJourney';
import { useChat, useGeneralChat, useVoiceChat } from '@/api/hooks/useChat';
import { useTranslateText } from '@/api/hooks/useTranslate';

interface Message {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  time: string;
}

const MAX_MESSAGE_LENGTH = 500;
const LENGTH_WARNING_THRESHOLD = 400;

// Customer-facing language options (spec: multilingual support scoped to
// the customer experience, never internal identifiers). "English" sends
// nothing through /translate at all - it is the language replies already
// arrive in.
const LANGUAGE_OPTIONS: { code: string; label: string }[] = [
  { code: 'en-IN', label: 'English' },
  { code: 'hi-IN', label: 'Hindi' },
  { code: 'kn-IN', label: 'Kannada' },
  { code: 'ta-IN', label: 'Tamil' },
  { code: 'te-IN', label: 'Telugu' },
  { code: 'ml-IN', label: 'Malayalam' },
  { code: 'mr-IN', label: 'Marathi' },
  { code: 'bn-IN', label: 'Bengali' },
];

// Generic quick actions shown before a journey exists, or while journey
// data is still loading — the same defaults as before.
const GENERIC_SUGGESTED_QUESTIONS: { text: string; icon: ReactNode }[] = [
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

// `pending_clarification` is only ever present when readiness is already
// NEEDS_REVIEW (handled separately below), so for the general "something is
// blocking me" case the real signal is a BLOCKED field with an explanation
// — the same thing the deterministic chat fallback (MockAI) already keys
// off server-side.
function findBlockedField(
  journeyData: JourneyStateResponse
): JourneyStateResponse['fields'][number] | undefined {
  return journeyData.fields.find((f) => f.status === 'BLOCKED' && f.explanation);
}

// Both the opening message and the quick-action suggestions are driven by
// the SAME real journey state already fetched for the screen (readiness,
// pending_clarification) — never a generic "how can I help" greeting when
// the application already knows exactly what the user is doing.
function welcomeMessageFor(
  journeyData: JourneyStateResponse | undefined,
  journeyContext: string | null
): string {
  const title = journeyData?.display?.title;
  const titlePhrase = title ? ` "${title}"` : '';

  if (journeyData?.readiness === 'READY') {
    return `Your${titlePhrase} application is ready. Want me to explain what happens next?`;
  }
  if (journeyData?.readiness === 'NEEDS_REVIEW') {
    return `Your${titlePhrase} application needs a review. I can explain what caused it and what you can do next.`;
  }
  const blockedField = journeyData ? findBlockedField(journeyData) : undefined;
  if (blockedField) {
    return `I can see you're working on your${titlePhrase} application. Right now it's waiting on ${blockedField.label}. Ask me why, or what to do next.`;
  }
  if (title) {
    return `Hello! I'm here to help with your "${title}" application. Ask me about your next step, required documents, or progress.`;
  }
  if (journeyContext) {
    return `Hello! Ask me anything about your ${journeyContext} application.`;
  }
  return "Hello! I'm your PaytmFlow assistant. Ask me anything about filling out an application, or start one and I can guide you step by step.";
}

function suggestedQuestionsFor(
  journeyData: JourneyStateResponse | undefined
): { text: string; icon: ReactNode }[] {
  if (!journeyData) return GENERIC_SUGGESTED_QUESTIONS;

  if (journeyData.readiness === 'READY') {
    return [
      { text: 'Am I ready?', icon: <Check className="w-3 h-3" /> },
      { text: "What's next?", icon: <Sparkles className="w-3 h-3" /> },
    ];
  }
  if (journeyData.readiness === 'NEEDS_REVIEW') {
    return [
      { text: 'Why is this under review?', icon: <HelpCircle className="w-3 h-3" /> },
      { text: 'What do I need to fix?', icon: <FileCheck2 className="w-3 h-3" /> },
      { text: 'What can I do now?', icon: <Sparkles className="w-3 h-3" /> },
    ];
  }
  if (journeyData.readiness === 'DEAD_END') {
    return [
      { text: 'Why am I stuck?', icon: <HelpCircle className="w-3 h-3" /> },
      { text: 'What are my options?', icon: <PieChart className="w-3 h-3" /> },
    ];
  }
  if (findBlockedField(journeyData)) {
    return [
      { text: 'Why am I stuck?', icon: <HelpCircle className="w-3 h-3" /> },
      { text: 'What is missing?', icon: <FileCheck2 className="w-3 h-3" /> },
      { text: 'What should I do?', icon: <Sparkles className="w-3 h-3" /> },
    ];
  }
  return [
    { text: "What's my next step?", icon: <Sparkles className="w-3 h-3" /> },
    { text: 'What documents are accepted?', icon: <FileCheck2 className="w-3 h-3" /> },
    { text: 'How much have I completed?', icon: <PieChart className="w-3 h-3" /> },
  ];
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
  const voiceChatMutation = useVoiceChat();
  const translateMutation = useTranslateText();

  const welcomeText = welcomeMessageFor(journeyData, journeyContext);
  const suggestedQuestions = suggestedQuestionsFor(journeyData);

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([
    { id: 'welcome', sender: 'assistant', text: welcomeText, time: timeNow() },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastFailedQuestion, setLastFailedQuestion] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [replyLanguage, setReplyLanguage] = useState(LANGUAGE_OPTIONS[0].code);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Voice is only meaningful once a journey exists (the backend endpoint is
  // journey-scoped so it can ground the reply in real journey state) and
  // only where the browser actually supports recording - never shown as a
  // dead button.
  const supportsVoice =
    !!journeyId &&
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== 'undefined';

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

  // Translation (spec: multilingual customer experience) is applied ONLY to
  // an already-generated reply string, never to amounts/statuses/display
  // values elsewhere in the app - and is best-effort: a translation failure
  // falls back to the original English text rather than blocking the reply.
  const translateReply = async (reply: string): Promise<string> => {
    if (replyLanguage === LANGUAGE_OPTIONS[0].code) return reply;
    try {
      const result = await translateMutation.mutateAsync({
        text: reply,
        targetLanguageCode: replyLanguage,
      });
      return result.translated_text;
    } catch {
      return reply;
    }
  };

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
      const displayReply = await translateReply(reply);

      setMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, sender: 'assistant', text: displayReply, time: timeNow() },
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

  const handleVoiceStop = async (): Promise<void> => {
    if (!journeyId || audioChunksRef.current.length === 0) return;
    const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
    setIsLoading(true);
    setError(null);
    try {
      // Transcript and reply come back from ONE grounded backend call - the
      // transcript is shown as the user's own message (so they can confirm
      // they were heard correctly), the reply exactly like a typed answer.
      const result = await voiceChatMutation.mutateAsync({ journeyId, audioBlob });
      const displayReply = await translateReply(result.reply);
      setMessages((prev) => [
        ...prev,
        { id: `u-${Date.now()}`, sender: 'user', text: result.transcript, time: timeNow() },
        { id: `a-${Date.now() + 1}`, sender: 'assistant', text: displayReply, time: timeNow() },
      ]);
    } catch {
      setVoiceError('Could not process that recording. Please try typing your question instead.');
    } finally {
      setIsLoading(false);
    }
  };

  const startRecording = async (): Promise<void> => {
    if (!journeyId) return;
    setVoiceError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      audioChunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        void handleVoiceStop();
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setIsRecording(true);
    } catch {
      setVoiceError('Microphone access was denied or is unavailable.');
    }
  };

  const stopRecording = (): void => {
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
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
        journeyData?.display?.title
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
          <div className="flex items-center gap-2">
            <label htmlFor="assistant-reply-language" className="sr-only">
              Reply language
            </label>
            <select
              id="assistant-reply-language"
              value={replyLanguage}
              onChange={(e) => setReplyLanguage(e.target.value)}
              data-testid="assistant-language-select"
              className="text-[11px] font-semibold text-content-secondary bg-surface border border-surface-border rounded-md px-1.5 py-1 focus-visible:ring-2 focus-visible:ring-paytm-cyan focus-visible:outline-none"
            >
              {LANGUAGE_OPTIONS.map((opt) => (
                <option key={opt.code} value={opt.code}>
                  {opt.label}
                </option>
              ))}
            </select>
            <IconButton
              icon={<RotateCcw className="w-3.5 h-3.5" />}
              aria-label="Restart conversation"
              variant="ghost"
              size="sm"
              onClick={handleResetChat}
              disabled={isLoading || messages.length <= 1}
            />
          </div>
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

          {voiceError && (
            <div
              className="flex items-center gap-1.5 p-2.5 rounded bg-paytm-red-light border border-paytm-red/20 text-xs text-paytm-red animate-chat-msg-in"
              data-testid="voice-error"
            >
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              {voiceError}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Suggested questions */}
        {messages.length <= 1 && (
          <div className="mt-3 flex flex-wrap gap-1.5" data-testid="assistant-suggestions">
            {suggestedQuestions.map((suggestion) => (
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
          {supportsVoice && (
            <button
              type="button"
              onClick={() => (isRecording ? stopRecording() : void startRecording())}
              disabled={isLoading}
              aria-label={isRecording ? 'Stop recording' : 'Ask by voice'}
              aria-pressed={isRecording}
              data-testid="voice-record-btn"
              className={`w-10 h-10 shrink-0 rounded-full flex items-center justify-center shadow-sm transition-all duration-150 active:scale-95 disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-paytm-cyan focus-visible:outline-none ${
                isRecording
                  ? 'bg-paytm-red text-white animate-pulse'
                  : 'bg-white text-paytm-blue border border-paytm-blue/20 hover:bg-paytm-blue/5'
              }`}
            >
              {isRecording ? <Square className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
            </button>
          )}
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
