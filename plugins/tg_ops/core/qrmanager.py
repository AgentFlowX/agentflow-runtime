"""
qrmanager.py — QR login that actually works under Hermes.

🔴 Root cause of "QR invalid / expired even though I scanned": tg tool handlers run
via model_tools._run_async, which — inside the gateway's async stack — executes each
handler in a FRESH thread with its OWN event loop that is DISPOSED when the handler
returns. So a Telethon client created in tg_account_qr_start (loop A) is DEAD by the
time tg_account_qr_confirm (loop B) looks at it — nobody is left listening for the
login-token update the scan produces.

Fix (mirrors the old single-script reliability): the whole QR login runs in ONE
PERSISTENT background thread + loop. That thread builds the client, shows the QR,
WAITS for the scan itself (refreshing on expiry, handling 2FA), and registers the
account on success. The tools just submit and poll shared state — the client never
crosses loops.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import threading
import time

from telethon import TelegramClient, errors
from telethon.sessions import StringSession

from . import tgclient, accounts, proxylease, fingerprints
from .db import default_app_id, default_app_hash
from .qr import _render_png

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_start_lock = threading.Lock()
_sessions: dict[str, dict] = {}
_TTL = 600


def _ensure_loop() -> None:
    global _loop, _thread
    with _start_lock:
        if _loop is not None and _thread is not None and _thread.is_alive():
            return
        _loop = asyncio.new_event_loop()
        _thread = threading.Thread(target=_loop.run_forever, name="tg-qr", daemon=True)
        _thread.start()


def _gc() -> None:
    now = time.monotonic()
    for tok in [t for t, s in _sessions.items() if now - s.get("created", now) > _TTL]:
        _sessions.pop(tok, None)


async def _login(token: str, country: str | None) -> None:
    st = _sessions[token]
    client = None
    try:
        proxy = await asyncio.to_thread(proxylease.lease, country)
        proxy_tuple = tgclient.parse_proxy(accounts._parse_proxy(proxy, country)) if proxy else None
        prefer = "ru" if (country or "").lower() in ("kz", "uz", "by", "ru") else None
        device = fingerprints.pick_fingerprint(int(time.time()) % 100000, prefer_lang=prefer)
        client = TelegramClient(StringSession(), int(default_app_id()), default_app_hash(),
                                proxy=proxy_tuple, **fingerprints.as_client_kwargs(device))
        await client.connect()
        qr = await client.qr_login()
        st.update({"qr_url": qr.url, "qr_png": _render_png(qr.url, token),
                   "via_proxy": bool(proxy), "device": device["device_model"], "status": "pending"})
        st["_ready"].set()   # tg_account_qr_start can now return the QR

        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            try:
                await qr.wait(15)
                break                                   # scanned
            except errors.SessionPasswordNeededError:
                st["status"] = "need_password"
                fut = _loop.create_future()             # type: ignore[union-attr]
                st["_pw_fut"] = fut
                try:
                    pw = await asyncio.wait_for(fut, timeout=180)
                except asyncio.TimeoutError:
                    st.update({"status": "error", "error": "2FA password timeout"})
                    return
                await client.sign_in(password=pw)
                break
            except asyncio.TimeoutError:
                if await client.is_user_authorized():
                    break
                try:                                     # refresh an expired code
                    await qr.recreate()
                    st.update({"qr_url": qr.url, "qr_png": _render_png(qr.url, token)})
                except Exception:  # noqa: BLE001
                    pass
                continue

        if not await client.is_user_authorized():
            st["status"] = "expired"
            return
        session_str = client.session.save()
        await client.disconnect()
        client = None
        res = await accounts.add_account(session_str, source="own", proxy=st.get("proxy") or proxy,
                                         country=country, device=json.dumps(device))
        st.update({"status": "done", "result": res})
    except Exception as e:  # noqa: BLE001
        st.update({"status": "error", "error": f"{type(e).__name__}: {e}"})
    finally:
        st["_ready"].set()
        if client is not None:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass


def submit(country: str | None = None) -> dict:
    """Start a QR login in the persistent thread; return once the QR is ready."""
    _ensure_loop()
    _gc()
    token = secrets.token_urlsafe(9)
    _sessions[token] = {"status": "starting", "created": time.monotonic(),
                        "_ready": threading.Event(), "_pw_fut": None, "country": country}
    asyncio.run_coroutine_threadsafe(_login(token, country), _loop)  # type: ignore[arg-type]
    _sessions[token]["_ready"].wait(30)
    st = _sessions[token]
    out = {"ok": st.get("status") != "error", "token": token, "status": st.get("status"),
           "qr_url": st.get("qr_url"), "via_proxy": st.get("via_proxy"), "device": st.get("device"),
           "hint": "Покажи QR юзеру (Telegram → Настройки → Устройства → Подключить устройство), "
                   "затем опрашивай tg_account_qr_confirm с token, пока не станет done."}
    if st.get("qr_png"):
        out["qr_png"] = st["qr_png"]
    if st.get("error"):
        out["error"] = st["error"]
    if not st.get("via_proxy"):
        out["warning"] = "прокси не арендован (PROXY_URL не настроен) — QR может не работать"
    return out


def poll(token: str, password: str | None = None) -> dict:
    """Check a login's status. done → account registered; need_password → pass password."""
    st = _sessions.get(token)
    if not st:
        return {"ok": False, "error": "unknown_or_expired_token"}
    if password and st.get("status") == "need_password" and st.get("_pw_fut") is not None and _loop is not None:
        fut = st["_pw_fut"]
        _loop.call_soon_threadsafe(lambda: (not fut.done()) and fut.set_result(password))
        time.sleep(3)                                    # let sign_in run
    status = st.get("status")
    out = {"ok": True, "token": token, "status": status}
    if status == "done":
        out["result"] = st.get("result")
        _sessions.pop(token, None)
    elif status == "need_password":
        out["need_password"] = True
        out["note"] = "у аккаунта 2FA — вызови confirm ещё раз с password"
    elif status in ("pending", "starting"):
        out["qr_url"] = st.get("qr_url")
        if st.get("qr_png"):
            out["qr_png"] = st["qr_png"]
        out["note"] = "ещё не отсканирован — покажи QR и подожди, потом опроси снова"
    elif status == "expired":
        out["error"] = "qr_expired — начни заново tg_account_qr_start"
        _sessions.pop(token, None)
    elif status == "error":
        out["error"] = st.get("error")
        _sessions.pop(token, None)
    return out
