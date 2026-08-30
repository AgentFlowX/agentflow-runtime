"""
messaging.py — the "talk to a client" PRIMITIVE.

send / poll_inbound / history / list_conversations — everything you need to hold a
conversation from one or MANY accounts, with NO Campaign, NO Lead, NO warmup gate.
A `Conversation` (account ↔ peer) is created on first send (or first inbound); every
message is stored against it. `poll_inbound` fans out across accounts via the pool,
so "read new replies from all my accounts" is one call.

All MTProto goes through the persistent `pool`; all DB is sync SQLModel wrapped in
asyncio.to_thread. Hard account failures propagate as tgclient.AccountError.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Optional

from sqlmodel import select

from .db import (
    Account, Conversation, ConversationStatus, Message, MessageFrom,
    get_session, now, log_action,
)
from . import pool, tgclient


# --- helpers -----------------------------------------------------------------
def _peer_fields(entity) -> tuple[Optional[int], Optional[str], Optional[str], str]:
    """Extract (tg_id, username, name, kind) from a resolved Telethon entity."""
    tg_id = getattr(entity, "id", None)
    username = getattr(entity, "username", None)
    name = getattr(entity, "first_name", None) or getattr(entity, "title", None)
    is_group = bool(getattr(entity, "megagroup", False) or getattr(entity, "broadcast", False)
                    or getattr(entity, "title", None))
    return tg_id, username, name, ("group" if is_group else "dm")


def _get_or_create_conversation(s, account_id, entity, peer_ref, conversation_id):
    """Load the given conversation, or find/create one for (account, peer)."""
    if conversation_id:
        conv = s.get(Conversation, conversation_id)
        if conv is not None:
            return conv
    tg_id, username, name, kind = _peer_fields(entity)
    conv = None
    if tg_id is not None:
        conv = s.exec(
            select(Conversation).where(
                Conversation.account_id == account_id,
                Conversation.peer_tg_id == tg_id,
            )
        ).first()
    if conv is None:
        conv = Conversation(account_id=account_id, peer_ref=peer_ref, peer_tg_id=tg_id,
                            peer_username=username, peer_name=name, kind=kind)
        s.add(conv)
        s.commit()
        s.refresh(conv)
    return conv


# --- primitives --------------------------------------------------------------
async def send(account_id: int, peer_ref: str, text: str, *, conversation_id: Optional[int] = None) -> dict:
    """Send `text` to a peer from an account; upsert the Conversation + store the
    outbound Message. Returns {ok, conversation_id, tg_msg_id, peer_tg_id}."""
    client = await pool.get(account_id)
    entity = await tgclient.resolve(client, peer_ref)          # raises AccountError
    tg_msg_id = await tgclient.send_message(client, entity, text)

    def _persist():
        with get_session() as s:
            conv = _get_or_create_conversation(s, account_id, entity, peer_ref, conversation_id)
            conv.last_out_id = tg_msg_id or conv.last_out_id
            conv.last_message_at = now()
            conv.status = ConversationStatus.open
            s.add(Message(conversation_id=conv.id, sender=MessageFrom.account,
                          text=text, tg_msg_id=tg_msg_id))
            acc = s.get(Account, account_id)
            if acc is not None:
                acc.last_send_at = now()
                s.add(acc)
            s.add(conv)
            s.commit()
            return conv.id, conv.peer_tg_id

    conv_id, peer_tg_id = await asyncio.to_thread(_persist)
    log_action(account_id, "send", f"conv={conv_id}", ok=True)
    return {"ok": True, "conversation_id": conv_id, "tg_msg_id": tg_msg_id, "peer_tg_id": peer_tg_id}


def _select_conversations(account_id, conversation_id) -> list[Conversation]:
    with get_session() as s:
        q = select(Conversation).where(Conversation.status == ConversationStatus.open)
        if conversation_id is not None:
            q = select(Conversation).where(Conversation.id == conversation_id)
        elif account_id is not None:
            q = q.where(Conversation.account_id == account_id)
        return list(s.exec(q).all())


async def poll_inbound(account_id: Optional[int] = None, conversation_id: Optional[int] = None,
                       *, limit: int = 30) -> list[dict]:
    """Fetch NEW inbound messages for open conversations (optionally scoped to one
    account or one conversation), fanning out across accounts via the pool. Stores
    each new inbound Message and advances the per-conversation cursor. Returns a flat
    list of {conversation_id, account_id, peer_tg_id, text, tg_msg_id}."""
    convs = await asyncio.to_thread(_select_conversations, account_id, conversation_id)
    by_account: dict[int, list[Conversation]] = defaultdict(list)
    for c in convs:
        by_account[c.account_id].append(c)

    collected: list[dict] = []
    for acc_id, clist in by_account.items():
        try:
            client = await pool.get(acc_id)
        except tgclient.AccountError:
            continue  # account down — skip its conversations this pass (health handles it)
        for conv in clist:
            peer = conv.peer_username or conv.peer_ref or conv.peer_tg_id
            try:
                batch = await client.get_messages(peer, min_id=conv.last_in_id, limit=limit)
            except Exception:
                continue
            if not batch:
                continue
            max_id = max((getattr(m, "id", 0) or 0) for m in batch)
            inbound = [m for m in batch if not getattr(m, "out", False) and getattr(m, "message", None)]
            inbound.reverse()  # get_messages is newest-first → store chronologically

            def _persist():
                with get_session() as s:
                    fresh = s.get(Conversation, conv.id)
                    if fresh is None:
                        return []
                    saved = []
                    for m in inbound:
                        s.add(Message(conversation_id=fresh.id, sender=MessageFrom.user,
                                      text=m.message or "", tg_msg_id=m.id))
                        saved.append({"conversation_id": fresh.id, "account_id": acc_id,
                                      "peer_tg_id": fresh.peer_tg_id, "text": m.message or "",
                                      "tg_msg_id": m.id})
                    fresh.last_in_id = max(fresh.last_in_id, max_id)
                    if inbound:
                        fresh.last_message_at = now()
                    s.add(fresh)
                    s.commit()
                    return saved

            saved = await asyncio.to_thread(_persist)
            collected.extend(saved)
    return collected


def history(conversation_id: int, limit: int = 50) -> list[dict]:
    """Read the stored messages of a conversation, oldest→newest."""
    with get_session() as s:
        rows = s.exec(
            select(Message).where(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc()).limit(limit)
        ).all()
        rows = list(reversed(rows))
        return [{"sender": r.sender.value, "text": r.text, "tg_msg_id": r.tg_msg_id,
                 "at": r.created_at.isoformat()} for r in rows]


def list_conversations(account_id: Optional[int] = None, status: str = "open", limit: int = 100) -> list[dict]:
    """List conversations (optionally by account), newest activity first."""
    with get_session() as s:
        q = select(Conversation)
        if status and status != "all":
            q = q.where(Conversation.status == ConversationStatus(status))
        if account_id is not None:
            q = q.where(Conversation.account_id == account_id)
        rows = list(s.exec(q).all())
        rows.sort(key=lambda c: (c.last_message_at or c.created_at), reverse=True)
        return [{"conversation_id": c.id, "account_id": c.account_id, "peer_ref": c.peer_ref,
                 "peer_tg_id": c.peer_tg_id, "peer_username": c.peer_username, "peer_name": c.peer_name,
                 "kind": c.kind, "auto_reply": c.auto_reply, "status": c.status.value,
                 "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None}
                for c in rows[:limit]]
