import type React from 'react';
import { AlertCircle, Eye, HelpCircle, UploadCloud, CheckCircle2 } from 'lucide-react';
import type { ReviewCaseStatus } from '@/api/hooks/useReview';

interface CustomerHandoffLoopProps {
  status: ReviewCaseStatus;
}

interface Step {
  id: string;
  label: string;
  icon: React.FC<{ className?: string }>;
  isCurrent: boolean;
  isPast: boolean;
}

export const CustomerHandoffLoop: React.FC<CustomerHandoffLoopProps> = ({ status }) => {
  const steps: Step[] = [
    {
      id: 'flagged',
      label: 'Exception Flagged',
      icon: AlertCircle,
      isCurrent: status === 'REVIEW_REQUIRED',
      isPast: status !== 'REVIEW_REQUIRED',
    },
    {
      id: 'investigating',
      label: 'Reviewer Investigation',
      icon: Eye,
      isCurrent: status === 'UNDER_REVIEW',
      isPast: ['ADDITIONAL_INFO_REQUIRED', 'RESOLVED', 'ESCALATED'].includes(status),
    },
    {
      id: 'info_requested',
      label: 'Info Requested / Waiting',
      icon: HelpCircle,
      isCurrent: status === 'ADDITIONAL_INFO_REQUIRED',
      isPast: ['RESOLVED'].includes(status),
    },
    {
      id: 'customer_response',
      label: 'Customer Evidence',
      icon: UploadCloud,
      isCurrent: false,
      isPast: ['RESOLVED'].includes(status),
    },
    {
      id: 'resolved',
      label: 'Resolution & Recovery',
      icon: CheckCircle2,
      isCurrent: status === 'RESOLVED',
      isPast: false,
    },
  ];

  return (
    <div className="bg-white border border-surface-border rounded-card p-3 shadow-2xs">
      <div className="flex items-center justify-between gap-1 overflow-x-auto select-none hide-scrollbar text-xs">
        {steps.map((step, idx) => {
          const Icon = step.icon;

          return (
            <div key={step.id} className="flex items-center gap-1.5 shrink-0 px-2 py-1">
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 text-xs font-bold transition-all ${
                  step.isCurrent
                    ? 'bg-paytm-blue-action text-white ring-2 ring-blue-100'
                    : step.isPast
                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    : 'bg-slate-100 text-content-tertiary'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
              </div>
              <span
                className={`font-semibold whitespace-nowrap text-[11px] ${
                  step.isCurrent
                    ? 'text-paytm-blue-action font-bold'
                    : step.isPast
                    ? 'text-content-primary'
                    : 'text-content-tertiary'
                }`}
              >
                {step.label}
              </span>
              {idx < steps.length - 1 && (
                <span className="text-slate-300 ml-1.5 select-none font-bold">&rarr;</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default CustomerHandoffLoop;
