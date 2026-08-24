import { AlertTriangle } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";

import { useBalance } from "@/contexts/balance-context";
import { openTopUp } from "@/lib/agentflow";
import { useI18n } from "@/i18n";

/**
 * Global banner shown when the account is out of tokens — driven by the balance
 * endpoint AND by the gateway's out-of-tokens signal latched from the chat
 * surfaces (ChatPage PTY stream + ChatSidebar `error` event). Carries the same
 * «Пополнить» top-up action as the sidebar pill.
 */
export function OutOfTokensBanner() {
  const { locale } = useI18n();
  const ru = locale === "ru" || locale === "uk";
  const { outOfTokens, balance, unavailable } = useBalance();

  // Until the balance endpoint ships (404 → unavailable), never show the banner
  // so a stray gateway signal can't latch a sticky false alert. Mirrors AccountBalance.
  if (unavailable) return null;
  if (!outOfTokens) return null;

  const message = ru
    ? "Закончились токены на балансе — агент не сможет отвечать, пока вы не пополните счёт."
    : "You're out of tokens — the agent can't reply until you top up.";
  const cta = ru ? "Пополнить" : "Top up";

  return (
    <div
      role="alert"
      className="flex shrink-0 items-center gap-3 border-b border-warning/40 bg-warning/10 px-4 py-2 text-sm text-text-primary"
    >
      <AlertTriangle className="h-4 w-4 shrink-0 text-warning" />
      <span className="min-w-0 flex-1">{message}</span>
      <Button
        size="sm"
        onClick={() => openTopUp(balance?.topup_url)}
        className="shrink-0"
      >
        {cta}
      </Button>
    </div>
  );
}
