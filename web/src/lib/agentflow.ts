/**
 * AgentFlow-specific billing config + gateway out-of-tokens signal detection.
 *
 * This is AgentFlow's OWN balance surface (site = https://agentflow.website,
 * gateway = https://llm.agentflow.website), distinct from the upstream
 * Nous/Stripe `/api/billing/*` flow used by apps/desktop. Balance is read from
 * the dashboard backend's `/api/account/balance` proxy; top-up opens the
 * AgentFlow website in the browser.
 */

// Configurable at build time; falls back to the production site. `import.meta.env`
// is typed via "vite/client" (web/tsconfig.app.json) and carries a string index.
const RAW_SITE_URL =
  (import.meta.env.VITE_AGENTFLOW_SITE_URL as string | undefined) ??
  "https://agentflow.website";

// Path on the site that hosts the balance top-up / billing page.
const RAW_TOPUP_PATH =
  (import.meta.env.VITE_AGENTFLOW_TOPUP_PATH as string | undefined) ?? "/billing";

/** Normalised site origin, no trailing slash. */
export const AGENTFLOW_SITE_URL = RAW_SITE_URL.replace(/\/+$/, "");

/** Absolute URL of the top-up page. A per-response `topup_url` overrides this. */
export function agentflowTopUpUrl(override?: string | null): string {
  if (override && /^https?:\/\//i.test(override)) return override;
  const path = RAW_TOPUP_PATH.startsWith("/") ? RAW_TOPUP_PATH : `/${RAW_TOPUP_PATH}`;
  return `${AGENTFLOW_SITE_URL}${path}`;
}

/** Open the AgentFlow top-up page in a new browser tab. */
export function openTopUp(override?: string | null): void {
  try {
    window.open(agentflowTopUpUrl(override), "_blank", "noopener,noreferrer");
  } catch {
    /* popup blocked or no window (tests) — no-op */
  }
}

// Mirrors gateway/run.py `_GATEWAY_BUDGET_RE` (run.py:429-434) plus the friendly
// Russian copy from `_gateway_provider_error_reply` (run.py:718-724). The gateway
// turns an over-budget scoped key (a 401) into a plain "top up" message; the
// terminal stream and the JSON-RPC sidecar `error` event both carry that text.
const OUT_OF_TOKENS_RE =
  /(закончил(?:ись|ся)?\s+токен|пополни(?:те)?\s+баланс|is\s+blocked|blocked\s+key|key\s+[^\n]*blocked|budget[^\n]*exceeded|exceeded[^\n]*budget|crossed\s+spend|budget_exceeded|no_tokens|out\s+of\s+tokens|insufficient[^\n]*(?:token|balance|credit))/i;

/** True when `text` looks like the gateway's out-of-tokens / over-budget signal. */
export function isOutOfTokensSignal(text: unknown): boolean {
  return typeof text === "string" && text.length > 0 && OUT_OF_TOKENS_RE.test(text);
}
