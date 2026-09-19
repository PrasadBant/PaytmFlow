import type React from 'react';
import { Scale, FileText, CheckCircle2, XCircle, Info, Sparkles, Clock, History } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import type { ReviewCaseDetail } from '@/api/hooks/useReview';
import { formatRelativeTime } from '@/lib/utils';

interface EvidenceComparisonProps {
  detail: ReviewCaseDetail;
}

export const EvidenceComparisonWorkspace: React.FC<EvidenceComparisonProps> = ({ detail }) => {
  const contextField = detail.journey_context?.fields?.find(
    (f) => f.key === detail.field_key
  );

  const evidenceList = detail.evidence ?? [];
  const hasMultipleEvidence = evidenceList.length > 1;

  // Chronologically sorted evidence
  const sortedEvidence = [...evidenceList].sort(
    (a, b) => new Date(a.uploaded_at).getTime() - new Date(b.uploaded_at).getTime()
  );
  const latestEvidence = sortedEvidence[sortedEvidence.length - 1];
  const previousEvidence = sortedEvidence.length > 1 ? sortedEvidence[0] : null;

  return (
    <div className="space-y-4" data-testid="evidence-comparison-workspace">
      {/* Evidence Workspace Header Card */}
      <Card padding="lg" className="bg-white border border-surface-border shadow-xs space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-surface-border pb-4">
          <div className="flex items-center gap-2">
            <Scale className="w-5 h-5 text-paytm-blue-action" />
            <div>
              <h2 className="text-base font-extrabold text-content-primary tracking-tight">
                Evidence & Data Comparison
              </h2>
              <p className="text-xs text-content-secondary">
                Side-by-side evaluation of customer declaration vs verified evidence.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-bold text-content-secondary bg-slate-100 px-2.5 py-1 rounded-full border border-slate-200">
              {evidenceList.length} Document{evidenceList.length === 1 ? '' : 's'} Submitted
            </span>
          </div>
        </div>

        {/* Customer Provided Reference */}
        <div className="bg-blue-50/40 p-4 rounded-card border border-blue-200/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="space-y-0.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-paytm-blue-action">
              Customer Declaration in Application
            </span>
            <p className="text-sm font-bold text-content-primary">
              {contextField?.label || detail.field_key}:{' '}
              <span className="font-extrabold text-paytm-blue">
                {contextField?.display_value || (contextField?.value != null ? String(contextField.value) : 'Not specified')}
              </span>
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs font-semibold text-content-secondary">
            <span>Status:</span>
            <span className="px-2 py-0.5 rounded-full bg-white border border-blue-200 text-[11px] font-bold text-paytm-blue">
              {contextField?.status || 'AMBIGUOUS'}
            </span>
          </div>
        </div>

        {/* Submitted Evidence Cards */}
        <div className="space-y-3">
          <h3 className="text-xs font-bold text-content-tertiary uppercase tracking-wider">
            Submitted Documents & Deterministic Extraction
          </h3>

          <div className="grid sm:grid-cols-2 gap-4">
            {evidenceList.map((e) => {
              const confidencePercent = e.confidence != null ? Math.round(e.confidence * 100) : null;

              return (
                <div
                  key={e.evidence_id}
                  data-testid={`evidence-${e.evidence_id}`}
                  className="p-4 rounded-card border border-surface-border bg-surface-subtle/40 space-y-3 relative hover:border-slate-300 transition-all shadow-xs"
                >
                  {/* Doc Type & Status */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 text-sm font-bold text-content-primary">
                      <FileText className="w-4 h-4 text-paytm-blue" />
                      <span>{e.doc_type.replace(/_/g, ' ')}</span>
                    </div>

                    {e.verified ? (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200/60">
                        <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                        Verified Document
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase text-amber-800 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200/60">
                        <XCircle className="w-3 h-3 text-amber-600" />
                        Unverified
                      </span>
                    )}
                  </div>

                  {/* Extracted Values Grid */}
                  <div className="space-y-2">
                    {e.extracted_values && Object.keys(e.extracted_values).length > 0 ? (
                      Object.entries(e.extracted_values).map(([k, v]) => (
                        <div
                          key={k}
                          className="bg-white p-2.5 border border-surface-border rounded-button flex items-center justify-between gap-2 shadow-2xs"
                        >
                          <span className="text-[11px] font-bold uppercase tracking-wide text-content-secondary">
                            {k.replace(/_/g, ' ')}
                          </span>
                          <span className="text-sm font-extrabold text-content-primary font-mono">
                            {typeof v === 'number' ? `₹${v.toLocaleString('en-IN')}` : String(v)}
                          </span>
                        </div>
                      ))
                    ) : (
                      <div className="bg-white p-3 border border-surface-border rounded-button text-xs text-content-secondary italic text-center">
                        No automated values extracted
                      </div>
                    )}
                  </div>

                  {/* Metadata & AI Confidence */}
                  <div className="pt-2 border-t border-surface-border/70 text-[11px] text-content-tertiary flex flex-col gap-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate max-w-[200px]" title={e.filename}>
                        File: <strong className="text-content-secondary font-mono">{e.filename}</strong>
                      </span>
                      <span className="flex items-center gap-1 shrink-0">
                        <Clock className="w-3 h-3" /> {formatRelativeTime(e.uploaded_at)}
                      </span>
                    </div>

                    {confidencePercent !== null && (
                      <div className="flex items-center justify-between gap-2 pt-0.5">
                        <span className="flex items-center gap-1 text-content-secondary font-semibold">
                          <Sparkles className="w-3 h-3 text-indigo-600" /> AI Extraction Confidence:
                        </span>
                        <span
                          className={`font-bold px-1.5 py-0.2 rounded-sm text-[10px] ${
                            confidencePercent >= 85
                              ? 'bg-emerald-50 text-emerald-700'
                              : confidencePercent >= 70
                              ? 'bg-amber-50 text-amber-800'
                              : 'bg-red-50 text-red-700'
                          }`}
                        >
                          {confidencePercent}% Confidence
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* "What Changed Since Last Review?" Section (Section 17) */}
        {hasMultipleEvidence && previousEvidence && latestEvidence && (
          <div className="p-4 bg-slate-50 rounded-card border border-surface-border space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-content-primary">
              <History className="w-4 h-4 text-paytm-blue-action" />
              <span>What Changed Since Initial Submission?</span>
            </div>

            <div className="grid sm:grid-cols-2 gap-3 text-xs bg-white p-3 rounded-button border border-surface-border">
              <div>
                <p className="text-[10px] font-bold uppercase text-content-tertiary mb-1">
                  Initial Document ({formatRelativeTime(previousEvidence.uploaded_at)})
                </p>
                <p className="font-bold text-content-primary truncate">{previousEvidence.filename}</p>
                <p className="text-content-secondary text-[11px] mt-0.5">
                  Type: {previousEvidence.doc_type.replace(/_/g, ' ')}
                </p>
                {previousEvidence.extracted_values && Object.entries(previousEvidence.extracted_values).map(([k, v]) => (
                  <p key={k} className="text-content-tertiary text-[11px] font-mono mt-0.5">
                    {k}: ₹{typeof v === 'number' ? v.toLocaleString('en-IN') : String(v)}
                  </p>
                ))}
              </div>

              <div className="border-t sm:border-t-0 sm:border-l sm:pl-3 border-surface-border pt-2 sm:pt-0">
                <p className="text-[10px] font-bold uppercase text-paytm-blue-action mb-1">
                  Latest Re-submission ({formatRelativeTime(latestEvidence.uploaded_at)})
                </p>
                <p className="font-bold text-content-primary truncate">{latestEvidence.filename}</p>
                <p className="text-content-secondary text-[11px] mt-0.5">
                  Type: {latestEvidence.doc_type.replace(/_/g, ' ')}
                </p>
                {latestEvidence.extracted_values && Object.entries(latestEvidence.extracted_values).map(([k, v]) => (
                  <p key={k} className="text-emerald-700 font-bold text-[11px] font-mono mt-0.5">
                    {k}: ₹{typeof v === 'number' ? v.toLocaleString('en-IN') : String(v)}
                  </p>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* AI Findings & Advisory Boundary Callout */}
        <div className="bg-indigo-50/50 p-4 rounded-card border border-indigo-100 space-y-2">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-indigo-600" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-950">
              AI Advisory Assistance
            </h3>
          </div>

          <div className="bg-white p-3 rounded-button border border-indigo-100 text-xs text-content-secondary space-y-1">
            <p className="font-semibold text-content-primary">
              Discrepancy identified between declared value and evidence extraction.
            </p>
            <p>
              AI extraction model identified candidate values but flagged potential ambiguity. Reviewer verification is mandatory.
            </p>
          </div>

          <div className="flex items-center gap-1.5 text-[11px] font-semibold text-content-tertiary">
            <Info className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
            <span>AI is strictly advisory. Deterministic journey rules control state transitions and unblock gates.</span>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default EvidenceComparisonWorkspace;
