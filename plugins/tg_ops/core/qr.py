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

from . import tgclient, accounts
from .db import default_app_id, default_app_hash

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
    """Begin a QR login. Returns {ok, token, qr_url, qr_png?, hint}."""
    proxy_tuple = None
    if proxy:
        proxy_tuple = tgclient.parse_proxy(accounts._parse_proxy(proxy, country))
    client = TelegramClient(StringSession(), int(app_id or default_app_id()),
                            app_hash or default_app_hash(), proxy=proxy_tuple)
    await client.connect()
    qr = await client.qr_login()
    token = secrets.token_urlsafe(9)
    _pending[token] = {"client": client, "qr": qr, "proxy": proxy,
                       "country": country, "created": time.monotonic()}
    _gc()
    res = {
        "ok": True, "token": token, "qr_url": qr.url,
        "hint": "Покажи QR юзеру (Telegram → Настройки → Устройства → Подключить устройство), "
                "затем вызови tg_account_qr_confirm с этим token.",
    }
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
        # not scanned in time — refresh the code and hand back a new QR
        try:
            await qr.recreate()
        except Exception:
            pass
        out = {"ok": False, "error": "not_scanned_yet", "token": token, "qr_url": qr.url}
        png = _render_png(qr.url, token)
        if png:
            out["qr_png"] = png
        return out
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "token": token}

    # scanned — 2FA may still be pending
    if not await client.is_user_authorized():
        if password:
            try:
                await client.sign_in(password=password)
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"bad_password: {e}", "token": token}
        if not await client.is_user_authorized():
            return {"ok": False, "need_password": True, "token": token}

    session_str = client.session.save()
    proxy, country = p["proxy"], p["country"]
    await tgclient.disconnect(client)
    _pending.pop(token, None)
    # register as OWN (reconnect+verify+fill identity via the normal path)
    return await accounts.add_account(session_str, source="own", proxy=proxy, country=country)
