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

async function cpRequest<T>(
  path: string,
  init: { method?: string; token?: string; body?: unknown } = {}
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (init.token) headers.Authorization = `Bearer ${init.token}`
  let res: Response
  try {
    res = await fetch(cpUrl(path), {
      method: init.method ?? 'GET',
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body)
    })
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
    const err = (data as { error?: { code?: string; message?: string } })?.error
    throw new CpError(String(err?.code ?? 'error'), String(err?.message ?? `HTTP ${res.status}`), res.status)
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
  try {
    window.localStorage.setItem(JWT_KEY, token)
  } catch {
    /* localStorage unavailable */
  }
}

export function getCpJwt(): string | null {
  try {
    return window.localStorage.getItem(JWT_KEY)
  } catch {
    return null
  }
}

export function clearCpJwt(): void {
  try {
    window.localStorage.removeItem(JWT_KEY)
  } catch {
    /* ignore */
  }
}
