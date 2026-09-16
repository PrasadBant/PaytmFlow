import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { HelpScreen } from '@/screens/HelpScreen';

function renderHelp() {
  return render(
    <MemoryRouter>
      <HelpScreen />
    </MemoryRouter>
  );
}

describe('HelpScreen', () => {
  it('renders the Help header, subtitle, and search — not the Home hero', () => {
    renderHelp();
    expect(screen.getByTestId('screen-help')).toBeInTheDocument();
    expect(screen.getByText('How can we help?')).toBeInTheDocument();
    expect(
      screen.getByText('Find answers about your journeys, documents, verification, and account.')
    ).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Search for help')).toBeInTheDocument();
    expect(screen.queryByText(/Your Financial Journey/i)).not.toBeInTheDocument();
    expect(screen.queryByText('Start Your Journey →')).not.toBeInTheDocument();
  });

  it('renders all six help categories', () => {
    renderHelp();
    [
      'Getting Started',
      'My Journeys',
      'Documents & Verification',
      'Forms & Information',
      'Account & Security',
      'Common Questions',
    ].forEach((label) => {
      expect(screen.getByText(label)).toBeInTheDocument();
    });
  });

  it('expands and collapses an FAQ item on click', async () => {
    const user = userEvent.setup();
    renderHelp();

    const trigger = screen.getByTestId('faq-trigger-faq-start-journey');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');

    await user.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(/Start Journey.*from the sidebar/i)).toBeInTheDocument();

    await user.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('filters FAQ items by search query', async () => {
    const user = userEvent.setup();
    renderHelp();

    await user.type(screen.getByPlaceholderText('Search for help'), 'resume');

    expect(screen.getByText('Can I resume a journey I started earlier?')).toBeInTheDocument();
    expect(screen.queryByText('Is my uploaded information secure?')).not.toBeInTheDocument();
  });

  it('shows a "no results" message when search matches nothing', async () => {
    const user = userEvent.setup();
    renderHelp();

    await user.type(screen.getByPlaceholderText('Search for help'), 'zzzznomatch');

    expect(screen.getByText('No help topics match your search.')).toBeInTheDocument();
  });

  it('renders the "Still need help?" panel with both CTAs', () => {
    renderHelp();
    expect(screen.getByText('Still need help?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'View My Journeys' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Back to Home' })).toBeInTheDocument();
  });
});
