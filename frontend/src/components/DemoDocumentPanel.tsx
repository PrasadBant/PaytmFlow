import { useState, type ReactElement } from 'react';
import { Sparkles, Download, FileText } from 'lucide-react';
import { Button } from './primitives/Button';
import { Card } from './primitives/Card';
import type { DemoDocument } from '@/lib/demoDocuments';

export interface DemoDocumentPanelProps {
  demoDoc: DemoDocument;
  onUseSample: (file: File) => void;
  disabled?: boolean;
}

/**
 * "Don't have the required document?" panel shown on the real evidence
 * upload step. Fetches the same static demo file a "Download" link would,
 * wraps it in a real File object, and hands it to the SAME selectedFile
 * state / upload mutation a manually-picked file would use - no separate
 * code path, no bypass of the real upload/OCR/AI/validation pipeline.
 */
export function DemoDocumentPanel({ demoDoc, onUseSample, disabled }: DemoDocumentPanelProps): ReactElement {
  const [isFetching, setIsFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const handleUseSample = async (): Promise<void> => {
    setFetchError(null);
    setIsFetching(true);
    try {
      const res = await fetch(demoDoc.path);
      if (!res.ok) throw new Error('Could not load sample document');
      const blob = await res.blob();
      const file = new File([blob], demoDoc.fileName, {
        type: blob.type || 'application/pdf',
      });
      onUseSample(file);
    } catch {
      setFetchError('Could not load the sample document. Try the download link instead.');
    } finally {
      setIsFetching(false);
    }
  };

  return (
    <Card variant="tinted-blue" padding="sm" className="space-y-3" data-testid="demo-document-panel">
      <div className="flex items-start gap-2.5">
        <Sparkles className="w-4 h-4 text-paytm-blue-action shrink-0 mt-0.5" aria-hidden="true" />
        <div className="space-y-1">
          <h3 className="text-sm font-bold text-content-primary">Testing PaytmFlow?</h3>
          <p className="text-xs text-content-secondary leading-relaxed">
            Don&apos;t have a compatible document? Use the {demoDoc.label.toLowerCase()} below —
            it contains fictional data and goes through the exact same upload, extraction, and
            verification pipeline as a real document.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="primary"
          size="sm"
          onClick={handleUseSample}
          disabled={disabled || isFetching}
          data-testid="use-demo-document-btn"
        >
          {isFetching ? 'Loading sample…' : `Use ${demoDoc.label}`}
        </Button>
        <a
          href={demoDoc.path}
          download={demoDoc.fileName}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-paytm-blue-action hover:text-paytm-blue-action-hover"
          data-testid="download-demo-document-link"
        >
          <Download className="w-3.5 h-3.5" aria-hidden="true" />
          Download instead
        </a>
      </div>

      {fetchError && (
        <p className="text-xs text-paytm-red" role="alert">
          {fetchError}
        </p>
      )}

      <p className="text-[11px] text-content-tertiary flex items-center gap-1.5">
        <FileText className="w-3 h-3 shrink-0" aria-hidden="true" />
        Synthetic demo document — not a real financial record.
      </p>
    </Card>
  );
}

export default DemoDocumentPanel;
