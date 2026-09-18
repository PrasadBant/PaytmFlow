import { describe, it, expect } from 'vitest';
import { cn, formatIndianCurrency, parseIndianCurrency, formatRelativeTime } from './utils';

describe('Phase F30: Utility Functions (Formatting & Numbering)', () => {
  describe('cn (Tailwind Merge + Clsx)', () => {
    it('merges class names and resolves tailwind conflicts', () => {
      expect(cn('p-4', 'bg-white', false && 'hidden', 'p-6')).toBe('bg-white p-6');
    });
  });

  describe('formatIndianCurrency', () => {
    it('formats Indian digit grouping correctly (500000 -> 5,00,000)', () => {
      expect(formatIndianCurrency(500000)).toBe('5,00,000');
      expect(formatIndianCurrency(10000000)).toBe('1,00,00,000');
      expect(formatIndianCurrency(85000)).toBe('85,000');
      expect(formatIndianCurrency(500)).toBe('500');
      expect(formatIndianCurrency(0)).toBe('0');
    });

    it('handles string input and non-numeric characters', () => {
      expect(formatIndianCurrency('500000')).toBe('5,00,000');
      expect(formatIndianCurrency('₹85,000')).toBe('85,000');
    });

    it('handles null, undefined and empty values safely', () => {
      expect(formatIndianCurrency(null)).toBe('');
      expect(formatIndianCurrency(undefined)).toBe('');
      expect(formatIndianCurrency('')).toBe('');
    });
  });

  describe('parseIndianCurrency', () => {
    it('parses formatted Indian currency strings to raw numbers', () => {
      expect(parseIndianCurrency('5,00,000')).toBe(500000);
      expect(parseIndianCurrency('₹ 5,00,000')).toBe(500000);
      expect(parseIndianCurrency('85,000')).toBe(85000);
      expect(parseIndianCurrency('invalid')).toBe(null);
      expect(parseIndianCurrency('')).toBe(null);
    });
  });

  describe('formatRelativeTime', () => {
    it('formats recent timestamps as Just now, minutes, hours, days', () => {
      const now = new Date();
      expect(formatRelativeTime(now.toISOString())).toBe('Just now');

      const tenMinutesAgo = new Date(now.getTime() - 10 * 60 * 1000);
      expect(formatRelativeTime(tenMinutesAgo.toISOString())).toBe('10m ago');

      const twoHoursAgo = new Date(now.getTime() - 2 * 60 * 60 * 1000);
      expect(formatRelativeTime(twoHoursAgo.toISOString())).toBe('2h ago');

      const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
      expect(formatRelativeTime(oneDayAgo.toISOString())).toBe('Yesterday');

      const fiveDaysAgo = new Date(now.getTime() - 5 * 24 * 60 * 60 * 1000);
      expect(formatRelativeTime(fiveDaysAgo.toISOString())).toBe('5d ago');
    });

    it('handles invalid dates and empty inputs gracefully', () => {
      expect(formatRelativeTime('')).toBe('');
      expect(formatRelativeTime(null)).toBe('');
      expect(formatRelativeTime(undefined)).toBe('');
      expect(formatRelativeTime('invalid-date-string')).toBe('');
    });
  });
});
