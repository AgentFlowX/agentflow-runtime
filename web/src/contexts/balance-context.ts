import { createContext, useContext } from "react";

import type { AccountBalanceResponse } from "@/lib/api";

export interface BalanceState {
  /** Latest balance payload, or null before the first load / when unavailable. */
  balance: AccountBalanceResponse | null;
  /** True while the first fetch is in flight. */
  loading: boolean;
  /** True when the endpoint is unavailable (404 / network) — hide the UI. */
  unavailable: boolean;
  /** Derived: account is out of tokens (balance<=0, server flag, or gateway signal). */
  outOfTokens: boolean;
  /** Force an immediate refetch. */
  refresh: () => void;
  /** Eagerly latch out-of-tokens from a detected gateway signal, then refetch. */
  flagOutOfTokens: () => void;
}

export const BalanceContext = createContext<BalanceState | null>(null);

// Safe default so consumers rendered outside the provider (unit tests for
// ChatPage / ChatSidebar) neither crash nor surface balance UI.
const FALLBACK: BalanceState = {
  balance: null,
  loading: false,
  unavailable: true,
  outOfTokens: false,
  refresh: () => {},
  flagOutOfTokens: () => {},
};

export function useBalance(): BalanceState {
  return useContext(BalanceContext) ?? FALLBACK;
}
