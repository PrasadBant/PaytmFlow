import type React from 'react';
import { ShieldAlert, User, FileText, Cpu, AlertTriangle } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import type { ReviewCaseDetail } from '@/api/hooks/useReview';

interface WhySeeingCaseProps {
  detail: ReviewCaseDetail;
}

export const WhySeeingCase: React.FC<WhySeeingCaseProps> = ({ detail }) => {
  // Find declared customer value for this field in journey context
  const contextField = detail.journey_context?.fields?.find(
    (f) => f.key === detail.field_key
  );
  const customerDeclaredValue = contextField?.display_value || contextField?.value != null ? String(contextField?.display_value ?? contextField?.value) : 'Not specified';

  // Find extracted values from evidence
  const evidenceValues = detail.evidence
    .flatMap((e) => Object.entries(e.extracted_values ?? {}))
    .filter(([k]) => k === detail.field_key || k.includes('income') || k.includes('salary') || k.includes('amount'))
    .map(([k, v]) => `${k.replace(/_/g, ' ')}: ₹${typeof v === 'number' ? v.toLocaleString('en-IN') : String(v)}`);

  const evidenceSummary = evidenceValues.length > 0 ? evidenceValues.join(', ') : 'Evidence unverified or pending extraction';

  return (
    <Card
      padding="lg"
      className="bg-amber-50/40 border border-amber-200/80 shadow-xs space-y-4"
      data-testid="why-seeing-case"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center shrink-0">
            <ShieldAlert className="w-4 h-4 text-amber-700" />
          </div>
          <div>
            <h2 className="text-base font-extrabold text-content-primary tracking-tight">
              Why Am I Seeing This Case?
            </h2>
            <p className="text-xs text-content-secondary font-medium">
              Automation could not confidently resolve this case
            </p>
          </div>
        </div>

        <span className="text-[11px] font-bold text-amber-900 bg-amber-100 px-2.5 py-1 rounded-full border border-amber-300/60 uppercase tracking-wide">
          {detail.reason_code.replace(/_/g, ' ')}
        </span>
      </div>

      <div className="bg-white p-3.5 rounded-button border border-amber-200/70 text-sm text-content-primary font-medium leading-relaxed shadow-xs">
        <p>{detail.reason_description}</p>
      </div>

      {/* 3-Column Comparative Breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
        {/* Pillar 1: Customer Declared */}
        <div className="p-3 bg-white rounded-button border border-surface-border space-y-1.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-xs font-bold text-content-secondary uppercase tracking-wider">
            <User className="w-3.5 h-3.5 text-paytm-blue-action" />
            <span>Customer Declared</span>
          </div>
          <p className="text-sm font-extrabold text-content-primary">
            {customerDeclaredValue}
          </p>
          <p className="text-[11px] text-content-tertiary">
            Declared for {contextField?.label || detail.field_key}
          </p>
        </div>

        {/* Pillar 2: Submitted Evidence */}
        <div className="p-3 bg-white rounded-button border border-surface-border space-y-1.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-xs font-bold text-content-secondary uppercase tracking-wider">
            <FileText className="w-3.5 h-3.5 text-indigo-600" />
            <span>Evidence Indicates</span>
          </div>
          <p className="text-sm font-extrabold text-content-primary">
            {evidenceSummary}
          </p>
          <p className="text-[11px] text-content-tertiary">
            From {detail.evidence.length} submitted document{detail.evidence.length === 1 ? '' : 's'}
          </p>
        </div>

        {/* Pillar 3: System Assessment */}
        <div className="p-3 bg-white rounded-button border border-surface-border space-y-1.5 shadow-xs">
          <div className="flex items-center gap-1.5 text-xs font-bold text-content-secondary uppercase tracking-wider">
            <Cpu className="w-3.5 h-3.5 text-amber-600" />
            <span>System Assessment</span>
          </div>
          <div className="flex items-center gap-1 text-xs font-bold text-amber-800">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
            <span className="truncate">{detail.reason_title}</span>
          </div>
          <p className="text-[11px] text-content-tertiary">
            Stopped for human exception resolution
          </p>
        </div>
      </div>
    </Card>
  );
};

export default WhySeeingCase;
