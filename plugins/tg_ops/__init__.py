"""
tg_ops — native Telegram-userbot PRIMITIVES, baked into the agent image.

The CORE the dynamic agent stands on: own/buy accounts, and TALK to people from one
or many accounts — with no campaign and no warmup gate. Mailing/warmup are separate
opt-in modules (template distribution) that build on these same tables.

Tools (toolset ``tg_ops``):
  tg_account_add    register + verify a session (source=own|bought)
  tg_account_list   list accounts with health + source
  tg_send           send a message from an account (creates/updates a Conversation)
  tg_poll           fetch NEW inbound across accounts (multi-account in one call)
  tg_conversations  list conversations, or read one thread's history

Deps (telethon, sqlmodel) ship in the image. `check_fn` gates the tools off cleanly
where they're absent, so the plugin never breaks agent boot on a bare host.
"""
from __future__ import annotations

from tools.registry import tool_result, tool_error


def _available(*_a, **_k) -> bool:
    try:
        import telethon  # noqa: F401
        import sqlmodel   # noqa: F401
        return True
    except Exception:
        return False


# --- handlers (lazy-import core so a missing dep never breaks plugin load) ----
async def _h_account_add(args: dict, **_kw) -> str:
    from .core import accounts
    try:
        if not args.get("session"):
            return tool_error("session required (Telethon StringSession)")
        r = await accounts.add_account(
            args["session"], source=args.get("source", "bought"),
            proxy=args.get("proxy"), country=args.get("country"),
            purpose=args.get("purpose"), group=args.get("group"),
        )
        return tool_result(r)
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


def _h_account_list(args: dict, **_kw) -> str:
    from .core import accounts
    try:
        return tool_result(accounts.list_accounts(
            source=args.get("source"), status=args.get("status"), group=args.get("group")))
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


async def _h_qr_start(args: dict, **_kw) -> str:
    from .core import qr
    try:
        r = await qr.qr_start(proxy=args.get("proxy"), country=args.get("country"))
        return tool_result(r)
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


async def _h_qr_confirm(args: dict, **_kw) -> str:
    from .core import qr
    try:
        if not args.get("token"):
            return tool_error("token required (from tg_account_qr_start)")
        r = await qr.qr_confirm(args["token"], password=args.get("password"),
                                timeout=int(args.get("timeout", 30)))
        return tool_result(r)
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


async def _h_send(args: dict, **_kw) -> str:
    from .core import messaging
    try:
        r = await messaging.send(int(args["account_id"]), args["peer"], args["text"],
                                 conversation_id=args.get("conversation_id"))
        return tool_result(r)
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


async def _h_poll(args: dict, **_kw) -> str:
    from .core import messaging
    try:
        msgs = await messaging.poll_inbound(
            account_id=args.get("account_id"), conversation_id=args.get("conversation_id"),
            limit=int(args.get("limit", 30)))
        return tool_result({"new": msgs, "count": len(msgs)})
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


def _h_conversations(args: dict, **_kw) -> str:
    from .core import messaging
    try:
        if args.get("conversation_id"):
            return tool_result({"history": messaging.history(
                int(args["conversation_id"]), limit=int(args.get("limit", 50)))})
        return tool_result({"conversations": messaging.list_conversations(
            account_id=args.get("account_id"), status=args.get("status", "open"))})
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


# --- schemas -----------------------------------------------------------------
_S_ACCOUNT_ADD = {
    "name": "tg_account_add",
    "description": "Register a Telegram account from a Telethon StringSession and verify it connects. "
                   "source=own for the user's own account (via QR — never warmed), source=bought for a "
                   "purchased account (warmup material). Optionally attach a proxy of the account's country.",
    "parameters": {
        "type": "object",
        "properties": {
            "session": {"type": "string", "description": "Telethon StringSession"},
            "source": {"type": "string", "enum": ["own", "bought"], "description": "own = user's (QR, no warmup); bought = market"},
            "proxy": {"type": "string", "description": "socks5://user:pass@host:port (country must match account)"},
            "country": {"type": "string", "description": "ISO-2 country of the account/proxy, e.g. US"},
            "purpose": {"type": "string"},
            "group": {"type": "string", "description": "named fleet/group label"},
        },
        "required": ["session"],
    },
}
_S_ACCOUNT_LIST = {
    "name": "tg_account_list",
    "description": "List registered accounts with health, source (own/bought), warmup phase and proxy. Never returns sessions.",
    "parameters": {
        "type": "object",
        "properties": {
            "source": {"type": "string", "enum": ["own", "bought"]},
            "status": {"type": "string", "description": "active|spamblock|cooldown|dead|banned|unknown"},
            "group": {"type": "string"},
        },
    },
}
_S_QR_START = {
    "name": "tg_account_qr_start",
    "description": "Start connecting the USER'S OWN Telegram account via QR. Returns a qr_url (and qr_png if "
                   "renderable) to show the user — they scan it in Telegram → Settings → Devices → Link Device. "
                   "Then call tg_account_qr_confirm with the returned token. Own accounts are never warmed.",
    "parameters": {
        "type": "object",
        "properties": {
            "proxy": {"type": "string", "description": "optional socks5://user:pass@host:port"},
            "country": {"type": "string", "description": "optional ISO-2 country for the proxy/account"},
        },
    },
}
_S_QR_CONFIRM = {
    "name": "tg_account_qr_confirm",
    "description": "Finish a QR login started by tg_account_qr_start. Poll this after the user scans. Returns the "
                   "registered own account on success; {need_password:true} if the account has 2FA (call again with "
                   "password); {not_scanned_yet, qr_url} if still waiting (show the refreshed QR).",
    "parameters": {
        "type": "object",
        "properties": {
            "token": {"type": "string", "description": "token from tg_account_qr_start"},
            "password": {"type": "string", "description": "2FA password, only if need_password was returned"},
            "timeout": {"type": "integer", "description": "seconds to wait for the scan this call (default 30)"},
        },
        "required": ["token"],
    },
}
_S_SEND = {
    "name": "tg_send",
    "description": "Send a message to a person from a specific account. Creates or updates the Conversation "
                   "(account ↔ peer) and stores the message. No campaign needed — this is the base 'talk to a client' action.",
    "parameters": {
        "type": "object",
        "properties": {
            "account_id": {"type": "integer", "description": "which account sends"},
            "peer": {"type": "string", "description": "@username, t.me link, or numeric id"},
            "text": {"type": "string"},
            "conversation_id": {"type": "integer", "description": "optional: send within an existing thread"},
        },
        "required": ["account_id", "peer", "text"],
    },
}
_S_POLL = {
    "name": "tg_poll",
    "description": "Fetch NEW inbound messages for open conversations and store them. With no account_id it "
                   "polls ALL accounts in one call (multi-account). Scope to one account_id or one conversation_id.",
    "parameters": {
        "type": "object",
        "properties": {
            "account_id": {"type": "integer", "description": "optional: only this account's conversations"},
            "conversation_id": {"type": "integer", "description": "optional: only this thread"},
            "limit": {"type": "integer", "description": "max messages per conversation to scan (default 30)"},
        },
    },
}
_S_CONVERSATIONS = {
    "name": "tg_conversations",
    "description": "List conversations (account ↔ peer, newest activity first), or read one thread's stored "
                   "history when conversation_id is given.",
    "parameters": {
        "type": "object",
        "properties": {
            "account_id": {"type": "integer"},
            "status": {"type": "string", "enum": ["open", "closed", "all"]},
            "conversation_id": {"type": "integer", "description": "if set, returns this thread's message history"},
            "limit": {"type": "integer"},
        },
    },
}

_TOOLS = (
    ("tg_account_qr_start",   _S_QR_START,    _h_qr_start,     True,  "📲"),
    ("tg_account_qr_confirm", _S_QR_CONFIRM,  _h_qr_confirm,   True,  "✅"),
    ("tg_account_add",   _S_ACCOUNT_ADD,   _h_account_add,   True,  "➕"),
    ("tg_account_list",  _S_ACCOUNT_LIST,  _h_account_list,  False, "📇"),
    ("tg_send",          _S_SEND,          _h_send,          True,  "✉️"),
    ("tg_poll",          _S_POLL,          _h_poll,          True,  "📥"),
    ("tg_conversations", _S_CONVERSATIONS, _h_conversations, False, "💬"),
)


def register(ctx) -> None:
    """Register the tg_ops primitives. Called once by the plugin loader."""
    # Best-effort schema bootstrap (also done at pod boot); harmless if deps absent.
    try:
        from .core.db import init_db
        init_db()
    except Exception:
        pass
    for name, schema, handler, is_async, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="tg_ops",
            schema=schema,
            handler=handler,
            check_fn=_available,
            is_async=is_async,
            emoji=emoji,
        )
