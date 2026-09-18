import type React from 'react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search,
  ChevronDown,
  Rocket,
  FileText,
  ShieldCheck,
  ClipboardList,
  Lock,
  HelpCircle as HelpCircleIcon,
} from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Input } from '@/components/primitives/Input';
import { Button } from '@/components/primitives/Button';
import { cn } from '@/lib/utils';
import { useUiStore } from '@/state/ui';

interface HelpCategory {
  key: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const categories: HelpCategory[] = [
  { key: 'getting-started', label: 'Getting Started', icon: Rocket },
  { key: 'my-journeys', label: 'My Journeys', icon: FileText },
  { key: 'documents-verification', label: 'Documents & Verification', icon: ShieldCheck },
  { key: 'forms-information', label: 'Forms & Information', icon: ClipboardList },
  { key: 'account-security', label: 'Account & Security', icon: Lock },
  { key: 'common-questions', label: 'Common Questions', icon: HelpCircleIcon },
];

interface FaqItem {
  id: string;
  category: string;
  question: string;
  answer: string;
}

const faqItems: FaqItem[] = [
  {
    id: 'faq-start-journey',
    category: 'getting-started',
    question: 'How do I start a new journey?',
    answer:
      'Go to "Start Journey" from the sidebar, pick the journey type that matches what you need (like a personal loan or account opening), and tell us your goal. We\'ll show you exactly what\'s needed next.',
  },
  {
    id: 'faq-resume-journey',
    category: 'my-journeys',
    question: 'Can I resume a journey I started earlier?',
    answer:
      'Yes. Open "My Journeys" from the sidebar to see every journey you\'ve started, its current progress, and pick up exactly where you left off.',
  },
  {
    id: 'faq-upload-document',
    category: 'documents-verification',
    question: 'What happens after I upload a document?',
    answer:
      'Your document is reviewed automatically. If everything checks out with high confidence, the related requirement is marked complete right away. If anything needs a closer look, it\'s flagged for manual review before it\'s applied — we\'ll always tell you which case applies.',
  },
  {
    id: 'faq-wrong-document',
    category: 'documents-verification',
    question: 'I uploaded the wrong document. What now?',
    answer:
      'No problem — we\'ll let you know the document doesn\'t match what was requested, and you can upload the correct one right away. Nothing is applied to your journey until a document is genuinely verified.',
  },
  {
    id: 'faq-form-fields',
    category: 'forms-information',
    question: 'Why do some steps ask me to fill a form instead of uploading a document?',
    answer:
      'Some requirements — like confirming your employment type or accepting terms — are direct declarations rather than something a document proves. Those steps use a short form instead of an upload.',
  },
  {
    id: 'faq-account-security',
    category: 'account-security',
    question: 'Is my uploaded information secure?',
    answer:
      'Your documents and data are processed to verify the specific requirements of your journey only. We never store more than what your journey needs, and your session is tied to your device — no one else can view your journeys.',
  },
  {
    id: 'faq-review-needed',
    category: 'common-questions',
    question: 'What does "Review Needed" mean?',
    answer:
      'It means we found real information in what you provided, but it didn\'t clear the bar for automatic confirmation. It will be checked manually — the value you provided isn\'t being rejected, it just isn\'t applied automatically yet.',
  },
  {
    id: 'faq-progress',
    category: 'common-questions',
    question: 'How is my progress calculated?',
    answer:
      'Progress reflects exactly how many requirements for your journey are complete versus outstanding. It updates in real time as you complete each step — there\'s nothing hidden or estimated about it.',
  },
];

export const HelpScreen: React.FC = () => {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  const filteredFaqs = useMemo(() => {
    const q = query.trim().toLowerCase();
    return faqItems.filter((item) => {
      const matchesCategory = !activeCategory || item.category === activeCategory;
      const matchesQuery =
        !q || item.question.toLowerCase().includes(q) || item.answer.toLowerCase().includes(q);
      return matchesCategory && matchesQuery;
    });
  }, [query, activeCategory]);

  return (
    <div data-testid="screen-help" className="w-full max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 md:py-12 space-y-10">
      {/* Header */}
      <div className="text-center space-y-3">
        <h1 className="text-3xl sm:text-4xl font-extrabold text-content-primary tracking-tight">
          How can we help?
        </h1>
        <p className="text-sm sm:text-base text-content-secondary max-w-xl mx-auto">
          Find answers about your journeys, documents, verification, and account.
        </p>
      </div>

      {/* Search */}
      <div className="max-w-lg mx-auto">
        <Input
          type="search"
          placeholder="Search for help"
          aria-label="Search for help"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          leftIcon={<Search className="w-4 h-4" aria-hidden="true" />}
        />
      </div>

      {/* Categories */}
      <div
        role="group"
        aria-label="Help categories"
        className="grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4"
      >
        {categories.map((cat) => {
          const isActive = activeCategory === cat.key;
          return (
            <button
              key={cat.key}
              type="button"
              data-testid={`help-category-${cat.key}`}
              aria-pressed={isActive}
              onClick={() => setActiveCategory(isActive ? null : cat.key)}
              className={cn(
                'flex flex-col items-center justify-center gap-2 rounded-card border p-4 text-center transition-colors',
                isActive
                  ? 'border-paytm-blue-action bg-paytm-blue-50 text-paytm-blue-action'
                  : 'border-surface-border bg-surface text-content-secondary hover:bg-surface-hover hover:text-content-primary'
              )}
            >
              <cat.icon className="w-5 h-5" aria-hidden="true" />
              <span className="text-xs sm:text-sm font-semibold">{cat.label}</span>
            </button>
          );
        })}
      </div>

      {/* FAQ Accordion */}
      <div className="space-y-2" data-testid="help-faq-list">
        {filteredFaqs.length === 0 ? (
          <p className="text-sm text-content-secondary text-center py-8">
            No help topics match your search.
          </p>
        ) : (
          filteredFaqs.map((item) => {
            const isOpen = openId === item.id;
            return (
              <Card key={item.id} padding="none" className="overflow-hidden">
                <button
                  type="button"
                  data-testid={`faq-trigger-${item.id}`}
                  aria-expanded={isOpen}
                  aria-controls={`${item.id}-panel`}
                  onClick={() => setOpenId(isOpen ? null : item.id)}
                  className="w-full flex items-center justify-between gap-3 px-4 py-3.5 text-left"
                >
                  <span className="text-sm font-semibold text-content-primary">{item.question}</span>
                  <ChevronDown
                    className={cn(
                      'w-4 h-4 shrink-0 text-content-tertiary transition-transform',
                      isOpen && 'rotate-180'
                    )}
                    aria-hidden="true"
                  />
                </button>
                {isOpen && (
                  <div
                    id={`${item.id}-panel`}
                    role="region"
                    aria-labelledby={`faq-trigger-${item.id}`}
                    className="px-4 pb-4 text-sm text-content-secondary leading-relaxed"
                  >
                    {item.answer}
                  </div>
                )}
              </Card>
            );
          })
        )}
      </div>

      {/* Still need help */}
      <Card className="text-center space-y-4 bg-surface-subtle">
        <h2 className="text-base font-bold text-content-primary">Still need help?</h2>
        <p className="text-xs text-content-secondary max-w-sm mx-auto">
          Have a question about your documents, requirements, or next steps? Our assistant is ready to help.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <Button
            variant="primary"
            onClick={() => useUiStore.getState().openAssistant()}
            data-testid="help-ask-assistant-btn"
          >
            Ask AI Assistant
          </Button>
          <Button variant="secondary" onClick={() => navigate('/my-journeys')}>
            View My Journeys
          </Button>
          <Button variant="outline" onClick={() => navigate('/')}>
            Back to Home
          </Button>
        </div>
      </Card>
    </div>
  );
};

export default HelpScreen;
