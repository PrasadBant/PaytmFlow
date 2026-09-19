import type React from 'react';
import { Clock, User, Cpu, Sparkles, UserCheck } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import type { ReviewCaseAuditEntry } from '@/api/hooks/useReview';

interface AuditTimelineWorkspaceProps {
  entries: ReviewCaseAuditEntry[];
}

type ActorCategory = 'CUSTOMER' | 'SYSTEM' | 'AI' | 'REVIEWER';

function categorizeEvent(eventType: string, payload?: Record<string, unknown>): { actor: ActorCategory; title: string } {
  const typeLower = eventType.toLowerCase();

  if (typeLower.includes('reviewer') || typeLower.includes('claimed') || typeLower.includes('resolved') || typeLower.includes('escalated') || typeLower.includes('info_requested')) {
    return { actor: 'REVIEWER', title: eventType.replace(/_/g, ' ') };
  }

  if (typeLower.includes('evidence') || typeLower.includes('upload') || typeLower.includes('customer') || typeLower.includes('answer')) {
    return { actor: 'CUSTOMER', title: eventType.replace(/_/g, ' ') };
  }

  if (typeLower.includes('ai') || typeLower.includes('extract') || typeLower.includes('ocr') || typeLower.includes('model')) {
    return { actor: 'AI', title: eventType.replace(/_/g, ' ') };
  }

  if (payload && payload.reviewer) {
    return { actor: 'REVIEWER', title: eventType.replace(/_/g, ' ') };
  }

  return { actor: 'SYSTEM', title: eventType.replace(/_/g, ' ') };
}

const ACTOR_STYLES: Record<ActorCategory, { label: string; badge: string; icon: React.FC<{ className?: string }> }> = {
  CUSTOMER: {
    label: 'Customer',
    badge: 'bg-emerald-50 text-emerald-700 border-emerald-200/60',
    icon: User,
  },
  REVIEWER: {
    label: 'Reviewer',
    badge: 'bg-indigo-50 text-indigo-700 border-indigo-200/60',
    icon: UserCheck,
  },
  SYSTEM: {
    label: 'System',
    badge: 'bg-slate-100 text-slate-700 border-slate-200',
    icon: Cpu,
  },
  AI: {
    label: 'AI Model',
    badge: 'bg-purple-50 text-purple-700 border-purple-200/60',
    icon: Sparkles,
  },
};

export const AuditTimelineWorkspace: React.FC<AuditTimelineWorkspaceProps> = ({ entries }) => {
  if (!entries || entries.length === 0) {
    return (
      <Card padding="md" className="bg-white border border-surface-border shadow-xs text-center py-6">
        <Clock className="w-5 h-5 text-content-tertiary mx-auto mb-1" />
        <p className="text-xs text-content-secondary">No audit entries recorded yet.</p>
      </Card>
    );
  }

  return (
    <Card padding="md" className="bg-white border border-surface-border shadow-xs space-y-4" data-testid="audit-timeline">
      <div className="flex items-center justify-between border-b border-surface-border pb-3">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-paytm-blue-action" />
          <h3 className="text-sm font-bold text-content-primary">Lifecycle Audit Trail</h3>
        </div>
        <span className="text-[10px] font-bold text-content-tertiary uppercase tracking-wider bg-slate-100 px-2 py-0.5 rounded-sm">
          {entries.length} Events
        </span>
      </div>

      <div className="relative border-l-2 border-slate-100 ml-2.5 space-y-4 py-1">
        {entries.map((entry, idx) => {
          const payload = entry.payload as Record<string, unknown> | undefined;
          const { actor, title } = categorizeEvent(entry.event_type, payload);
          const style = ACTOR_STYLES[actor];
          const Icon = style.icon;

          return (
            <div key={idx} className="relative pl-5 group">
              {/* Dot marker */}
              <div className="absolute -left-[5px] top-1 w-2.5 h-2.5 rounded-full bg-slate-300 ring-4 ring-white group-hover:bg-paytm-blue transition-colors" />

              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${style.badge}`}>
                    <Icon className="w-3 h-3" />
                    {style.label}
                  </span>

                  <span className="text-[11px] font-mono text-content-tertiary">
                    {new Date(entry.created_at).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                </div>

                <p className="text-xs font-bold text-content-primary capitalize">
                  {title}
                </p>

                {payload && (
                  <div className="text-[11px] text-content-secondary space-y-0.5 font-medium">
                    {payload.reviewer != null && (
                      <p>
                        Action by: <strong className="text-content-primary">{String(payload.reviewer)}</strong>
                      </p>
                    )}
                    {payload.requested_docs != null && Array.isArray(payload.requested_docs) && (
                      <p className="text-amber-800">
                        Requested: {payload.requested_docs.map(String).join(', ')}
                      </p>
                    )}
                    {payload.customer_message != null && (
                      <p className="italic text-content-tertiary truncate">
                        &ldquo;{String(payload.customer_message)}&rdquo;
                      </p>
                    )}
                    {payload.resolution_type != null && (
                      <p className="text-emerald-700 font-bold">
                        Type: {String(payload.resolution_type).replace(/_/g, ' ')}
                      </p>
                    )}
                    {payload.escalation_reason != null && (
                      <p className="text-red-700">
                        Reason: {String(payload.escalation_reason)}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
};

export default AuditTimelineWorkspace;
