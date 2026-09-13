import {
  useState,
  useRef,
  type DragEvent,
  type ChangeEvent,
  type KeyboardEvent,
  type ReactElement,
} from 'react';
import { UploadCloud, FileText, FileImage, X, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Spinner } from '@/components/primitives/Spinner';

const MAX_EVIDENCE_BYTES = 10 * 1024 * 1024; // 10 MB

export interface EvidenceDropzoneProps {
  onFileSelect: (file: File | null) => void;
  selectedFile?: File | null;
  accept?: string[];
  maxSizeBytes?: number;
  isUploading?: boolean;
  error?: string | null;
  disabled?: boolean;
  className?: string;
}

const DEFAULT_ACCEPTED_TYPES = [
  'application/pdf',
  'image/jpeg',
  'image/png',
  'image/jpg',
];

const DEFAULT_ACCEPTED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png'];

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function EvidenceDropzone({
  onFileSelect,
  selectedFile = null,
  accept = DEFAULT_ACCEPTED_TYPES,
  maxSizeBytes = MAX_EVIDENCE_BYTES,
  isUploading = false,
  error = null,
  disabled = false,
  className,
}: EvidenceDropzoneProps): ReactElement {
  const [isDragging, setIsDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeError = error || validationError;

  const validateFile = (file: File): boolean => {
    setValidationError(null);

    // Size validation (Max 10MB)
    if (file.size > maxSizeBytes) {
      setValidationError('File size exceeds the 10MB limit. Please upload a smaller file.');
      return false;
    }

    // Type validation
    const fileType = file.type.toLowerCase();
    const fileName = file.name.toLowerCase();
    const matchesMime = accept.some((t) => t.toLowerCase() === fileType);
    const matchesExt = DEFAULT_ACCEPTED_EXTENSIONS.some((ext) => fileName.endsWith(ext));

    if (!matchesMime && !matchesExt) {
      setValidationError('Invalid file format. Only PDF, JPEG, and PNG files are supported.');
      return false;
    }

    return true;
  };

  const handleFiles = (files: FileList | null): void => {
    if (!files || files.length === 0 || disabled || isUploading) return;
    const file = files[0];
    if (validateFile(file)) {
      onFileSelect(file);
    } else {
      onFileSelect(null);
    }
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    if (!disabled && !isUploading) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>): void => {
    handleFiles(e.target.files);
    // Reset file input value so selecting the same file triggers change
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (disabled || isUploading || selectedFile) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fileInputRef.current?.click();
    }
  };

  const handleRemove = (e: React.MouseEvent): void => {
    e.stopPropagation();
    setValidationError(null);
    onFileSelect(null);
  };

  const isPdf = selectedFile?.name.toLowerCase().endsWith('.pdf');

  return (
    <div className={cn('w-full space-y-3', className)}>
      <input
        ref={fileInputRef}
        type="file"
        accept={accept.join(',') + ',' + DEFAULT_ACCEPTED_EXTENSIONS.join(',')}
        onChange={handleInputChange}
        disabled={disabled || isUploading}
        className="hidden"
        data-testid="evidence-file-input"
        aria-label="Upload evidence file"
      />

      {selectedFile ? (
        /* Selected file display card */
        <div
          data-testid="selected-file-card"
          className="p-4 rounded-card bg-surface border border-surface-border flex items-center justify-between gap-3 shadow-xs"
        >
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-button bg-paytm-blue-50 text-paytm-blue flex items-center justify-center shrink-0">
              {isPdf ? (
                <FileText className="w-5 h-5" aria-hidden="true" />
              ) : (
                <FileImage className="w-5 h-5" aria-hidden="true" />
              )}
            </div>

            <div className="min-w-0">
              <p className="text-sm font-semibold text-content-primary truncate">
                {selectedFile.name}
              </p>
              <p className="text-xs text-content-secondary mt-0.5">
                {formatFileSize(selectedFile.size)}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {isUploading ? (
              <div className="flex items-center gap-2 text-xs text-paytm-blue font-semibold">
                <Spinner size="sm" className="text-paytm-blue" />
                <span>Uploading...</span>
              </div>
            ) : (
              <button
                type="button"
                onClick={handleRemove}
                disabled={disabled}
                aria-label="Remove selected file"
                className="p-1.5 rounded-button text-content-tertiary hover:text-paytm-red hover:bg-paytm-red-light transition-colors focus-visible:ring-2 focus-visible:ring-paytm-cyan focus-visible:outline-none"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      ) : (
        /* Dropzone area matching reference */
        <div
          role="button"
          tabIndex={disabled || isUploading ? -1 : 0}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          onKeyDown={handleKeyDown}
          data-testid="evidence-dropzone"
          aria-label="Drop files here or click to browse"
          aria-describedby={activeError ? 'dropzone-error' : undefined}
          className={cn(
            'relative rounded-2xl border-2 border-dashed p-8 md:p-10 text-center cursor-pointer transition-all duration-150 select-none flex flex-col items-center justify-center gap-3',
            isDragging
              ? 'border-paytm-blue bg-paytm-blue-50/50 scale-[1.01]'
              : 'border-slate-300 bg-white hover:border-paytm-blue/60 hover:bg-slate-50/60',
            activeError && 'border-paytm-red bg-paytm-red-light/30',
            (disabled || isUploading) && 'opacity-60 cursor-not-allowed bg-surface-muted',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-paytm-cyan focus-visible:border-paytm-cyan'
          )}
        >
          <div className="w-12 h-12 rounded-full bg-paytm-blue-50 text-paytm-blue flex items-center justify-center shrink-0 mb-1">
            <UploadCloud className="w-6 h-6 text-paytm-blue" aria-hidden="true" />
          </div>

          <div className="space-y-2 flex flex-col items-center">
            <p className="text-sm font-semibold text-content-primary">
              Drag and drop your file here
            </p>
            <span className="text-xs text-content-tertiary">or</span>
            <span className="inline-flex items-center px-4 py-1.5 rounded-full text-xs font-semibold text-paytm-blue border border-paytm-blue/40 bg-white hover:bg-paytm-blue-50 shadow-xs transition-colors">
              Choose File
            </span>
            <p className="text-xs text-content-secondary pt-2">
              Accepted formats: PDF, JPG, PNG (Max 10MB)
              <span className="sr-only">Click to upload or drag and drop. Supported formats: PDF, JPEG, PNG (Max 10MB)</span>
            </p>
          </div>
        </div>
      )}

      {/* Validation / Server Error */}
      {activeError && (
        <p
          id="dropzone-error"
          data-testid="dropzone-error"
          className="text-xs text-paytm-red flex items-center gap-1.5 mt-1.5"
        >
          <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />
          <span>{activeError}</span>
        </p>
      )}
    </div>
  );
}

export default EvidenceDropzone;
