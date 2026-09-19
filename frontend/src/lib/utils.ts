import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Formats a numeric value using the Indian numbering system (e.g. 500000 -> 5,00,000)
 */
export function formatIndianCurrency(value: number | string | undefined | null): string {
  if (value === undefined || value === null || value === '') {
    return '';
  }
  const numericValue = typeof value === 'number' ? value : Number(String(value).replace(/[^0-9.-]+/g, ''));
  if (isNaN(numericValue)) {
    return String(value);
  }

  // Format with en-IN locale
  return new Intl.NumberFormat('en-IN').format(numericValue);
}

/**
 * Formats an ISO date string into human-readable relative time (e.g. "2h ago", "3d ago")
 */
export function formatRelativeTime(dateInput: string | Date | undefined | null): string {
  if (!dateInput) return '';
  
  let date: Date;
  if (typeof dateInput === 'string') {
    // Error #9: SQLite/FastAPI sometimes returns naive datetime strings for UTC times
    // (e.g., "2026-09-18T09:00:00" instead of "2026-09-18T09:00:00Z").
    // If it lacks a timezone indicator (Z or +/- offset), assume it's UTC.
    let dateStr = dateInput;
    if (dateStr.includes('T') && !/(Z|[+-]\d{2}:\d{2})$/.test(dateStr)) {
      dateStr += 'Z';
    }
    date = new Date(dateStr);
  } else {
    date = dateInput;
  }
  
  if (isNaN(date.getTime())) return '';

  const now = new Date();
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  // If the date is in the future (negative diff), or less than 60s ago
  if (diffInSeconds < 60) {
    return 'Just now';
  }
  const diffInMinutes = Math.floor(diffInSeconds / 60);
  if (diffInMinutes < 60) {
    return `${diffInMinutes}m ago`;
  }
  const diffInHours = Math.floor(diffInMinutes / 60);
  if (diffInHours < 24) {
    return `${diffInHours}h ago`;
  }
  const diffInDays = Math.floor(diffInHours / 24);
  if (diffInDays === 1) {
    return 'Yesterday';
  }
  if (diffInDays < 30) {
    return `${diffInDays}d ago`;
  }
  return date.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
}

/**
 * Parses Indian currency string (e.g. "₹ 5,00,000" or "5,00,000") back to a raw number.
 */
export function parseIndianCurrency(value: string): number | null {
  const cleaned = value.replace(/[^0-9.-]+/g, '');
  if (!cleaned) return null;
  const num = Number(cleaned);
  return isNaN(num) ? null : num;
}

// Source traceability (Sarvam integration): a subtle "where did this AI
// extraction come from" label shared by every Review Center surface that
// shows evidence (EvidenceComparisonWorkspace, WhySeeingCase) - never a
// "Powered by AI" banner, just a small factual source line. Falls back to
// the raw provider string for a value not in this map.
const AI_PROVIDER_LABELS: Record<string, string> = {
  sarvam: 'Sarvam Vision',
  local_ml: 'Local Document AI',
  llm: 'Hosted LLM',
  mock: 'Demo Data',
};

export function aiProviderLabel(provider: string | null | undefined): string | null {
  if (!provider) return null;
  return AI_PROVIDER_LABELS[provider] ?? provider;
}



