import type React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/primitives/Button';
import { Card } from '@/components/primitives/Card';
import { Compass, Sparkles, Shield, FileText, CheckCircle2, BarChart3 } from 'lucide-react';

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
            <span className="text-paytm-blue">Back on Track.</span>
          </h1>

          <p className="text-base sm:text-lg text-content-secondary max-w-lg leading-relaxed">
            Resolve application blockers, complete your journey, and move forward with confidence — all in one place.
          </p>

          <div className="pt-2">
            <Button
              variant="primary"
              size="lg"
              onClick={() => navigate('/start')}
              className="h-12 px-8 py-3.5 text-base font-semibold shadow-md inline-flex items-center gap-2"
              aria-label="Start Your Journey →"
            >
              <span>Start Your Journey →</span>
            </Button>
          </div>
        </div>

        {/* Hero Illustration Area */}
        <div
          data-testid="hero-illustration"
          role="img"
          aria-label="Financial journey recovery hero illustration"
          className="relative flex items-center justify-center min-h-[320px] sm:min-h-[380px] lg:min-h-[420px] select-none"
        >
          <span className="sr-only">Hero Illustration Area</span>
          {/* Soft background wave / gradient blob */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="w-[280px] sm:w-[360px] h-[280px] sm:h-[360px] rounded-full bg-gradient-to-tr from-sky-100 via-blue-50 to-cyan-50 opacity-90 blur-xl" />
          </div>

          {/* Floating Financial Icons */}
          <div className="absolute top-6 left-4 sm:left-12 z-20 p-2.5 sm:p-3 rounded-2xl bg-white shadow-card border border-slate-100 flex items-center justify-center animate-bounce-subtle">
            <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-blue-50 text-paytm-blue flex items-center justify-center">
              <FileText className="w-5 h-5 sm:w-6 sm:h-6" />
            </div>
          </div>

          <div
            className="absolute bottom-16 left-2 sm:left-8 z-20 p-2.5 sm:p-3 rounded-2xl bg-white shadow-card border border-slate-100 flex items-center justify-center animate-bounce-subtle"
            style={{ animationDelay: '0.4s' }}
          >
            <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-emerald-50 text-paytm-green flex items-center justify-center">
              <Shield className="w-5 h-5 sm:w-6 sm:h-6" />
            </div>
          </div>

          <div
            className="absolute top-8 right-4 sm:right-12 z-20 p-2.5 sm:p-3 rounded-2xl bg-white shadow-card border border-slate-100 flex items-center justify-center animate-bounce-subtle"
            style={{ animationDelay: '0.2s' }}
          >
            <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-blue-50 text-paytm-blue flex items-center justify-center">
              <BarChart3 className="w-5 h-5 sm:w-6 sm:h-6" />
            </div>
          </div>

          <div
            className="absolute bottom-20 right-2 sm:right-10 z-20 p-2.5 sm:p-3 rounded-2xl bg-white shadow-card border border-slate-100 flex items-center justify-center animate-bounce-subtle"
            style={{ animationDelay: '0.6s' }}
          >
            <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-emerald-50 text-paytm-green flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5 sm:w-6 sm:h-6" />
            </div>
          </div>

          {/* Character Illustration */}
          <svg
            viewBox="0 0 360 380"
            className="w-full max-w-[320px] sm:max-w-[360px] h-auto z-10 relative drop-shadow-sm"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            {/* Wavy bottom ground/curve */}
            <path
              d="M20 340C90 320 180 360 270 330C310 316 340 330 360 340V380H0V350C6 346 14 341 20 340Z"
              fill="#E0F2FE"
            />
            {/* Body / Blue Shirt */}
            <path
              d="M110 380V270C110 245 130 225 155 225H205C230 225 250 245 250 270V380H110Z"
              fill="#005BF5"
            />
            {/* Collar & Neck */}
            <path d="M165 225V205H195V225H165Z" fill="#FBD5B5" />
            <path d="M155 225L180 250L205 225H155Z" fill="#0047CC" />

            {/* Head / Face */}
            <ellipse cx="180" cy="165" rx="36" ry="42" fill="#FBD5B5" />
            {/* Hair */}
            <path
              d="M144 165C144 125 155 115 180 115C205 115 216 125 216 165C216 145 210 135 180 135C150 135 144 145 144 165Z"
              fill="#1E293B"
            />
            <path
              d="M142 160C140 140 150 120 180 120C210 120 220 140 218 160C216 148 208 132 180 132C152 132 144 148 142 160Z"
              fill="#0F172A"
            />
            {/* Eyebrows, Eyes, Smile */}
            <path d="M162 155C166 153 170 153 174 155" stroke="#1E293B" strokeWidth="2.5" strokeLinecap="round" />
            <path d="M186 155C190 153 194 153 198 155" stroke="#1E293B" strokeWidth="2.5" strokeLinecap="round" />
            <circle cx="168" cy="164" r="3" fill="#1E293B" />
            <circle cx="192" cy="164" r="3" fill="#1E293B" />
            <path d="M174 180C177 184 183 184 186 180" stroke="#E11D48" strokeWidth="2.5" strokeLinecap="round" />

            {/* Arm & Hand holding Smartphone */}
            <path d="M125 280L135 240L145 270L135 310Z" fill="#005BF5" />
            <rect x="130" y="220" width="28" height="48" rx="6" fill="#0F172A" />
            <rect x="133" y="224" width="22" height="40" rx="3" fill="#38BDF8" />
            {/* Hand fingers */}
            <path d="M126 240C126 235 130 232 135 235L138 255C134 258 126 250 126 240Z" fill="#FBD5B5" />
          </svg>
        </div>
      </div>

      {/* 3 Feature Cards in a Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="p-6 bg-white border border-surface-border shadow-xs hover:shadow-card transition-all text-left flex flex-col items-start gap-3 rounded-card">
          <div className="w-12 h-12 rounded-full bg-blue-50 text-paytm-blue flex items-center justify-center">
            <Compass className="w-6 h-6" />
          </div>
          <div>
            <h2 className="font-bold text-base text-content-primary">Guided next steps</h2>
            <p className="text-xs text-content-secondary mt-1">Know exactly what to do next.</p>
          </div>
        </Card>

        <Card className="p-6 bg-white border border-surface-border shadow-xs hover:shadow-card transition-all text-left flex flex-col items-start gap-3 rounded-card">
          <div className="w-12 h-12 rounded-full bg-blue-50 text-paytm-blue flex items-center justify-center">
            <Sparkles className="w-6 h-6" />
          </div>
          <div>
            <h2 className="font-bold text-base text-content-primary">AI-powered insights</h2>
            <p className="text-xs text-content-secondary mt-1">Get personalized guidance.</p>
          </div>
        </Card>

        <Card className="p-6 bg-white border border-surface-border shadow-xs hover:shadow-card transition-all text-left flex flex-col items-start gap-3 rounded-card">
          <div className="w-12 h-12 rounded-full bg-blue-50 text-paytm-blue flex items-center justify-center">
            <Shield className="w-6 h-6" />
          </div>
          <div>
            <h2 className="font-bold text-base text-content-primary">Secure & private</h2>
            <p className="text-xs text-content-secondary mt-1">Your data stays safe.</p>
          </div>
        </Card>
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
