import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter, useNavigate } from 'react-router-dom';
import type * as ReactRouterDom from 'react-router-dom';
import { Screen02JourneySelection } from '@/screens/Screen02JourneySelection';
import * as usePacksHook from '@/api/hooks/usePacks';
import type { JourneyPackSummary } from '@/api/hooks/usePacks';

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof ReactRouterDom>('react-router-dom');
  return {
    ...actual,
    useNavigate: vi.fn(),
  };
});

const mockPacks: JourneyPackSummary[] = [
  {
    journey_type: 'LENDING',
    display_name: 'Personal Loan',
    description: 'Unlock instant disbursement.',
    icon: 'rupee',
    flagship_demo: true,
    lifecycle_status: 'SUPPORTED',
  },
  {
    journey_type: 'INSURANCE',
    display_name: 'Health & Life Insurance',
    description: 'Fast-track policy issuance.',
    icon: 'shield',
    flagship_demo: false,
    lifecycle_status: 'SUPPORTED',
  },
  {
    journey_type: 'DRAFT_JOURNEY',
    display_name: 'Draft Journey',
    description: 'Coming soon',
    icon: 'bank',
    flagship_demo: false,
    lifecycle_status: 'DRAFT',
  },
];

describe('Screen02JourneySelection', () => {
  it('renders headline and description', () => {
    vi.spyOn(usePacksHook, 'usePacks').mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof usePacksHook.usePacks>);

    render(<Screen02JourneySelection />, { wrapper: BrowserRouter });

    expect(screen.getByText('Choose Your Financial Journey')).toBeInTheDocument();
    expect(screen.getByText('Select the journey you want to continue or start.')).toBeInTheDocument();
  });

  it('renders loading state', () => {
    vi.spyOn(usePacksHook, 'usePacks').mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof usePacksHook.usePacks>);

    render(<Screen02JourneySelection />, { wrapper: BrowserRouter });
    expect(screen.getByText('Loading journeys...')).toBeInTheDocument();
  });

  it('renders error state', () => {
    vi.spyOn(usePacksHook, 'usePacks').mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('API failed'),
    } as unknown as ReturnType<typeof usePacksHook.usePacks>);

    render(<Screen02JourneySelection />, { wrapper: BrowserRouter });
    expect(screen.getByText('Failed to load journeys')).toBeInTheDocument();
    expect(screen.getByText('API failed')).toBeInTheDocument();
  });

  it('renders packs with icons, descriptions, and flagship badge', () => {
    vi.spyOn(usePacksHook, 'usePacks').mockReturnValue({
      data: { packs: mockPacks },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof usePacksHook.usePacks>);

    render(<Screen02JourneySelection />, { wrapper: BrowserRouter });

    expect(screen.getByText('Personal Loan')).toBeInTheDocument();
    expect(screen.getByText('Unlock instant disbursement.')).toBeInTheDocument();
    expect(screen.getByText('Flagship Demo')).toBeInTheDocument();

    expect(screen.getByText('Health & Life Insurance')).toBeInTheDocument();
    expect(screen.getByText('Fast-track policy issuance.')).toBeInTheDocument();

    // The draft journey should be present but have correct attributes
    expect(screen.getByText('Draft Journey')).toBeInTheDocument();
  });

  it('navigates when clicking a supported journey', () => {
    const navigateMock = vi.fn();
    vi.mocked(useNavigate).mockReturnValue(navigateMock);

    vi.spyOn(usePacksHook, 'usePacks').mockReturnValue({
      data: { packs: mockPacks },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof usePacksHook.usePacks>);

    render(<Screen02JourneySelection />, { wrapper: BrowserRouter });

    const card = screen.getByTestId('pack-card-LENDING');
    fireEvent.click(card);

    expect(navigateMock).toHaveBeenCalledWith('/start/LENDING');
  });

  it('does not navigate when clicking a draft journey', () => {
    const navigateMock = vi.fn();
    vi.mocked(useNavigate).mockReturnValue(navigateMock);

    vi.spyOn(usePacksHook, 'usePacks').mockReturnValue({
      data: { packs: mockPacks },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof usePacksHook.usePacks>);

    render(<Screen02JourneySelection />, { wrapper: BrowserRouter });

    const draftCard = screen.getByTestId('pack-card-DRAFT_JOURNEY');
    expect(draftCard).toHaveAttribute('title', 'This journey is coming soon');
    
    fireEvent.click(draftCard);
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('is keyboard-reachable and activatable with Enter (regression)', () => {
    // Real-user QA finding: this card - the primary way to choose a
    // journey on this screen - was a plain <div onClick>, unreachable and
    // unusable via keyboard alone (no Tab stop, no Enter/Space
    // activation).
    const navigateMock = vi.fn();
    vi.mocked(useNavigate).mockReturnValue(navigateMock);

    vi.spyOn(usePacksHook, 'usePacks').mockReturnValue({
      data: { packs: mockPacks },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof usePacksHook.usePacks>);

    render(<Screen02JourneySelection />, { wrapper: BrowserRouter });

    const card = screen.getByTestId('pack-card-LENDING');
    expect(card).toHaveAttribute('tabIndex', '0');
    expect(card).toHaveAttribute('role', 'button');

    fireEvent.keyDown(card, { key: 'Enter' });
    expect(navigateMock).toHaveBeenCalledWith('/start/LENDING');
  });

  it('is activatable with the Space key (regression)', () => {
    const navigateMock = vi.fn();
    vi.mocked(useNavigate).mockReturnValue(navigateMock);

    vi.spyOn(usePacksHook, 'usePacks').mockReturnValue({
      data: { packs: mockPacks },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof usePacksHook.usePacks>);

    render(<Screen02JourneySelection />, { wrapper: BrowserRouter });

    const card = screen.getByTestId('pack-card-LENDING');
    fireEvent.keyDown(card, { key: ' ' });
    expect(navigateMock).toHaveBeenCalledWith('/start/LENDING');
  });

  it('a draft journey card is removed from the tab order and does not activate via keyboard', () => {
    const navigateMock = vi.fn();
    vi.mocked(useNavigate).mockReturnValue(navigateMock);

    vi.spyOn(usePacksHook, 'usePacks').mockReturnValue({
      data: { packs: mockPacks },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof usePacksHook.usePacks>);

    render(<Screen02JourneySelection />, { wrapper: BrowserRouter });

    const draftCard = screen.getByTestId('pack-card-DRAFT_JOURNEY');
    expect(draftCard).toHaveAttribute('tabIndex', '-1');
    fireEvent.keyDown(draftCard, { key: 'Enter' });
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
