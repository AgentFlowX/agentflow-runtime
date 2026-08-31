"""
db.py — the core SQLite data layer for tg-ops PRIMITIVES.

This is the *baked* core (ships in the agent image): the minimal tables needed to
own accounts and TALK to people — with no campaign/mailing scaffold. The mailing
module (in the template distribution) extends the SAME SQLite file with its own
Campaign/Lead/Dialog tables that reference `Conversation.id` here; it does not
redefine these.

Design decisions that fix the old engine's coupling:
  • A `Conversation` (account ↔ peer) is a FIRST-CLASS primitive. `Message` hangs
    off a Conversation, NOT off a Dialog→Campaign chain — so "send one message to a
    client and read the reply" needs no Campaign, no Lead, no Dialog.
  • `Account.source` (own | bought) drives the warmup rule: own accounts (QR) are
    `ready` on arrival and never warmed; only bought/new accounts are warmup material.

State lives in ONE SQLite file on the pod's PVC (survives restarts). No HTTP, no
Redis — tools write/read rows here directly. `init_db()` is idempotent (create-all).
"""
from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import SQLModel, Field, create_engine, Session

# Data path is on the PVC; the engine CODE is baked in the image. tg_ops uses its
# OWN db env (TGOPS_DB) — deliberately NOT the legacy distribution engine's
# TGENGINE_DB — so the two never share a SQLite file and collide on the account/proxy
# table schemas. Defaults beside HERMES_HOME (the PVC) for the pod, cwd for tests.
DB_PATH = os.environ.get("TGOPS_DB") or os.path.join(os.environ.get("HERMES_HOME", "."), "tgops.db")
_engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def init_db() -> None:
    """Create any missing tables. Idempotent — never drops or rewrites data."""
    SQLModel.metadata.create_all(_engine)


def get_session() -> Session:
    """Sync SQLModel session. Tools use it directly; async callers wrap in
    asyncio.to_thread (SQLite writes are sub-ms at this scale)."""
    return Session(_engine)


def now() -> datetime:
    return datetime.utcnow()


# --- Telegram app credentials (env-driven, easily swappable) ------------------
# app_id/app_hash identify the CLIENT APP (my.telegram.org), NOT the account — one
# throwaway app pair serves the whole fleet. Baked as image env (TG_API_ID/TG_API_HASH)
# so agents never ask the user for them; overridable per-agent via CP env. Falls back
# to Telegram Desktop's public app (2040) if unset.
def default_app_id() -> int:
    raw = os.environ.get("TG_API_ID")
    try:
        return int(raw) if raw else 2040
    except ValueError:
        return 2040


def default_app_hash() -> str:
    return os.environ.get("TG_API_HASH") or "b18441a1ff607e10a989891a5462e627"


# --- enums -------------------------------------------------------------------
class AccountSource(str, Enum):
    own = "own"          # user's own account, connected via QR — already "warm"
    bought = "bought"    # purchased from the market — new, warmup material


class AccountStatus(str, Enum):
    """Health of a userbot account — the account marks itself via health checks."""
    active = "active"
    spamblock = "spamblock"
    cooldown = "cooldown"
    terminated = "terminated"
    banned = "banned"
    dead = "dead"
    unknown = "unknown"


class WarmupPhase(str, Enum):
    cold = "cold"        # fresh bought account, not warmed
    warming = "warming"
    ready = "ready"      # warm enough (own accounts start here)


class ConversationStatus(str, Enum):
    open = "open"
    closed = "closed"


class MessageFrom(str, Enum):
    account = "account"  # outbound (our userbot)
    user = "user"        # inbound (the person we're talking to)


# --- accounts / proxies ------------------------------------------------------
class Proxy(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = "socks5"
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    country: Optional[str] = None        # must equal the account's country
    created_at: datetime = Field(default_factory=now)


class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # identity — IMMUTABLE once set. session is a native Telethon StringSession.
    session: str
    app_id: int = Field(default_factory=default_app_id)      # from TG_API_ID env
    app_hash: str = Field(default_factory=default_app_hash)  # from TG_API_HASH env
    device: Optional[str] = None         # JSON desktop fingerprint (coherent w/ app 2040)
    dc_id: Optional[int] = None
    tg_id: Optional[int] = None
    phone: Optional[str] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    country: Optional[str] = None
    proxy_id: Optional[int] = Field(default=None, foreign_key="proxy.id")
    # 🔴 origin drives the warmup rule (own = never warmed; bought = warmup material)
    source: AccountSource = AccountSource.bought
    # organization (owner labels accounts by purpose/group)
    purpose: Optional[str] = None
    group_name: Optional[str] = None
    tags: Optional[str] = None           # JSON list
    note: Optional[str] = None
    avatar_path: Optional[str] = None
    # health / scheduling — the account marks itself via health checks
    status: AccountStatus = AccountStatus.unknown
    spamblock_until: Optional[datetime] = None
    last_health_check: Optional[datetime] = None
    is_active: bool = True
    warmup_phase: WarmupPhase = WarmupPhase.cold   # add-primitive sets `ready` for own
    warmup_actions: int = 0
    warmup_requested: bool = False       # opt-in: only set before a mailing (bought)
    # autopilot — the daemon auto-maintains this account's auto_reply dialogs
    autopilot: bool = False
    persona: Optional[str] = None        # system prompt / role for auto-replies
    goal: Optional[str] = None           # goal of this worker's dialogs
    auto_mode: str = "inbound"           # inbound (answer everyone) | outreach (only seeded)
    cooldown_until: Optional[datetime] = None
    deactivated_reason: Optional[str] = None
    last_send_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now)


# --- conversations (the PRIMITIVE — no campaign required) --------------------
class Conversation(SQLModel, table=True):
    """One thread between one of our accounts and one peer. The unit of 'talk to a
    client'. Mailing dialogs later reference this row instead of owning messages."""
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id")
    peer_ref: str                        # @username / t.me link / numeric id as given
    peer_tg_id: Optional[int] = None     # resolved id (dedupe key with account_id)
    peer_username: Optional[str] = None
    peer_name: Optional[str] = None
    kind: str = "dm"                     # dm | group
    title: Optional[str] = None          # optional human label for the thread
    auto_reply: bool = False             # primitives default to MANUAL; agent opts in
    last_in_id: int = 0                  # highest inbound Telegram msg id processed
    last_out_id: int = 0                 # last outbound Telegram msg id we sent
    status: ConversationStatus = ConversationStatus.open
    last_message_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now)


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id")
    sender: MessageFrom
    text: str
    tg_msg_id: Optional[int] = None      # the Telegram message id (dedupe inbound)
    created_at: datetime = Field(default_factory=now)


class SavedTool(SQLModel, table=True):
    """An agent-AUTHORED tool (recipe): a named async Python body the agent wrote from
    the primitives, saved on the PVC and reusable via tg_tool_run. The template layer:
    a curated set of these = a shippable toolset the agent grows itself."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    code: str                            # async body receiving (client, args)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class ActionLog(SQLModel, table=True):
    """Audit trail: what each account did, when, and whether it worked."""
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: Optional[int] = Field(default=None, foreign_key="account.id")
    action: str                          # send | poll | ingest | health_check | ...
    detail: Optional[str] = None
    ok: bool = True
    created_at: datetime = Field(default_factory=now)


# --- shared helpers ----------------------------------------------------------
def log_action(account_id, action: str, detail: str = "", ok: bool = True) -> None:
    """Append an ActionLog row (best-effort; never raises into a caller's flow)."""
    try:
        with get_session() as s:
            s.add(ActionLog(account_id=account_id, action=action,
                            detail=(detail or "")[:400], ok=ok))
            s.commit()
    except Exception:
        pass


if __name__ == "__main__":
    init_db()
    print(f"initialized {DB_PATH}")
