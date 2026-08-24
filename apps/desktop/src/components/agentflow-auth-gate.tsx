import { type CSSProperties, useState } from 'react'

import { getCpJwt } from '@/lib/cp-auth'
import { loginAgentFlow, type OnboardingContext } from '@/store/onboarding'

const SITE_URL = (import.meta.env.VITE_AGENTFLOW_SITE_URL as string | undefined) ?? 'https://agentflow.website'

// AgentFlow brand tokens (dark, from the brand book) — inline so the gate looks
// identical to the site regardless of the app's theme tokens.
const C = {
  bg: '#0A0A0B',
  panel: '#0E0E10',
  panel2: '#141417',
  ink: '#F4F4F5',
  muted: '#9a9aa2',
  faint: '#5a5a62',
  line: 'rgba(255,255,255,.10)',
  accent: '#2F9BF6',
  onAccent: '#08090c'
} as const

const FONT_DISPLAY = "'Unbounded', system-ui, sans-serif"
const FONT_MONO = "'JetBrains Mono', ui-monospace, monospace"

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
 * MANDATORY auth gate — the FIRST screen, styled to match the AgentFlow site
 * личный кабинет. Blocks the whole app until the user is signed into AgentFlow
 * (a stored CP JWT), independent of provider onboarding. On success,
 * loginAgentFlow stores the JWT, issues the unified key, and points the runtime
 * at our gateway — so the app then uses OUR models, overriding any local config.
 */
export function AgentFlowAuthGate({ profile, requestGateway }: AgentFlowAuthGateProps) {
  const [authed, setAuthed] = useState(() => Boolean(getCpJwt()))
  const [tab, setTab] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<null | string>(null)

  if (authed) {
    return null
  }

  const isRegister = tab === 'register'
  const canSubmit = email.trim().length > 0 && password.length > 0 && !saving

  const submit = async () => {
    if (!canSubmit) {
      return
    }
    setSaving(true)
    setError(null)
    const ctx: OnboardingContext = { requestGateway, profile, onCompleted: () => undefined }
    const res = await loginAgentFlow(email, password, isRegister, ctx)
    if (res.ok) {
      setAuthed(true)
    } else {
      setError(res.message ?? 'Не удалось войти.')
      setSaving(false)
    }
  }

  const label: CSSProperties = {
    fontFamily: FONT_MONO,
    fontSize: 11,
    letterSpacing: '.14em',
    textTransform: 'uppercase',
    color: C.faint,
    marginBottom: 8,
    display: 'block'
  }
  const input: CSSProperties = {
    width: '100%',
    background: C.panel2,
    border: `1px solid ${C.line}`,
    borderRadius: 14,
    padding: '14px 16px',
    color: C.ink,
    fontSize: 15,
    outline: 'none',
    boxSizing: 'border-box'
  }

  const tabBtn = (active: boolean): CSSProperties => ({
    flex: 1,
    padding: '12px 0',
    borderRadius: 12,
    border: 'none',
    cursor: 'pointer',
    fontWeight: 700,
    fontSize: 14,
    background: active ? C.accent : 'transparent',
    color: active ? C.onAccent : C.muted,
    transition: 'background .15s, color .15s'
  })

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: C.bg,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        fontFamily: "'Manrope', system-ui, sans-serif"
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 460,
          background: C.panel,
          border: `1px solid ${C.line}`,
          borderRadius: 24,
          padding: 'clamp(28px,5vw,44px)',
          boxShadow: '0 40px 100px rgba(0,0,0,.55)'
        }}
      >
        {/* eyebrow + title */}
        <div style={{ textAlign: 'center', marginBottom: 22 }}>
          <div style={{ fontFamily: FONT_MONO, fontSize: 12, letterSpacing: '.16em', textTransform: 'uppercase', color: C.faint }}>
            Личный кабинет
          </div>
          <h1
            style={{
              fontFamily: FONT_DISPLAY,
              fontWeight: 800,
              fontSize: 'clamp(30px,6vw,44px)',
              letterSpacing: '-.02em',
              lineHeight: 1.02,
              color: C.ink,
              margin: '12px 0 0'
            }}
          >
            {isRegister ? 'Регистрация' : 'Вход в AgentFlow'}
          </h1>
          <p style={{ color: C.muted, fontSize: 15, lineHeight: 1.5, margin: '14px auto 0', maxWidth: 360 }}>
            {isRegister
              ? 'Создай аккаунт по email — и агент готов к работе.'
              : 'Войди по email, чтобы увидеть баланс токенов и управлять агентами.'}
          </p>
        </div>

        {/* segmented toggle */}
        <div style={{ display: 'flex', gap: 4, padding: 4, background: C.panel2, border: `1px solid ${C.line}`, borderRadius: 16, marginBottom: 22 }}>
          <button onClick={() => { setTab('login'); setError(null) }} style={tabBtn(!isRegister)} type="button">
            Вход
          </button>
          <button onClick={() => { setTab('register'); setError(null) }} style={tabBtn(isRegister)} type="button">
            Регистрация
          </button>
        </div>

        {/* fields */}
        <div style={{ marginBottom: 16 }}>
          <label style={label}>Email</label>
          <input
            autoComplete="email"
            autoFocus
            onChange={e => setEmail(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.nativeEvent.isComposing && void submit()}
            placeholder="you@example.com"
            style={input}
            type="email"
            value={email}
          />
        </div>
        <div style={{ marginBottom: error ? 12 : 22 }}>
          <label style={label}>Пароль</label>
          <input
            autoComplete={isRegister ? 'new-password' : 'current-password'}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.nativeEvent.isComposing && void submit()}
            placeholder="••••••••"
            style={input}
            type="password"
            value={password}
          />
        </div>

        {error ? (
          <p style={{ color: '#ff6b6b', fontSize: 13, margin: '0 0 16px', textAlign: 'center' }}>{error}</p>
        ) : null}

        {/* primary CTA */}
        <button
          disabled={!canSubmit}
          onClick={() => void submit()}
          style={{
            width: '100%',
            padding: '15px 0',
            borderRadius: 16,
            border: 'none',
            background: C.accent,
            color: C.onAccent,
            fontWeight: 800,
            fontSize: 15,
            cursor: canSubmit ? 'pointer' : 'default',
            opacity: canSubmit ? 1 : 0.55,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 10
          }}
          type="button"
        >
          {saving ? <Spinner /> : null}
          {saving ? 'Секунду…' : isRegister ? 'Зарегистрироваться' : 'Войти'}
        </button>

        {/* divider + telegram (opens the site's login, where Telegram auth lives) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, margin: '22px 0 16px', color: C.faint }}>
          <span style={{ flex: 1, height: 1, background: C.line }} />
          <span style={{ fontSize: 13 }}>или через Telegram</span>
          <span style={{ flex: 1, height: 1, background: C.line }} />
        </div>
        <button
          onClick={() => openSite('/login')}
          style={{
            width: '100%',
            padding: '13px 0',
            borderRadius: 999,
            border: 'none',
            background: C.accent,
            color: '#fff',
            fontWeight: 700,
            fontSize: 14,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 10
          }}
          type="button"
        >
          <TelegramIcon />
          Войти через Telegram
        </button>
      </div>
    </div>
  )
}

function Spinner() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" style={{ animation: 'spin 0.8s linear infinite' }} aria-hidden>
      <style>{'@keyframes spin{to{transform:rotate(360deg)}}'}</style>
      <circle cx="12" cy="12" r="9" fill="none" stroke={C.onAccent} strokeOpacity="0.3" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke={C.onAccent} strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

function TelegramIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
      <path
        fill="#fff"
        d="M9.8 15.6 9.6 19c.4 0 .6-.2.8-.4l1.9-1.8 3.9 2.9c.7.4 1.2.2 1.4-.7l2.6-12c.2-1-.4-1.4-1-1.1L3.3 10.5c-1 .4-.9.9-.1 1.2l4.2 1.3 9.7-6.1c.5-.3.9-.1.5.2z"
      />
    </svg>
  )
}
