import { create } from 'zustand';

export type Role = 'CUSTOMER' | 'REVIEW_OFFICER';

interface RoleState {
  role: Role;
  setRole: (role: Role) => void;
}

// Prototype-only client mirror of the session's server-side role (see
// backend app/security/reviewer.py). This store is never the security
// boundary - every /review/* API call is independently authorized by the
// backend against the session's own persisted role, not this value.
export const useRoleStore = create<RoleState>((set) => ({
  role: 'CUSTOMER',
  setRole: (role) => set({ role }),
}));
