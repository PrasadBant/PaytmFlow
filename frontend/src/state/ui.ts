import { create } from 'zustand';

interface UiState {
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
  closeSidebar: () => void;
  isAssistantOpen: boolean;
  assistantJourneyContext: string | null;
  openAssistant: (context?: string | null) => void;
  closeAssistant: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  isSidebarOpen: false,
  toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
  closeSidebar: () => set({ isSidebarOpen: false }),
  isAssistantOpen: false,
  assistantJourneyContext: null,
  openAssistant: (context = null) =>
    set({ isAssistantOpen: true, assistantJourneyContext: context }),
  closeAssistant: () => set({ isAssistantOpen: false, assistantJourneyContext: null }),
}));
