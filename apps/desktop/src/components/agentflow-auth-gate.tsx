import { useStore } from '@nanostores/react'
import { type CSSProperties, useEffect, useState } from 'react'

import { getCpJwt } from '@/lib/cp-auth'
import { $desktopBoot } from '@/store/boot'
import { $gatewayState } from '@/store/session'
import { completeAgentFlowTelegramLogin, loginAgentFlow, type OnboardingContext } from '@/store/onboarding'

// The site's Telegram login redirects the OS browser back to the app via this
// deep link once auth succeeds: hermes://agentflow-auth?token=<CP JWT>. Main's
// generic hermes:// handler parses it to { kind:'agentflow-auth', params:{ token } }
// and forwards it to the renderer over hermes:deep-link.
const TELEGRAM_DEEP_LINK_KIND = 'agentflow-auth'

interface DeepLinkPayload {
  kind: string
  name: string
  params: Record<string, string>
}
interface DeepLinkBridge {
  onDeepLink?: (cb: (payload: DeepLinkPayload) => void) => () => void
  signalDeepLinkReady?: () => void
}
function deepLinkBridge(): DeepLinkBridge | undefined {
  return (window as unknown as { hermesDesktop?: DeepLinkBridge }).hermesDesktop
}

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
  const [tgPending, setTgPending] = useState(false)
  const [error, setError] = useState<null | string>(null)
  // Show a branded loading splash until the local gateway is up — the login
  // action needs it, so before it's ready the form would look interactive but
  // "dead". `open` = the runtime gateway is connected.
  const boot = useStore($desktopBoot)
  const gatewayState = useStore($gatewayState)
  const ready = gatewayState === 'open'

  // Telegram login return path: capture the hermes://agentflow-auth?token=…
  // deep link, then finish exactly like email/password (issue key, point the
  // runtime at our gateway).
  useEffect(() => {
    const bridge = deepLinkBridge()
    if (!bridge?.onDeepLink) {
      return
    }
    const off = bridge.onDeepLink(payload => {
      if (payload?.kind !== TELEGRAM_DEEP_LINK_KIND) {
        return
      }
      const token = payload.params?.token
      if (!token) {
        setTgPending(false)
        setError('Telegram-вход не вернул токен. Попробуй ещё раз.')
        return
      }
      setTgPending(true)
      setError(null)
      const ctx: OnboardingContext = { requestGateway, profile, onCompleted: () => undefined }
      void completeAgentFlowTelegramLogin(token, ctx).then(res => {
        if (res.ok) {
          setAuthed(true)
        } else {
          setTgPending(false)
          setError(res.message ?? 'Не удалось войти через Telegram.')
        }
      })
    })
    // Flush a link that arrived during boot (main queues until a listener is up).
    bridge.signalDeepLinkReady?.()
    return off
  }, [profile, requestGateway])

  if (authed) {
    return null
  }

  // Branded preloader while the app boots / the gateway connects — no dead UI.
  if (!ready) {
    return <AgentFlowSplash message={boot.message} progress={boot.progress} error={boot.error} />
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
          disabled={tgPending}
          onClick={() => {
            setError(null)
            setTgPending(true)
            // The site finishes Telegram auth and redirects back to
            // hermes://agentflow-auth?token=<JWT>, which the deep-link listener
            // above captures. Passing desktop=1 + the redirect target tells the
            // site to hand the token to the app instead of rendering a web session.
            openSite(`/login?desktop=1&redirect=${encodeURIComponent('hermes://agentflow-auth')}`)
          }}
          style={{
            width: '100%',
            padding: '13px 0',
            borderRadius: 999,
            border: 'none',
            background: C.accent,
            color: '#fff',
            fontWeight: 700,
            fontSize: 14,
            cursor: tgPending ? 'default' : 'pointer',
            opacity: tgPending ? 0.6 : 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 10
          }}
          type="button"
        >
          <TelegramIcon />
          {tgPending ? 'Ждём Telegram…' : 'Войти через Telegram'}
        </button>
      </div>
    </div>
  )
}

/** Branded boot preloader — AgentFlow logo, progress, status. Shown until the
 *  gateway is ready so the user never faces a "dead" login UI. */
function AgentFlowSplash({ message, progress, error }: { message?: string; progress?: number; error?: null | string }) {
  const pct = Math.max(3, Math.min(100, Math.round(progress ?? 3)))
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: C.bg,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 22,
        fontFamily: "'Manrope', system-ui, sans-serif"
      }}
    >
      <style>{'@keyframes afpulse{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.06);opacity:.82}}@keyframes afspin{to{transform:rotate(360deg)}}'}</style>
      <div style={{ position: 'relative', width: 96, height: 96, animation: 'afpulse 1.8s ease-in-out infinite' }}>
        <div style={{ position: 'absolute', inset: -14, borderRadius: '50%', background: C.accent, filter: 'blur(28px)', opacity: 0.35 }} />
        <svg width="96" height="96" viewBox="0 0 100 100" style={{ position: 'relative' }} aria-hidden>
          <circle cx="50" cy="50" r="46" fill={C.accent} />
          <path d="M42 30 L62 50 L42 70" fill="none" stroke={C.onAccent} strokeWidth="13" strokeLinecap="square" />
        </svg>
      </div>
      <div style={{ fontFamily: FONT_DISPLAY, fontWeight: 800, fontSize: 22, letterSpacing: '-.01em', color: C.ink }}>AgentFlow</div>
      <div style={{ width: 220, height: 4, borderRadius: 999, background: C.panel2, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: C.accent, borderRadius: 999, transition: 'width .3s ease' }} />
      </div>
      <div style={{ fontFamily: FONT_MONO, fontSize: 12, letterSpacing: '.04em', color: error ? '#ff6b6b' : C.muted, maxWidth: 360, textAlign: 'center' }}>
        {error ? error : message && !/hermes/i.test(message) ? message : 'Запуск AgentFlow…'}
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
