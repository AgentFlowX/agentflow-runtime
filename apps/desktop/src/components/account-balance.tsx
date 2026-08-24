import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { cpMe, getCpJwt } from '@/lib/cp-auth'

const SITE_URL = (import.meta.env.VITE_AGENTFLOW_SITE_URL as string | undefined) ?? 'https://agentflow.website'
const TOPUP_PATH = (import.meta.env.VITE_AGENTFLOW_TOPUP_PATH as string | undefined) ?? '/billing'

function topUpUrl(): string {
  const base = SITE_URL.replace(/\/+$/, '')
  const path = TOPUP_PATH.startsWith('/') ? TOPUP_PATH : `/${TOPUP_PATH}`
  return `${base}${path}`
}

function openTopUp(): void {
  const url = topUpUrl()
  // Prefer the desktop bridge (opens the OS browser); fall back to window.open.
  const bridge = (window as { hermesDesktop?: { openExternal?: (u: string) => void } }).hermesDesktop
  if (bridge?.openExternal) {
    try {
      bridge.openExternal(url)
      return
    } catch {
      /* fall through */
    }
  }
  window.open(url, '_blank', 'noopener,noreferrer')
}

function fmt(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`
  return String(Math.max(0, Math.round(n)))
}

/**
 * Account balance pill — shows the signed-in user's remaining tokens (read from
 * {CP}/v1/me with the stored JWT) and a «Пополнить» button that opens the
 * AgentFlow site. Renders nothing when the user isn't signed into AgentFlow
 * (no JWT) or the balance can't be fetched, so it never shows a broken state.
 */
export function AccountBalance() {
  const [tokens, setTokens] = useState<number | null>(null)
  const [unavailable, setUnavailable] = useState(false)

  useEffect(() => {
    const jwt = getCpJwt()
    if (!jwt) {
      setUnavailable(true)
      return
    }
    let cancelled = false
    cpMe(jwt)
      .then(acc => {
        if (!cancelled) setTokens(Number(acc.balanceTokens ?? 0))
      })
      .catch(() => {
        if (!cancelled) setUnavailable(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (unavailable || tokens === null) {
    return null
  }

  return (
    <div className="flex items-center gap-2 rounded-full border border-(--ui-stroke-tertiary) bg-(--ui-bg-tertiary)/40 px-3 py-1 text-xs">
      <span className="text-muted-foreground">Баланс</span>
      <span className="font-semibold tabular-nums">{fmt(tokens)}</span>
      <span className="text-muted-foreground">токенов</span>
      <Button className="-mr-1 h-5 px-2 font-medium" onClick={openTopUp} size="xs" variant="text">
        Пополнить
      </Button>
    </div>
  )
}
