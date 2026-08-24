import { Wallet } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { Typography } from "@nous-research/ui/ui/components/typography/index";

import { useBalance } from "@/contexts/balance-context";
import { openTopUp } from "@/lib/agentflow";
import { useI18n } from "@/i18n";
import { cn } from "@/lib/utils";

/**
 * Sidebar balance pill + «Пополнить» top-up button. Renders nothing until the
 * `/api/account/balance` endpoint answers (so it stays invisible on deployments
 * that have not shipped the endpoint yet).
 */
export function AccountBalance() {
  const { locale } = useI18n();
  const ru = locale === "ru" || locale === "uk";
  const { balance, unavailable, loading, outOfTokens } = useBalance();

  if (unavailable) return null;

  const topUpLabel = ru ? "Пополнить" : "Top up";
  const balanceLabel = ru ? "Баланс" : "Balance";

  let remaining: string;
  if (balance?.remaining_display) {
    remaining = balance.remaining_display;
  } else if (typeof balance?.remaining_tokens === "number") {
    remaining = `${balance.remaining_tokens.toLocaleString()} ${ru ? "токенов" : "tokens"}`;
  } else if (typeof balance?.remaining === "number") {
    remaining = `${balance.remaining.toLocaleString()}${balance.currency ? ` ${balance.currency}` : ""}`;
  } else {
    remaining = loading ? "…" : "—";
  }

  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-between gap-2",
        "px-5 py-2.5",
        "border-t border-current/10",
      )}
    >
      <div className="flex min-w-0 items-center gap-2">
        <Wallet
          className={cn(
            "h-3.5 w-3.5 shrink-0",
            outOfTokens ? "text-destructive" : "text-text-tertiary",
          )}
        />
        <Typography className="min-w-0 truncate font-mono-ui text-xs tabular-nums tracking-[0.06em] text-text-secondary">
          {balanceLabel}:{" "}
          <span className={outOfTokens ? "text-destructive" : "text-text-primary"}>
            {remaining}
          </span>
        </Typography>
      </div>

      <Button
        size="sm"
        onClick={() => openTopUp(balance?.topup_url)}
        aria-label={topUpLabel}
        className="shrink-0"
      >
        {topUpLabel}
      </Button>
    </div>
  );
}
