"""
qr.py — connect the user's OWN account via QR (Telethon qr_login).

Two-call flow so the agent can show the QR before the scan:
  1) qr_start()   → connects a fresh (empty-session) client, gets a login QR, keeps
     the client alive in a pending map, returns {token, qr_url, qr_png?}. The agent
     shows the QR: Telegram → Settings → Devices → Link Desktop Device.
  2) qr_confirm(token) → resumes that client, waits briefly for the scan. On 2FA it
     asks for the password; on success it exports the StringSession and registers the
     account as source=own (ready, never warmed) through the normal add_account path.

The pending client is held in module state — fine because the Hermes agent process is
long-lived and both tool calls run in the same process/event loop. Expired QR codes are
recreated automatically so the agent can re-show a fresh one.
"""
from __future__ import annotations

import asyncio
import os
import secrets
import time
from typing import Optional

from telethon import TelegramClient, errors
from telethon.sessions import StringSession

from . import tgclient, accounts, proxylease, fingerprints
from .db import default_app_id, default_app_hash
import json

_pending: dict[str, dict] = {}
_PENDING_TTL = 600  # seconds a pending QR client is kept before GC


def _gc() -> None:
    now = time.monotonic()
    for tok in [t for t, p in _pending.items() if now - p["created"] > _PENDING_TTL]:
        p = _pending.pop(tok, None)
        if p:
            try:
                asyncio.ensure_future(tgclient.disconnect(p["client"]))
            except Exception:
                pass


def _render_png(url: str, token: str) -> Optional[str]:
    """Best-effort QR PNG into the outbox so the agent can just send the file."""
    try:
        import qrcode  # optional dep
        outdir = os.environ.get("TGOPS_OUTBOX", "/app/outbox")
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, f"tg_qr_{token}.png")
        qrcode.make(url).save(path)
        return path
    except Exception:
        return None


async def qr_start(proxy: Optional[str] = None, country: Optional[str] = None,
                   app_id: Optional[int] = None, app_hash: Optional[str] = None) -> dict:
    """Begin a QR login. Returns {ok, token, qr_url, qr_png?, hint}.

    🔴 The pod can't reach Telegram directly (NetworkPolicy) — so if no proxy is
    given we LEASE one (country-matched), and we ALWAYS build the login client with a
    coherent desktop DEVICE fingerprint. Both the proxy and the device are carried
    onto the account so every later connection stays consistent (device = identity)."""
    # 1) ensure a proxy — direct connect is blocked, that's what makes a QR "invalid"
    if not proxy:
        proxy = await asyncio.to_thread(proxylease.lease, country)
    proxy_tuple = tgclient.parse_proxy(accounts._parse_proxy(proxy, country)) if proxy else None
    # 2) coherent desktop device (Telethon default library signature = obvious tell)
    prefer = "ru" if (country or "").lower() in ("kz", "uz", "by", "ru") else None
    device = fingerprints.pick_fingerprint(int(time.time()) % 100000, prefer_lang=prefer)
    dev_kwargs = fingerprints.as_client_kwargs(device)
    client = TelegramClient(StringSession(), int(app_id or default_app_id()),
                            app_hash or default_app_hash(), proxy=proxy_tuple, **dev_kwargs)
    await client.connect()
    qr = await client.qr_login()
    token = secrets.token_urlsafe(9)
    _pending[token] = {"client": client, "qr": qr, "proxy": proxy, "country": country,
                       "device": json.dumps(device), "created": time.monotonic()}
    _gc()
    res = {
        "ok": True, "token": token, "qr_url": qr.url,
        "via_proxy": bool(proxy), "device": device.get("device_model"),
        "hint": "Покажи QR юзеру (Telegram → Настройки → Устройства → Подключить устройство), "
                "затем вызови tg_account_qr_confirm с этим token.",
    }
    if not proxy:
        res["warning"] = "прокси не арендован (PROXY_URL не настроен) — QR может не работать с пода"
    png = _render_png(qr.url, token)
    if png:
        res["qr_png"] = png
    return res


async def qr_confirm(token: str, password: Optional[str] = None, timeout: int = 30) -> dict:
    """Resume a pending QR login. Returns the registered own account, or a status
    ({need_password} / {not_scanned_yet, qr_url}) so the agent can drive the flow."""
    p = _pending.get(token)
    if not p:
        return {"ok": False, "error": "unknown_or_expired_token"}
    client, qr = p["client"], p["qr"]

    # 1) 🔴 The user may have ALREADY scanned before we polled — check first. This is
    #    the fix for "connected but the agent didn't notice and started over".
    try:
        if await client.is_user_authorized():
            return await _finalize(token, client, p)
    except Exception:  # noqa: BLE001
        pass

    # 2) Wait for the scan. NEVER recreate the QR on a plain timeout — that throws away
    #    a QR the user may be scanning right now (the old destructive bug). Only refresh
    #    when the code has actually EXPIRED.
    try:
        await qr.wait(timeout)
    except errors.SessionPasswordNeededError:
        if not password:
            return {"ok": False, "need_password": True, "token": token}
        try:
            await client.sign_in(password=password)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"bad_password: {e}", "token": token}
    except asyncio.TimeoutError:
        # maybe it authorized right as we timed out
        try:
            if await client.is_user_authorized():
                return await _finalize(token, client, p)
        except Exception:  # noqa: BLE001
            pass
        expired = False
        try:
            if qr.expires is not None:
                expired = qr.expires.timestamp() <= time.time()
        except Exception:  # noqa: BLE001
            expired = False
        if expired:
            try:
                await qr.recreate()
            except Exception:  # noqa: BLE001
                pass
        out = {"ok": False, "error": "qr_expired_refreshed" if expired else "not_scanned_yet",
               "token": token, "qr_url": qr.url}
        png = _render_png(qr.url, token)
        if png:
            out["qr_png"] = png
        return out
    except Exception as e:  # noqa: BLE001
        # a raise during wait doesn't always mean failure — re-check auth
        try:
            if await client.is_user_authorized():
                return await _finalize(token, client, p)
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": str(e), "token": token}

    # 3) wait returned — 2FA may still be pending
    if not await client.is_user_authorized():
        if password:
            try:
                await client.sign_in(password=password)
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"bad_password: {e}", "token": token}
        if not await client.is_user_authorized():
            return {"ok": False, "need_password": True, "token": token}

    return await _finalize(token, client, p)


async def _finalize(token: str, client, p: dict) -> dict:
    """Export the authorized session and register it as the user's own account."""
    session_str = client.session.save()
    proxy, country, device = p.get("proxy"), p.get("country"), p.get("device")
    await tgclient.disconnect(client)
    _pending.pop(token, None)
    return await accounts.add_account(session_str, source="own", proxy=proxy,
                                      country=country, device=device)
