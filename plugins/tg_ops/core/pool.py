"""
pool.py — a persistent Telethon client pool.

The old engine connected → acted → disconnected on EVERY action (CLI-per-call), so
each message/poll paid a full MTProto handshake and Telegram saw constant re-logins.
Inside the long-lived Hermes agent process the tool handlers share one event loop, so
we keep clients CONNECTED and reuse them across calls, evicting the least-recently-used
past a cap. One asyncio.Lock per account serializes (re)connect so two concurrent tool
calls never build two clients for the same account.

Everything is keyed by Account.id. Hard failures surface as tgclient.AccountError so
callers can cooldown/deactivate the account.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Optional

from telethon import TelegramClient

from .db import Account, Proxy, get_session
from . import tgclient

MAX_CLIENTS = int(os.environ.get("TGENGINE_POOL_MAX", "20") or "20")

_clients: dict[int, TelegramClient] = {}
_last_used: dict[int, float] = {}
_locks: dict[int, asyncio.Lock] = {}
_pool_lock = asyncio.Lock()


def _load(account_id: int) -> tuple[Account, Optional[Proxy]]:
    """Load the Account (+ its Proxy) from the DB (sync; call via to_thread)."""
    with get_session() as s:
        acc = s.get(Account, account_id)
        if acc is None:
            raise tgclient.AccountError("error", f"account {account_id} not found")
        proxy = s.get(Proxy, acc.proxy_id) if acc.proxy_id else None
        return acc, proxy


async def _lock_for(account_id: int) -> asyncio.Lock:
    async with _pool_lock:
        return _locks.setdefault(account_id, asyncio.Lock())


async def get(account_id: int) -> TelegramClient:
    """Return a CONNECTED client for the account, reusing the cached one when live.

    Raises tgclient.AccountError (dead/banned/flood/proxy) if the account can't
    connect — the caller decides how to cooldown/deactivate.
    """
    lock = await _lock_for(account_id)
    async with lock:
        cached = _clients.get(account_id)
        if cached is not None and cached.is_connected():
            _last_used[account_id] = time.monotonic()
            return cached
        # stale/missing → drop it and (re)connect fresh
        if cached is not None:
            await tgclient.disconnect(cached)
            _clients.pop(account_id, None)

        acc, proxy = await asyncio.to_thread(_load, account_id)
        client = await tgclient.connect(acc, proxy)   # raises AccountError on failure
        _clients[account_id] = client
        _last_used[account_id] = time.monotonic()

    await _evict_if_over_cap(keep=account_id)
    return client


async def _evict_if_over_cap(keep: int) -> None:
    """Disconnect least-recently-used clients until we're back under MAX_CLIENTS."""
    if len(_clients) <= MAX_CLIENTS:
        return
    victims = sorted((t, aid) for aid, t in _last_used.items() if aid != keep)
    while len(_clients) > MAX_CLIENTS and victims:
        _, aid = victims.pop(0)
        await close(aid)


async def close(account_id: int) -> None:
    """Disconnect + evict one account's client (best-effort)."""
    client = _clients.pop(account_id, None)
    _last_used.pop(account_id, None)
    if client is not None:
        await tgclient.disconnect(client)


async def close_all() -> None:
    """Tear down every pooled client (shutdown/best-effort)."""
    for account_id in list(_clients.keys()):
        await close(account_id)
