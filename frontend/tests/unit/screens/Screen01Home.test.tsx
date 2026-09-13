import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type * as RouterDom from 'react-router-dom';
import { BrowserRouter, useNavigate } from 'react-router-dom';
import { Screen01Home } from '@/screens/Screen01Home';

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof RouterDom>('react-router-dom');
  return {
    ...actual,
    useNavigate: vi.fn(),
  };
});

describe('Screen01Home', () => {
  it('renders exact copy for headline, body, and bottom statement', () => {
    render(<Screen01Home />, { wrapper: BrowserRouter });

    // Headline
    expect(screen.getByText(/Your Financial Journey/i)).toBeInTheDocument();
    expect(screen.getByText(/Back on Track\./i)).toBeInTheDocument();
    
    // Body
    expect(screen.getByText('Resolve application blockers, complete your journey, and move forward with confidence — all in one place.')).toBeInTheDocument();
    
    // Bottom statement
    expect(screen.getByText('One Platform. Six Financial Journeys. Real Progress.')).toBeInTheDocument();
  });

  it('renders CTA and navigates to /start on click', () => {
    const navigateMock = vi.fn();
    vi.mocked(useNavigate).mockReturnValue(navigateMock);
    
    render(<Screen01Home />, { wrapper: BrowserRouter });
    
    const ctaButton = screen.getByRole('button', { name: 'Start Your Journey →' });
    expect(ctaButton).toBeInTheDocument();
    
    fireEvent.click(ctaButton);
    expect(navigateMock).toHaveBeenCalledWith('/start');
  });

  it('renders all 3 value cards with exact titles and descriptions', () => {
    render(<Screen01Home />, { wrapper: BrowserRouter });
    
    // Card 1
    expect(screen.getByRole('heading', { level: 2, name: 'Guided next steps' })).toBeInTheDocument();
    expect(screen.getByText('Know exactly what to do next.')).toBeInTheDocument();
    
    // Card 2
    expect(screen.getByRole('heading', { level: 2, name: 'AI-powered insights' })).toBeInTheDocument();
    expect(screen.getByText('Get personalized guidance.')).toBeInTheDocument();
    
    // Card 3
    expect(screen.getByRole('heading', { level: 2, name: 'Secure & private' })).toBeInTheDocument();
    expect(screen.getByText('Your data stays safe.')).toBeInTheDocument();
  });

  it('has an accessible structure including hero illustration slot', () => {
    render(<Screen01Home />, { wrapper: BrowserRouter });
    
    // The headline is an h1
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
    
    // Hero illustration is present with accessible label or text
    expect(screen.getByTestId('hero-illustration')).toBeInTheDocument();
    expect(screen.getByText('Hero Illustration Area')).toBeInTheDocument();
    
    // Value card icons should be hidden from screen readers (handled in implementation with aria-hidden)
    // The headings are semantically correct (h2)
    const subHeadings = screen.getAllByRole('heading', { level: 2 });
    expect(subHeadings).toHaveLength(3);
  });
});
