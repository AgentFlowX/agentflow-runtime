import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { KeyRound, Loader2 } from '@/lib/icons'
import { getCpJwt } from '@/lib/cp-auth'
import { loginAgentFlow, type OnboardingContext } from '@/store/onboarding'

const SITE_URL = (import.meta.env.VITE_AGENTFLOW_SITE_URL as string | undefined) ?? 'https://agentflow.website'

function openSite(path = '/'): void {
  const url = `${SITE_URL.replace(/\/+$/, '')}${path.startsWith('/') ? path : `/${path}`}`
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

interface AgentFlowAuthGateProps {
  profile: string
  requestGateway: OnboardingContext['requestGateway']
}

/**
 * MANDATORY auth gate — the FIRST screen. Blocks the whole app until the user is
 * signed into AgentFlow (a stored CP JWT). Independent of the provider
 * onboarding: even if the local Hermes already has providers configured, the
 * user must log in / register with AgentFlow first. On success, loginAgentFlow
 * stores the JWT, issues the unified key, and points the runtime at our gateway
 * — so after login the app uses OUR models, overriding any local config.
 */
export function AgentFlowAuthGate({ profile, requestGateway }: AgentFlowAuthGateProps) {
  const [authed, setAuthed] = useState(() => Boolean(getCpJwt()))
  const [isRegister, setIsRegister] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<null | string>(null)

  if (authed) {
    return null
  }

  const canSubmit = email.trim().length > 0 && password.length > 0 && !saving

  const submit = async () => {
    if (!canSubmit) {
      return
    }

    setSaving(true)
    setError(null)

    const ctx: OnboardingContext = {
      requestGateway,
      profile,
      onCompleted: () => undefined
    }

    const res = await loginAgentFlow(email, password, isRegister, ctx)

    if (res.ok) {
      setAuthed(true)
    } else {
      setError(res.message ?? 'Не удалось войти.')
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-(--ui-chat-surface-background) p-6">
      <div className="w-full max-w-[26rem] overflow-hidden rounded-xl border border-(--stroke-nous) bg-(--ui-chat-bubble-background) shadow-nous">
        <div className="px-6 pt-6 pb-2">
          <div className="flex items-center gap-3">
            <svg width="34" height="34" viewBox="0 0 100 100" aria-hidden>
              <circle cx="50" cy="50" r="46" fill="#2F9BF6" />
              <path d="M42 30 L62 50 L42 70" fill="none" stroke="#08090c" strokeWidth="13" strokeLinecap="square" />
            </svg>
            <div>
              <h2 className="text-[0.95rem] font-semibold tracking-tight">
                {isRegister ? 'Регистрация в AgentFlow' : 'Вход в AgentFlow'}
              </h2>
              <p className="text-[0.8125rem] leading-5 text-(--ui-text-tertiary)">
                {isRegister ? 'Email и пароль — и агент готов к работе.' : 'Войди, чтобы подключить агента.'}
              </p>
            </div>
          </div>
        </div>

        <div className="grid gap-3 p-6 pt-3">
          <Input
            autoComplete="email"
            autoFocus
            onChange={e => setEmail(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.nativeEvent.isComposing && void submit()}
            placeholder="you@example.com"
            type="email"
            value={email}
          />
          <Input
            autoComplete={isRegister ? 'new-password' : 'current-password'}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.nativeEvent.isComposing && void submit()}
            placeholder="Пароль"
            type="password"
            value={password}
          />
          {error ? <p className="text-xs text-destructive">{error}</p> : null}

          <Button className="mt-1 w-full" disabled={!canSubmit} onClick={() => void submit()}>
            {saving ? <Loader2 className="animate-spin" /> : <KeyRound />}
            {isRegister ? 'Зарегистрироваться' : 'Войти'}
          </Button>

          <div className="flex items-center justify-between gap-2 pt-1">
            <Button
              onClick={() => {
                setIsRegister(v => !v)
                setError(null)
              }}
              size="xs"
              type="button"
              variant="text"
            >
              {isRegister ? 'Уже есть аккаунт? Войти' : 'Нет аккаунта? Регистрация'}
            </Button>
            <Button
              className="text-(--ui-text-tertiary)"
              onClick={() => openSite('/')}
              size="xs"
              type="button"
              variant="text"
            >
              Открыть сайт
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
