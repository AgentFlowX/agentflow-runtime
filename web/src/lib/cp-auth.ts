/**
 * cp-auth.ts — typed client for the AgentFlow control-plane (CP) public auth +
 * account surface. Pure request helpers: NO secret storage and NO Electron
 * session wiring here — those live in the main process (agentflow-auth in
 * electron/), which calls these shapes. The renderer login form uses `login` /
 * `register`; the balance pill uses `me`.
 *
 * Backend contract (apps/cp):
 *   POST /v1/auth/register {email,password} -> { ok, token, expiresAt, user }
 *   POST /v1/auth/login    {email,password} -> same
 *   GET  /v1/me            Bearer token     -> { ok, account:{ balanceTokens, balanceUsdCents, ... } }
 *   GET  /v1/me/key        Bearer token     -> { ok, key:{ alias, masked, baseUrl } }
 *   POST /v1/me/key/rotate Bearer token     -> { ok, key:{ raw, baseUrl, ... } }  (raw issued ONCE)
 */

import { cpUrl } from "./agentflow";

export interface CpUser {
  id: string;
  username: string;
}

export interface CpAuthResult {
  ok: true;
  token: string;
  expiresAt: number | string;
  user: CpUser;
}

export interface CpAccount {
  balanceTokens: number;
  balanceUsdCents: number;
  [k: string]: unknown;
}

export interface CpKey {
  alias?: string;
  masked?: string;
  baseUrl?: string;
  /** raw unified LLM key — present only on the rotate response, once. */
  raw?: string;
}

/** A CP error with a stable machine `code` (from the CP `{error:{code,message}}` body). */
export class CpError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "CpError";
    this.code = code;
    this.status = status;
  }
}

async function cpRequest<T>(
  path: string,
  init: { method?: string; token?: string; body?: unknown } = {},
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (init.token) headers.Authorization = `Bearer ${init.token}`;
  let res: Response;
  try {
    res = await fetch(cpUrl(path), {
      method: init.method ?? "GET",
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    });
  } catch {
    throw new CpError("network", "Нет связи с сервером. Проверь интернет.", 0);
  }
  let data: any = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) {
    const code = data?.error?.code ?? "error";
    const message = data?.error?.message ?? `HTTP ${res.status}`;
    throw new CpError(String(code), String(message), res.status);
  }
  return data as T;
}

/** Human Russian message for a CP error code (login/register surfaces). */
export function cpAuthErrorRu(err: unknown): string {
  if (err instanceof CpError) {
    switch (err.code) {
      case "network":
        return "Нет связи с сервером. Проверь интернет и попробуй снова.";
      case "invalid_credentials":
      case "unauthorized":
        return "Неверный email или пароль.";
      case "email_taken":
        return "Этот email уже зарегистрирован — попробуй войти.";
      case "invalid_email":
        return "Введи корректный email.";
      case "weak_password":
        return "Пароль слишком короткий — минимум 8 символов.";
      default:
        return err.message || "Что-то пошло не так. Попробуй ещё раз.";
    }
  }
  return "Что-то пошло не так. Попробуй ещё раз.";
}

export function login(email: string, password: string): Promise<CpAuthResult> {
  return cpRequest<CpAuthResult>("/v1/auth/login", { method: "POST", body: { email, password } });
}

export function register(email: string, password: string): Promise<CpAuthResult> {
  return cpRequest<CpAuthResult>("/v1/auth/register", { method: "POST", body: { email, password } });
}

export async function me(token: string): Promise<CpAccount> {
  const r = await cpRequest<{ ok: true; account: CpAccount }>("/v1/me", { token });
  return r.account;
}

/** Issue (once) the raw unified LLM key for the local runtime/gateway. */
export async function rotateKey(token: string): Promise<CpKey> {
  const r = await cpRequest<{ ok: true; key: CpKey }>("/v1/me/key/rotate", { method: "POST", token });
  return r.key;
}
