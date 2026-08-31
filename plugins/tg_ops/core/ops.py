"""
ops.py — generic Telegram OPERATOR primitives: search, browse, read, crawl, join.

These turn tg_ops from "send/receive" into "do anything on Telegram from an account":
find channels/chats/people, see what an account is in, read a feed, pull a group's
members (find clients), and join. Everything runs through the persistent pool and
resolves peers the same way as send. Hard account failures raise AccountError.
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

from telethon.tl import functions, types

from . import pool, tgclient


def _stringify(v, limit: int = 6000):
    """Make an arbitrary Telethon/Python result JSON-safe (objects → their str)."""
    import json
    try:
        return json.loads(json.dumps(v, default=str))
    except Exception:  # noqa: BLE001
        return str(v)[:limit]


async def exec_code(account_id: int, code: str, timeout: int = 60) -> dict:
    """🔴 ESCAPE HATCH — run an async Python snippet with the CONNECTED Telethon
    `client` (+ `functions`, `types`, `tgclient`) in scope, and return whatever it
    produces. This is how the agent does ANYTHING Telegram's API supports without a
    dedicated tool: delete/edit/pin messages, create channels/groups, forward, react,
    invite, stats, raw MTProto — you name it. `code` is the BODY of an async function
    receiving `client`; return a value to get it back. Runs on the USER'S OWN account.

    Example code: `msg = await client.send_message('me', 'hi'); return msg.id`
    """
    client = await pool.get(account_id)
    glb = {"client": client, "functions": functions, "types": types,
           "asyncio": asyncio, "tgclient": tgclient, "re": re}
    src = "async def __run(client):\n" + "\n".join("    " + ln for ln in (code or "").splitlines())
    loc: dict = {}
    try:
        exec(src, glb, loc)  # noqa: S102 — intentional escape hatch on the user's own account
        res = await asyncio.wait_for(loc["__run"](client), timeout=max(5, timeout))
    except tgclient.AccountError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "result": _stringify(res)}


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


_TOKEN_RE = re.compile(r"(\d{8,10}:[A-Za-z0-9_-]{35})")


async def _bf_exchange(client, bf: str, text: str, timeout: int = 30) -> str:
    """Send one line to @BotFather and return its NEXT reply text (polls up to timeout)."""
    before = await client.get_messages(bf, limit=1)
    before_id = before[0].id if before else 0
    await tgclient.send_message(client, bf, text)
    for _ in range(max(5, timeout)):
        await asyncio.sleep(1)
        msgs = await client.get_messages(bf, limit=4)
        newer = [m for m in msgs if getattr(m, "id", 0) > before_id
                 and not getattr(m, "out", False) and getattr(m, "message", None)]
        if newer:
            newer.sort(key=lambda m: m.id)
            return newer[-1].message
    return ""


async def create_bot(account_id: int, name: str, username: str) -> dict:
    """Create a Telegram bot by scripting the @BotFather conversation from an account.
    Returns {ok, username, token} on success, or {ok:false, note} (e.g. username taken)."""
    client = await pool.get(account_id)
    try:
        uname = username if username.lower().endswith("bot") else f"{username}bot"
        await _bf_exchange(client, "BotFather", "/newbot")        # → "choose a name"
        await _bf_exchange(client, "BotFather", name)             # → "choose a username"
        reply = await _bf_exchange(client, "BotFather", uname)    # → token or error
        m = _TOKEN_RE.search(reply or "")
        if m:
            return {"ok": True, "username": uname, "token": m.group(1)}
        return {"ok": False, "username": uname,
                "note": (reply or "no token — username may be taken; try another")[:300]}
    except tgclient.AccountError:
        raise
    except Exception as e:  # noqa: BLE001
        raise tgclient._classify(e)
