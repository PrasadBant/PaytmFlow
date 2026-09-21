import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ConnectionExperience } from './ConnectionExperience';

describe('ConnectionExperience', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the intro wordmark, tagline, and an accessible connecting status', () => {
    render(<ConnectionExperience slow={false} />);

    expect(screen.getByText('PaytmFlow')).toBeInTheDocument();
    expect(screen.getByText("Let's get things moving.")).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Connecting to PaytmFlow.');
  });

  it('never renders a fake percentage or progress number', () => {
    render(<ConnectionExperience slow={false} />);
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it('never exposes infrastructure/technical wording', () => {
    render(<ConnectionExperience slow />);
    const bannedTerms = [/backend/i, /server/i, /database/i, /render\.com/i, /api error/i];
    for (const term of bannedTerms) {
      expect(screen.queryByText(term)).not.toBeInTheDocument();
    }
  });

  it('switches to the long-wait status announcement once slow is true', () => {
    render(<ConnectionExperience slow />);
    expect(screen.getByRole('status')).toHaveTextContent('Still connecting to PaytmFlow.');
  });
});
