import type React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/primitives/Button';
import { Wand2, ShieldCheck, Shield, FileText, CheckCircle2, BarChart3 } from 'lucide-react';
import { useUiStore } from '@/state/ui';

export const Screen01Home: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div data-testid="screen-01-home" className="w-full max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 md:py-12 space-y-12 md:space-y-16">
      {/* 2-Column Hero Section */}
      <div className="grid grid-cols-1 md:grid-cols-2 items-center gap-8 lg:gap-12 pt-4">
        {/* Left Column: Copy & CTA */}
        <div className="space-y-6 text-left">
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-content-primary tracking-tight leading-[1.1]">
            Your Financial <br />
            Journey. <br />
            <span className="text-paytm-blue-action">Back on Track.</span>
          </h1>

          <p className="text-base sm:text-lg text-content-secondary max-w-lg leading-relaxed">
            Resolve application blockers, complete your journey, and move forward with confidence — all in one place.
          </p>

          <div className="pt-2 flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              size="lg"
              onClick={() => navigate('/start')}
              className="h-12 px-8 py-3.5 text-base font-semibold shadow-md inline-flex items-center gap-2"
              aria-label="Start Your Journey →"
            >
              <span>Start Your Journey →</span>
            </Button>
            <Button
              variant="secondary"
              size="lg"
              onClick={() => useUiStore.getState().openAssistant()}
              className="h-12 px-6 py-3.5 text-base font-semibold inline-flex items-center gap-2"
              aria-label="Ask AI Assistant"
              data-testid="home-ask-ai-btn"
            >
              <Wand2 className="w-4 h-4 text-paytm-blue" />
              <span>Ask AI Assistant</span>
            </Button>
          </div>
        </div>

        {/* Hero Illustration Area */}
        <div
          data-testid="hero-illustration"
          role="img"
          aria-label="Financial journey recovery hero illustration"
          className="relative flex items-center justify-center min-h-[320px] sm:min-h-[380px] lg:min-h-[440px] select-none overflow-hidden"
        >
          <span className="sr-only">Hero Illustration Area</span>
          {/* Soft background wave / gradient blob */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="w-[280px] sm:w-[360px] h-[280px] sm:h-[360px] rounded-full bg-gradient-to-tr from-sky-100 via-blue-50 to-cyan-50 opacity-90 blur-xl" />
          </div>

          {/* Floating Financial Icons - white "speech bubble" cards with a small
              pointed tail, matching the reference's badge shape */}
          <div className="absolute top-4 left-4 sm:left-10 z-20 flex flex-col items-center animate-bounce-subtle">
            <div className="p-2.5 sm:p-3 rounded-2xl bg-white shadow-card border border-slate-100 flex items-center justify-center">
              <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-blue-50 text-paytm-blue flex items-center justify-center">
                <FileText className="w-5 h-5 sm:w-6 sm:h-6" />
              </div>
            </div>
            <div className="w-3 h-3 -mt-1.5 rotate-45 bg-white border-r border-b border-slate-100" />
          </div>

          <div
            className="absolute bottom-20 left-2 sm:left-6 z-20 flex flex-col items-center animate-bounce-subtle"
            style={{ animationDelay: '0.4s' }}
          >
            <div className="p-2.5 sm:p-3 rounded-2xl bg-paytm-green shadow-card flex items-center justify-center">
              <ShieldCheck className="w-5 h-5 sm:w-6 sm:h-6 text-white" />
            </div>
          </div>

          <div
            className="absolute top-6 right-2 sm:right-10 z-20 flex flex-col items-center animate-bounce-subtle"
            style={{ animationDelay: '0.2s' }}
          >
            <div className="p-2.5 sm:p-3 rounded-2xl bg-white shadow-card border border-slate-100 flex items-center justify-center">
              <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-blue-50 text-paytm-blue flex items-center justify-center">
                <BarChart3 className="w-5 h-5 sm:w-6 sm:h-6" />
              </div>
            </div>
          </div>

          <div
            className="absolute bottom-24 right-0 sm:right-6 z-20 flex flex-col items-center animate-bounce-subtle"
            style={{ animationDelay: '0.6s' }}
          >
            <div className="p-2.5 sm:p-3 rounded-2xl bg-white shadow-card border border-slate-100 flex items-center justify-center">
              <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-emerald-50 text-paytm-green flex items-center justify-center">
                <CheckCircle2 className="w-5 h-5 sm:w-6 sm:h-6" />
              </div>
            </div>
          </div>

          {/* Character Illustration */}
          <svg
            viewBox="0 0 360 400"
            className="w-full max-w-[340px] sm:max-w-[400px] h-auto z-10 relative"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            {/* Layered wavy ground/curve - two soft bands for depth */}
            <path
              d="M0 355C50 340 110 368 170 358C230 348 260 330 310 340C330 344 345 350 360 356V400H0V355Z"
              fill="#DCEEFC"
            />
            <path
              d="M20 372C90 356 180 388 270 364C305 355 335 362 360 372V400H0V378C6 376 14 373 20 372Z"
              fill="#EAF4FD"
            />

            {/* Body / Blue Sweater - rounded shoulders */}
            <path
              d="M108 400V282C108 250 132 226 163 226H197C228 226 252 250 252 282V400H108Z"
              fill="#005BF5"
            />
            {/* Collar & Neck */}
            <path d="M163 226V202H197V226H163Z" fill="#F4C9A4" />
            <path d="M155 228C163 240 172 247 180 247C188 247 197 240 205 228L197 226H163L155 228Z" fill="#0047CC" />

            {/* Head / Face */}
            <ellipse cx="180" cy="163" rx="38" ry="43" fill="#F4C9A4" />

            {/* Hair - side-swept with a couple of texture strands */}
            <path
              d="M139 168C136 122 154 108 180 108C206 108 224 122 221 168C219 142 212 124 180 124C148 124 141 142 139 168Z"
              fill="#101828"
            />
            <path d="M218 140C222 150 222 160 219 168" stroke="#101828" strokeWidth="3" strokeLinecap="round" />
            <path d="M150 122C160 116 170 113 180 113" stroke="#1E293B" strokeWidth="2" strokeLinecap="round" opacity="0.5" />

            {/* Eyebrows, Eyes, blush, smile */}
            <path d="M160 152C164 149 170 149 175 151" stroke="#101828" strokeWidth="2.5" strokeLinecap="round" />
            <path d="M185 151C190 149 196 149 200 152" stroke="#101828" strokeWidth="2.5" strokeLinecap="round" />
            <circle cx="167" cy="162" r="3" fill="#101828" />
            <circle cx="193" cy="162" r="3" fill="#101828" />
            <circle cx="151" cy="175" r="6" fill="#F4A896" opacity="0.4" />
            <circle cx="209" cy="175" r="6" fill="#F4A896" opacity="0.4" />
            <path d="M172 179C175 184 185 184 188 179" stroke="#C2410C" strokeWidth="2.5" strokeLinecap="round" />

            {/* Arm & Hand holding Smartphone */}
            <path d="M122 288L133 244L146 276L136 320Z" fill="#005BF5" />
            <rect x="128" y="222" width="26" height="50" rx="7" fill="#101828" />
            <rect x="131" y="226" width="20" height="42" rx="3" fill="#1E293B" />
            <circle cx="141" cy="230" r="1.5" fill="#475569" />
            {/* Hand fingers */}
            <path d="M124 246C123 240 128 236 134 239L137 261C132 264 125 256 124 246Z" fill="#F4C9A4" />
          </svg>
        </div>
      </div>

      {/* 3 Feature Columns - plain on the page background with a thin divider
          between columns at desktop width, matching the reference (no boxed
          cards here - the outer page provides all the framing this section needs). */}
      <div className="grid grid-cols-1 md:grid-cols-3 md:divide-x md:divide-surface-border gap-8 md:gap-0">
        <div className="flex flex-col items-center text-center gap-3 md:px-6">
          <div className="w-12 h-12 rounded-full bg-blue-50 text-paytm-blue flex items-center justify-center">
            <Wand2 className="w-6 h-6" />
          </div>
          <div>
            <h2 className="font-bold text-base text-content-primary">Guided next steps</h2>
            <p className="text-xs text-content-secondary mt-1">Know exactly what to do next.</p>
          </div>
        </div>

        <div className="flex flex-col items-center text-center gap-3 md:px-6">
          <div className="w-12 h-12 rounded-full bg-blue-50 text-paytm-blue flex items-center justify-center">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <h2 className="font-bold text-base text-content-primary">AI-powered insights</h2>
            <p className="text-xs text-content-secondary mt-1">Get personalized guidance.</p>
          </div>
        </div>

        <div className="flex flex-col items-center text-center gap-3 md:px-6">
          <div className="w-12 h-12 rounded-full bg-blue-50 text-paytm-blue flex items-center justify-center">
            <Shield className="w-6 h-6" />
          </div>
          <div>
            <h2 className="font-bold text-base text-content-primary">Secure & private</h2>
            <p className="text-xs text-content-secondary mt-1">Your data stays safe.</p>
          </div>
        </div>
      </div>

      {/* Bottom Summary Pill Banner */}
      <div className="text-center pt-2 pb-4">
        <div className="inline-flex items-center px-6 py-2.5 rounded-full bg-paytm-blue-50 border border-paytm-blue/10 text-paytm-blue text-xs sm:text-sm font-semibold tracking-wide shadow-xs">
          <span>One Platform. Six Financial Journeys. Real Progress.</span>
        </div>
      </div>
    </div>
  );
};

export default Screen01Home;
