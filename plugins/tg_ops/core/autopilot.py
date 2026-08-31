"""
autopilot.py — the autonomous DIALOG ENGINE (the reason a dedicated engine exists).

The agent's LLM cron can't sustain many accounts x many concurrent dialogs — waking
the whole agent per message is too expensive and doesn't scale. The autopilot is a
background daemon that, across ALL accounts flagged `autopilot`, polls every open
`auto_reply` conversation, answers new inbound with a small DIRECT LLM call (ai.py),
and sends the reply with human pacing — continuously, without the agent.

🔴 It runs in its OWN thread + event loop with its OWN Telethon connections, so it is
independent of how Hermes invokes tool handlers (a tool-handler loop may not persist;
a dedicated thread does). Started/stopped/inspected via the tg_autopilot_* tools.
"""
from __future__ import annotations

import asyncio
import os
import random
import threading

from sqlmodel import select

from .db import (
    Account, Proxy, Conversation, ConversationStatus, Message, MessageFrom,
    get_session, now,
)
from . import tgclient, ai

TICK = int(os.environ.get("TGOPS_AUTOPILOT_TICK", "20") or "20")
DELAY_MIN = int(os.environ.get("TGOPS_AUTOPILOT_DELAY_MIN", "8") or "8")
DELAY_MAX = int(os.environ.get("TGOPS_AUTOPILOT_DELAY_MAX", "40") or "40")

_thread: threading.Thread | None = None
_loop: asyncio.AbstractEventLoop | None = None
_running = False
_clients: dict = {}
_stats = {"ticks": 0, "replies": 0, "errors": 0}


# --- sync DB helpers (SQLite check_same_thread=False → safe from the daemon thread) --
def _auto_accounts() -> list[Account]:
    with get_session() as s:
        rows = s.exec(select(Account).where(Account.autopilot == True, Account.is_active == True)).all()  # noqa: E712
        for a in rows:
            s.expunge(a)
        return list(rows)


def _auto_convs(account_id: int) -> list[Conversation]:
    with get_session() as s:
        rows = s.exec(select(Conversation).where(
            Conversation.account_id == account_id,
            Conversation.status == ConversationStatus.open,
            Conversation.auto_reply == True,  # noqa: E712
        )).all()
        for c in rows:
            s.expunge(c)
        return list(rows)


def _proxy_for(acc: Account):
    with get_session() as s:
        return s.get(Proxy, acc.proxy_id) if acc.proxy_id else None


def _store_inbound(conv_id: int, msgs: list, max_id: int) -> None:
    with get_session() as s:
        conv = s.get(Conversation, conv_id)
        if conv is None:
            return
        for m in msgs:
            s.add(Message(conversation_id=conv_id, sender=MessageFrom.user,
                          text=m.message or "", tg_msg_id=m.id))
        conv.last_in_id = max(conv.last_in_id, max_id)
        conv.last_message_at = now()
        s.add(conv)
        s.commit()


def _store_outbound(conv_id: int, account_id: int, text: str, tg_msg_id) -> None:
    with get_session() as s:
        conv = s.get(Conversation, conv_id)
        if conv is not None:
            conv.last_out_id = tg_msg_id or conv.last_out_id
            conv.last_message_at = now()
            s.add(conv)
        acc = s.get(Account, account_id)
        if acc is not None:
            acc.last_send_at = now()
            s.add(acc)
        s.add(Message(conversation_id=conv_id, sender=MessageFrom.account, text=text, tg_msg_id=tg_msg_id))
        s.commit()


def _history(conv_id: int, limit: int = 30) -> list[dict]:
    with get_session() as s:
        rows = s.exec(select(Message).where(Message.conversation_id == conv_id)
                      .order_by(Message.id.desc()).limit(limit)).all()
        rows = list(reversed(rows))
        return [{"sender": r.sender.value, "text": r.text} for r in rows]


# --- daemon loop --------------------------------------------------------------
async def _client_for(acc: Account):
    c = _clients.get(acc.id)
    if c is not None and c.is_connected():
        return c
    proxy = await asyncio.to_thread(_proxy_for, acc)
    c = await tgclient.connect(acc, proxy)   # raises AccountError
    _clients[acc.id] = c
    return c


async def _handle_conv(client, acc: Account, conv: Conversation) -> None:
    peer = conv.peer_username or conv.peer_ref or conv.peer_tg_id
    batch = await client.get_messages(peer, min_id=conv.last_in_id, limit=30)
    if not batch:
        return
    max_id = max((getattr(m, "id", 0) or 0) for m in batch)
    inbound = [m for m in batch if not getattr(m, "out", False) and getattr(m, "message", None)]
    if not inbound:
        return
    inbound.reverse()
    await asyncio.to_thread(_store_inbound, conv.id, inbound, max_id)
    history = await asyncio.to_thread(_history, conv.id, 30)
    if not history or history[-1]["sender"] != "user":
        return
    reply = await asyncio.to_thread(ai.generate_reply, acc.persona or "", history)
    if not reply:
        return
    sent = await client.send_message(peer, reply)
    await asyncio.to_thread(_store_outbound, conv.id, acc.id, reply, getattr(sent, "id", None))
    _stats["replies"] += 1
    await asyncio.sleep(random.randint(DELAY_MIN, DELAY_MAX))


async def _tick() -> None:
    for acc in await asyncio.to_thread(_auto_accounts):
        try:
            client = await _client_for(acc)
        except Exception:  # noqa: BLE001 — account down; skip this pass
            _stats["errors"] += 1
            continue
        for conv in await asyncio.to_thread(_auto_convs, acc.id):
            try:
                await _handle_conv(client, acc, conv)
            except Exception:  # noqa: BLE001 — one dialog failing never stops the rest
                _stats["errors"] += 1
    _stats["ticks"] += 1


async def _daemon() -> None:
    while _running:
        try:
            await _tick()
        except Exception:  # noqa: BLE001
            _stats["errors"] += 1
        await asyncio.sleep(TICK)
    for c in list(_clients.values()):
        try:
            await c.disconnect()
        except Exception:  # noqa: BLE001
            pass
    _clients.clear()


def _run() -> None:
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_until_complete(_daemon())


# --- control ------------------------------------------------------------------
def start() -> dict:
    global _thread, _running
    if _running:
        return {"ok": True, "already_running": True, **status()}
    _running = True
    _thread = threading.Thread(target=_run, name="tg-autopilot", daemon=True)
    _thread.start()
    return {"ok": True, "started": True, **status()}


def stop() -> dict:
    global _running
    _running = False
    return {"ok": True, "stopped": True}


def status() -> dict:
    try:
        n = len(_auto_accounts())
    except Exception:  # noqa: BLE001
        n = -1
    return {"running": _running, "auto_accounts": n, **_stats}


# --- config (who the daemon maintains) ---------------------------------------
def configure_account(account_id: int, *, persona: str | None = None, goal: str | None = None,
                      mode: str | None = None, on: bool = True) -> dict:
    """Set an account's autopilot role. mode: inbound (answer everyone) | outreach
    (only dialogs the account started). In inbound mode we also flip its existing open
    conversations to auto_reply so the daemon picks them up."""
    with get_session() as s:
        acc = s.get(Account, account_id)
        if acc is None:
            return {"ok": False, "error": "account not found"}
        if persona is not None:
            acc.persona = persona
        if goal is not None:
            acc.goal = goal
        if mode in ("inbound", "outreach"):
            acc.auto_mode = mode
        acc.autopilot = bool(on)
        s.add(acc)
        # inbound → maintain every open dialog; outreach → only ones the agent seeds
        if bool(on) and acc.auto_mode == "inbound":
            for c in s.exec(select(Conversation).where(
                    Conversation.account_id == account_id,
                    Conversation.status == ConversationStatus.open)).all():
                c.auto_reply = True
                s.add(c)
        s.commit()
        return {"ok": True, "account_id": account_id, "autopilot": acc.autopilot,
                "mode": acc.auto_mode, "persona_set": bool(acc.persona)}


def set_conversation_auto(conversation_id: int, on: bool) -> dict:
    """Take a specific dialog off autopilot (human takeover) or hand it back."""
    with get_session() as s:
        c = s.get(Conversation, conversation_id)
        if c is None:
            return {"ok": False, "error": "conversation not found"}
        c.auto_reply = bool(on)
        s.add(c)
        s.commit()
        return {"ok": True, "conversation_id": conversation_id, "auto_reply": c.auto_reply}
