"""
ops.py — generic Telegram OPERATOR primitives: search, browse, read, crawl, join.

These turn tg_ops from "send/receive" into "do anything on Telegram from an account":
find channels/chats/people, see what an account is in, read a feed, pull a group's
members (find clients), and join. Everything runs through the persistent pool and
resolves peers the same way as send. Hard account failures raise AccountError.
"""
from __future__ import annotations

from typing import Optional

from telethon.tl import functions

from . import pool, tgclient


async def search_public(account_id: int, query: str, limit: int = 20) -> list[dict]:
    """Search PUBLIC channels/chats/users by name/keyword (contacts.Search)."""
    client = await pool.get(account_id)
    try:
        res = await client(functions.contacts.SearchRequest(q=query, limit=max(1, min(limit, 50))))
    except Exception as e:  # noqa: BLE001
        raise tgclient._classify(e)
    out: list[dict] = []
    for c in getattr(res, "chats", []) or []:
        out.append({
            "type": "channel" if getattr(c, "broadcast", False) else "group",
            "id": getattr(c, "id", None), "username": getattr(c, "username", None),
            "title": getattr(c, "title", None), "participants": getattr(c, "participants_count", None),
        })
    for u in getattr(res, "users", []) or []:
        out.append({
            "type": "user", "id": getattr(u, "id", None), "username": getattr(u, "username", None),
            "name": getattr(u, "first_name", None), "bot": getattr(u, "bot", False),
        })
    return out


async def list_dialogs(account_id: int, limit: int = 50) -> list[dict]:
    """List the account's own chats/channels/DMs (what it's already in)."""
    client = await pool.get(account_id)
    out: list[dict] = []
    try:
        async for d in client.iter_dialogs(limit=max(1, min(limit, 200))):
            e = d.entity
            kind = ("channel" if getattr(e, "broadcast", False)
                    else "group" if getattr(e, "megagroup", False)
                    else "dm")
            out.append({
                "id": getattr(e, "id", None), "username": getattr(e, "username", None),
                "title": getattr(e, "title", None) or getattr(e, "first_name", None),
                "kind": kind, "unread": getattr(d, "unread_count", 0),
            })
    except Exception as e:  # noqa: BLE001
        raise tgclient._classify(e)
    return out


async def read_peer(account_id: int, peer: str, limit: int = 30) -> list[dict]:
    """Read recent messages from any channel/chat/user (read-only feed scroll)."""
    client = await pool.get(account_id)
    try:
        entity = await tgclient.resolve(client, peer)
        msgs: list[dict] = []
        async for m in client.iter_messages(entity, limit=max(1, min(limit, 100))):
            if getattr(m, "message", None):
                msgs.append({"id": m.id, "from": getattr(m, "sender_id", None),
                             "text": m.message, "date": m.date.isoformat() if m.date else None})
        msgs.reverse()
        return msgs
    except tgclient.AccountError:
        raise
    except Exception as e:  # noqa: BLE001
        raise tgclient._classify(e)


async def participants(account_id: int, peer: str, limit: int = 100, search: str = "") -> list[dict]:
    """List members of a group/channel — the raw material for finding clients."""
    client = await pool.get(account_id)
    try:
        entity = await tgclient.resolve(client, peer)
        out: list[dict] = []
        async for u in client.iter_participants(entity, limit=max(1, min(limit, 500)), search=search or ""):
            out.append({"id": getattr(u, "id", None), "username": getattr(u, "username", None),
                        "name": getattr(u, "first_name", None), "bot": getattr(u, "bot", False)})
        return out
    except tgclient.AccountError:
        raise
    except Exception as e:  # noqa: BLE001
        raise tgclient._classify(e)


async def join(account_id: int, peer: str) -> dict:
    """Join a public channel/group so the account can read/act in it."""
    client = await pool.get(account_id)
    try:
        entity = await tgclient.resolve(client, peer)
        await client(functions.channels.JoinChannelRequest(entity))
        return {"joined": getattr(entity, "username", None) or getattr(entity, "id", None)}
    except tgclient.AccountError:
        raise
    except Exception as e:  # noqa: BLE001
        raise tgclient._classify(e)
