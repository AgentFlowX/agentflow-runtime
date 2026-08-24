import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { api, type AccountBalanceResponse } from "@/lib/api";
import { BalanceContext, type BalanceState } from "@/contexts/balance-context";

const POLL_MS = 60_000;

function deriveOutOfTokens(
  b: AccountBalanceResponse | null,
  forced: boolean,
): boolean {
  if (forced) return true;
  if (!b) return false;
  if (b.out_of_tokens === true) return true;
  if (typeof b.remaining_tokens === "number") return b.remaining_tokens <= 0;
  if (typeof b.remaining === "number") return b.remaining <= 0;
  return false;
}

/**
 * App-wide AgentFlow balance state. Polls `GET /api/account/balance`, and lets
 * the chat surfaces latch out-of-tokens the instant the gateway's over-budget
 * text is seen (see ChatPage PTY stream + ChatSidebar `error` event).
 */
export function BalanceProvider({ children }: { children: ReactNode }) {
  const [balance, setBalance] = useState<AccountBalanceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  const [forced, setForced] = useState(false);
  const inFlight = useRef(false);

  const load = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const data = await api.getAccountBalance();
      setBalance(data);
      setUnavailable(false);
      // A fresh positive balance clears a previously-latched out-of-tokens flag.
      if (!deriveOutOfTokens(data, false)) setForced(false);
    } catch {
      // 404 (endpoint not deployed) or network error — hide the UI, don't nag.
      setUnavailable(true);
    } finally {
      setLoading(false);
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), POLL_MS);
    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("focus", onFocus);
    };
  }, [load]);

  const flagOutOfTokens = useCallback(() => {
    setForced(true);
    void load();
  }, [load]);

  const refresh = useCallback(() => void load(), [load]);

  const value = useMemo<BalanceState>(
    () => ({
      balance,
      loading,
      unavailable,
      outOfTokens: deriveOutOfTokens(balance, forced),
      refresh,
      flagOutOfTokens,
    }),
    [balance, loading, unavailable, forced, refresh, flagOutOfTokens],
  );

  return (
    <BalanceContext.Provider value={value}>{children}</BalanceContext.Provider>
  );
}
