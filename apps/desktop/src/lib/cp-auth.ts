/**
 * cp-auth.ts (desktop) — typed client for the AgentFlow control-plane public
 * auth + account surface. Self-contained (no cross-package import): the desktop
 * renderer uses this for the email/password login screen and the balance pill.
 *
 * Backend (apps/cp):
 *   POST /v1/auth/register {email,password} -> { ok, token, expiresAt, user }
 *   POST /v1/auth/login    {email,password} -> same
 *   GET  /v1/me            Bearer           -> { ok, account:{ balanceTokens, balanceUsdCents, ... } }
 *   POST /v1/me/key/rotate Bearer           -> { ok, key:{ raw, baseUrl, ... } }  (raw issued ONCE)
 */

const RAW_CP_URL =
  (import.meta.env.VITE_AGENTFLOW_CP_URL as string | undefined) ??
  'https://cp.agentflow.website:8797'

/** Normalised CP origin, no trailing slash. */
export const AGENTFLOW_CP_URL = RAW_CP_URL.replace(/\/+$/, '')

function cpUrl(path: string): string {
  return `${AGENTFLOW_CP_URL}${path.startsWith('/') ? path : `/${path}`}`
}

export interface CpAuthResult {
  ok: true
  token: string
  expiresAt: number | string
  user: { id: string; username: string }
}

export interface CpAccount {
  balanceTokens: number
  balanceUsdCents: number
  [k: string]: unknown
}

export interface CpKey {
  alias?: string
  masked?: string
  baseUrl?: string
  /** raw unified LLM key — present only on the rotate response, once. */
  raw?: string
}

export class CpError extends Error {
  code: string
  status: number
  constructor(code: string, message: string, status: number) {
    super(message)
    this.name = 'CpError'
    this.code = code
    this.status = status
  }
}

/* ---- Electron MAIN-process bridge (CORS-free CP transport) ----------------
 * The Electron renderer is a Chromium page (origin app://… or http://127.0.0.1)
 * so a direct fetch() to cp.agentflow.website is cross-origin — and CP does NOT
 * emit Access-Control-Allow-Origin, so Chromium blocks the response and the
 * fetch promise rejects ("Нет связи с сервером"). The Electron MAIN process
 * (Node/`net`) has NO CORS restriction, so we route CP requests through it via
 * the preload bridge (window.hermesDesktop.agentflow.cpFetch). We fall back to
 * a direct fetch only in a plain browser (dev web dashboard, no bridge). */
interface CpBridgeResponse {
  ok: boolean
  status: number
  data: unknown
}
interface CpDesktopBridge {
  cpFetch?: (p: { url: string; method: string; token?: string; body?: string }) => Promise<CpBridgeResponse>
  cpTokenGet?: () => Promise<string | null>
  cpTokenSet?: (token: string) => Promise<unknown> | void
  cpTokenClear?: () => Promise<unknown> | void
}
function cpBridge(): CpDesktopBridge | undefined {
  return (window as unknown as { hermesDesktop?: { agentflow?: CpDesktopBridge } }).hermesDesktop?.agentflow
}

function mapCpErrorBody(data: unknown, status: number): CpError {
  const err = (data as { error?: { code?: string; message?: string } })?.error
  return new CpError(String(err?.code ?? 'error'), String(err?.message ?? `HTTP ${status}`), status)
}

async function cpRequest<T>(
  path: string,
  init: { method?: string; token?: string; body?: unknown } = {}
): Promise<T> {
  const url = cpUrl(path)
  const method = init.method ?? 'GET'
  const bodyStr = init.body === undefined ? undefined : JSON.stringify(init.body)

  // Preferred path: Electron MAIN process — no CORS. cpFetch resolves with
  // { ok, status, data } for any HTTP response (incl. 401) and only rejects on
  // a genuine transport failure.
  const bridge = cpBridge()
  if (bridge?.cpFetch) {
    let r: CpBridgeResponse
    try {
      r = await bridge.cpFetch({ url, method, token: init.token, body: bodyStr })
    } catch {
      throw new CpError('network', 'Нет связи с сервером. Проверь интернет.', 0)
    }
    if (!r.ok) {
      throw mapCpErrorBody(r.data, r.status)
    }
    return r.data as T
  }

  // Fallback: plain browser (dev web) where same-origin / CORS is fine.
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (init.token) headers.Authorization = `Bearer ${init.token}`
  let res: Response
  try {
    res = await fetch(url, { method, headers, body: bodyStr })
  } catch {
    throw new CpError('network', 'Нет связи с сервером. Проверь интернет.', 0)
  }
  let data: unknown = null
  try {
    data = await res.json()
  } catch {
    /* non-JSON */
  }
  if (!res.ok) {
    throw mapCpErrorBody(data, res.status)
  }
  return data as T
}

/** Human Russian message for a CP auth error. */
export function cpAuthErrorRu(err: unknown): string {
  if (err instanceof CpError) {
    switch (err.code) {
      case 'network':
        return 'Нет связи с сервером. Проверь интернет и попробуй снова.'
      case 'invalid_credentials':
      case 'unauthorized':
        return 'Неверный email или пароль.'
      case 'email_taken':
        return 'Этот email уже зарегистрирован — попробуй войти.'
      case 'invalid_email':
        return 'Введи корректный email.'
      case 'weak_password':
        return 'Пароль слишком короткий — минимум 8 символов.'
      default:
        return err.message || 'Что-то пошло не так. Попробуй ещё раз.'
    }
  }
  return 'Что-то пошло не так. Попробуй ещё раз.'
}

export function cpLogin(email: string, password: string): Promise<CpAuthResult> {
  return cpRequest<CpAuthResult>('/v1/auth/login', { method: 'POST', body: { email, password } })
}

export function cpRegister(email: string, password: string): Promise<CpAuthResult> {
  return cpRequest<CpAuthResult>('/v1/auth/register', { method: 'POST', body: { email, password } })
}

export async function cpMe(token: string): Promise<CpAccount> {
  const r = await cpRequest<{ ok: true; account: CpAccount }>('/v1/me', { token })
  return r.account
}

/** Issue (once) the raw unified LLM key for the local runtime/gateway. */
export async function cpRotateKey(token: string): Promise<CpKey> {
  const r = await cpRequest<{ ok: true; key: CpKey }>('/v1/me/key/rotate', { method: 'POST', token })
  return r.key
}

/* ---- JWT session (renderer-side, for balance/account calls) --------------- */

const JWT_KEY = 'agentflow-cp-jwt-v1'

export function storeCpJwt(token: string): void {
  // Renderer cache — synchronous, read by the balance pill and the gate's
  // initial authed check.
  try {
    window.localStorage.setItem(JWT_KEY, token)
  } catch {
    /* localStorage unavailable */
  }
  // Durable + secure copy in the Electron MAIN process (OS keychain via
  // safeStorage). Fire-and-forget: the localStorage cache is authoritative for
  // the current session, this only survives a cache clear / reinstall.
  try {
    void cpBridge()?.cpTokenSet?.(token)
  } catch {
    /* bridge absent (dev web) */
  }
}

export function getCpJwt(): string | null {
  try {
    return window.localStorage.getItem(JWT_KEY)
  } catch {
    return null
  }
}

/**
 * Seed the renderer cache from the MAIN-process safeStorage store when the
 * localStorage cache is empty (fresh window / cleared cache). Call once before
 * deciding whether to show the auth gate so a returning user stays signed in.
 */
export async function hydrateCpJwtFromMain(): Promise<string | null> {
  const cached = getCpJwt()
  if (cached) {
    return cached
  }
  const bridge = cpBridge()
  if (!bridge?.cpTokenGet) {
    return null
  }
  try {
    const token = await bridge.cpTokenGet()
    if (token) {
      try {
        window.localStorage.setItem(JWT_KEY, token)
      } catch {
        /* ignore */
      }
      return token
    }
  } catch {
    /* ignore */
  }
  return null
}

export function clearCpJwt(): void {
  try {
    window.localStorage.removeItem(JWT_KEY)
  } catch {
    /* ignore */
  }
  try {
    void cpBridge()?.cpTokenClear?.()
  } catch {
    /* ignore */
  }
}
