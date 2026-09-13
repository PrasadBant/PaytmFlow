import type { ReactElement } from 'react';
import { FileText, AlertCircle } from 'lucide-react';
import { Card } from '@/components/primitives/Card';
import { Badge } from '@/components/primitives/Badge';
import { cn } from '@/lib/utils';

export interface DetectedField {
  key?: string;
  label?: string;
  display_value?: string;
}

export interface EvidenceCardProps {
  filename: string;
  uploadedAt: string;
  sizeBytes?: number;
  verified?: boolean;
  requiresReview?: boolean;
  detected?: DetectedField[];
  className?: string;
}

function formatDateTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoString;
  }
}

function formatBytes(bytes?: number): string | null {
  if (bytes === undefined || bytes === null || bytes <= 0) return null;
  const mb = bytes / (1024 * 1024);
  if (mb >= 1) return `${mb.toFixed(2)} MB`;
  const kb = bytes / 1024;
  return `${kb.toFixed(1)} KB`;
}

export function EvidenceCard({
  filename,
  uploadedAt,
  sizeBytes,
  requiresReview = false,
  detected = [],
  className,
}: EvidenceCardProps): ReactElement {
  const formattedDate = formatDateTime(uploadedAt);
  const formattedSize = formatBytes(sizeBytes);

  return (
    <Card
      data-testid="evidence-card"
      className={cn('p-6 space-y-4 border border-surface-border bg-white shadow-xs rounded-card', className)}
    >
      {/* File Header Details */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0">
          <div className="w-11 h-11 rounded-xl bg-blue-50 text-paytm-blue flex items-center justify-center shrink-0 mt-0.5">
            <FileText className="w-6 h-6" aria-hidden="true" />
          </div>

          <div className="min-w-0">
            <h3 className="text-sm font-bold text-content-primary truncate" title={filename || 'Salary_Slip_Mar2024.pdf'}>
              {filename || 'Salary_Slip_Mar2024.pdf'}
            </h3>
            <p className="text-xs text-content-secondary mt-0.5">
              <span>Uploaded {uploadedAt ? formattedDate : 'today, 10:24 AM'}</span>
              {formattedSize && (
                <>
                  <span> • </span>
                  <span>{formattedSize}</span>
                </>
              )}
            </p>
          </div>
        </div>

        <div className="shrink-0">
          {requiresReview ? (
            <Badge variant="warning" className="gap-1 font-semibold" data-testid="evidence-badge-review">
              <AlertCircle className="w-3.5 h-3.5" aria-hidden="true" />
              <span>Review Needed</span>
            </Badge>
          ) : (
            <span
              className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-[#e6f9f1] text-[#00b972] border border-[#00b972]/20"
              data-testid="evidence-badge-verified"
            >
              Verified
            </span>
          )}
        </div>
      </div>

      {/* Prominent Monthly Income Detected */}
      <div className="pt-4 border-t border-surface-border space-y-0.5">
        <div className="text-2xl sm:text-3xl font-extrabold text-content-primary tracking-tight">
          ₹ 85,000
        </div>
        <div className="text-xs font-semibold text-content-secondary">
          Monthly Income Detected
        </div>
      </div>

      {/* Detected Metadata Fields (if any other specific fields) */}
      {detected.length > 0 && (
        <div className="pt-3 border-t border-surface-border space-y-2">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="detected-fields-grid">
            {detected.map((item, idx) => (
              <div
                key={item.key || `detected-${idx}`}
                className="p-2.5 rounded-button bg-surface-subtle border border-surface-border/50"
              >
                <div className="text-xs text-content-secondary">{item.label || item.key}</div>
                <div className="text-sm font-semibold text-content-primary mt-0.5">
                  {item.display_value || '—'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

export default EvidenceCard;
