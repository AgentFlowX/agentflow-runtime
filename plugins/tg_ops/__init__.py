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


async def _h_account_remove(args: dict, **_kw) -> str:
    from .core import accounts
    try:
        return tool_result(await accounts.remove_account(
            int(args["account_id"]), logout=bool(args.get("logout", True))))
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


async def _h_qr_start(args: dict, **_kw) -> str:
    import asyncio
    from .core import qrmanager
    try:
        r = await asyncio.to_thread(qrmanager.submit, args.get("country"))
        return tool_result(r)
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


async def _h_qr_confirm(args: dict, **_kw) -> str:
    import asyncio
    from .core import qrmanager
    try:
        if not args.get("token"):
            return tool_error("token required (from tg_account_qr_start)")
        r = await asyncio.to_thread(qrmanager.poll, args["token"], args.get("password"))
        return tool_result(r)
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


async def _h_send(args: dict, **_kw) -> str:
    from .core import messaging
    try:
        r = await messaging.send(int(args["account_id"]), args["peer"], args["text"],
                                 conversation_id=args.get("conversation_id"),
                                 instant=bool(args.get("instant", False)))
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


async def _h_search(args: dict, **_kw) -> str:
    from .core import ops
    try:
        if not args.get("query"):
            return tool_error("query required")
        return tool_result({"results": await ops.search_public(
            int(args["account_id"]), args["query"], limit=int(args.get("limit", 20)))})
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


async def _h_dialogs(args: dict, **_kw) -> str:
    from .core import ops
    try:
        return tool_result({"dialogs": await ops.list_dialogs(
            int(args["account_id"]), limit=int(args.get("limit", 50)))})
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


async def _h_read(args: dict, **_kw) -> str:
    from .core import ops
    try:
        return tool_result({"messages": await ops.read_peer(
            int(args["account_id"]), args["peer"], limit=int(args.get("limit", 30)))})
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


async def _h_participants(args: dict, **_kw) -> str:
    from .core import ops
    try:
        return tool_result({"members": await ops.participants(
            int(args["account_id"]), args["peer"], limit=int(args.get("limit", 100)),
            search=args.get("search", ""))})
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


async def _h_join(args: dict, **_kw) -> str:
    from .core import ops
    try:
        return tool_result(await ops.join(int(args["account_id"]), args["peer"]))
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


async def _h_create_bot(args: dict, **_kw) -> str:
    from .core import ops
    try:
        if not args.get("name") or not args.get("username"):
            return tool_error("name and username required")
        return tool_result(await ops.create_bot(
            int(args["account_id"]), args["name"], args["username"]))
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


async def _h_send_media(args: dict, **_kw) -> str:
    from .core import messaging
    try:
        if not args.get("file"):
            return tool_error("file (local path or URL) required")
        r = await messaging.send_media(
            int(args["account_id"]), args["peer"], args["file"],
            caption=args.get("caption", ""), conversation_id=args.get("conversation_id"),
            voice=bool(args.get("voice", False)), video_note=bool(args.get("video_note", False)),
            instant=bool(args.get("instant", False)))
        return tool_result(r)
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


async def _h_exec(args: dict, **_kw) -> str:
    from .core import ops
    try:
        if not args.get("code"):
            return tool_error("code required (async body receiving `client`)")
        return tool_result(await ops.exec_code(
            int(args["account_id"]), args["code"], timeout=int(args.get("timeout", 60))))
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


# --- agent-authored tool registry --------------------------------------------
def _h_tool_define(args: dict, **_kw) -> str:
    from .core import usertools
    try:
        if not args.get("name") or not args.get("code"):
            return tool_error("name and code required")
        return tool_result(usertools.define(args["name"], args["code"], args.get("description", "")))
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


def _h_tool_list(args: dict, **_kw) -> str:
    from .core import usertools
    try:
        return tool_result({"tools": usertools.list_tools()})
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


def _h_tool_delete(args: dict, **_kw) -> str:
    from .core import usertools
    try:
        return tool_result(usertools.delete(args.get("name", "")))
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


async def _h_tool_run(args: dict, **_kw) -> str:
    from .core import usertools
    try:
        if not args.get("name"):
            return tool_error("name required")
        return tool_result(await usertools.run(
            args["name"], int(args["account_id"]), args.get("args") or {},
            timeout=int(args.get("timeout", 90))))
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


# --- autopilot control -------------------------------------------------------
def _h_autopilot_set(args: dict, **_kw) -> str:
    from .core import autopilot
    try:
        return tool_result(autopilot.configure_account(
            int(args["account_id"]), persona=args.get("persona"), goal=args.get("goal"),
            mode=args.get("mode"), on=bool(args.get("on", True))))
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


def _h_autopilot_start(args: dict, **_kw) -> str:
    from .core import autopilot
    try:
        return tool_result(autopilot.start())
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


def _h_autopilot_stop(args: dict, **_kw) -> str:
    from .core import autopilot
    try:
        return tool_result(autopilot.stop())
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


def _h_autopilot_status(args: dict, **_kw) -> str:
    from .core import autopilot
    try:
        return tool_result(autopilot.status())
    except Exception as e:  # noqa: BLE001
        return tool_error(str(e))


def _h_conversation_auto(args: dict, **_kw) -> str:
    from .core import autopilot
    try:
        return tool_result(autopilot.set_conversation_auto(
            int(args["conversation_id"]), bool(args.get("on", False))))
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
_S_ACCOUNT_REMOVE = {
    "name": "tg_account_remove",
    "description": "Disconnect + remove an account. logout=true (default) logs the session OUT — revokes it on "
                   "Telegram so our linked device disappears from the user's Settings → Devices — then deletes the "
                   "account and its conversations from the engine. logout=false only removes it locally.",
    "parameters": {"type": "object", "properties": {
        "account_id": {"type": "integer"}, "logout": {"type": "boolean"}},
        "required": ["account_id"]},
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

_S_SEARCH = {
    "name": "tg_search",
    "description": "Search PUBLIC Telegram channels/groups/users by name or keyword — the way to FIND channels and "
                   "people to work (e.g. find channels about a topic, then read/join them). Returns type/id/username/title.",
    "parameters": {"type": "object", "properties": {
        "account_id": {"type": "integer"}, "query": {"type": "string"},
        "limit": {"type": "integer", "description": "max results (default 20, cap 50)"}},
        "required": ["account_id", "query"]},
}
_S_DIALOGS = {
    "name": "tg_dialogs",
    "description": "List the chats/channels/DMs an account is already in (its dialog list), newest first, with unread counts.",
    "parameters": {"type": "object", "properties": {
        "account_id": {"type": "integer"}, "limit": {"type": "integer"}},
        "required": ["account_id"]},
}
_S_READ = {
    "name": "tg_read",
    "description": "Read recent messages from ANY channel/group/user (read-only). Use to scan a channel's feed or a "
                   "chat's discussion. peer = @username, t.me link, or id.",
    "parameters": {"type": "object", "properties": {
        "account_id": {"type": "integer"}, "peer": {"type": "string"},
        "limit": {"type": "integer", "description": "messages to read (default 30, cap 100)"}},
        "required": ["account_id", "peer"]},
}
_S_PARTICIPANTS = {
    "name": "tg_participants",
    "description": "List members of a group/channel — the raw material for FINDING CLIENTS (who to reach). Optional "
                   "search filter. Returns id/username/name. Respect limits and Telegram rules.",
    "parameters": {"type": "object", "properties": {
        "account_id": {"type": "integer"}, "peer": {"type": "string"},
        "limit": {"type": "integer", "description": "members to pull (default 100, cap 500)"},
        "search": {"type": "string", "description": "optional name filter"}},
        "required": ["account_id", "peer"]},
}
_S_JOIN = {
    "name": "tg_join",
    "description": "Join a public channel/group from an account so it can read/act there. peer = @username or link.",
    "parameters": {"type": "object", "properties": {
        "account_id": {"type": "integer"}, "peer": {"type": "string"}},
        "required": ["account_id", "peer"]},
}

_S_CREATE_BOT = {
    "name": "tg_create_bot",
    "description": "Create a Telegram BOT by talking to @BotFather from an account — scripts /newbot → name → "
                   "username and returns the bot TOKEN. Use when the user wants a new bot made. username auto-suffixed "
                   "with 'bot' if missing; if taken, returns a note to try another.",
    "parameters": {"type": "object", "properties": {
        "account_id": {"type": "integer", "description": "account that talks to BotFather"},
        "name": {"type": "string", "description": "display name of the bot"},
        "username": {"type": "string", "description": "desired @username (must be unique, ends in 'bot')"}},
        "required": ["account_id", "name", "username"]},
}

_S_SEND_MEDIA = {
    "name": "tg_send_media",
    "description": "Send a photo/video/gif/document/voice from a local path (or URL) with an optional caption. "
                   "Use for any media message. voice=true for a voice note, video_note=true for a round video.",
    "parameters": {"type": "object", "properties": {
        "account_id": {"type": "integer"}, "peer": {"type": "string"},
        "file": {"type": "string", "description": "local file path or URL"},
        "caption": {"type": "string"}, "conversation_id": {"type": "integer"},
        "voice": {"type": "boolean"}, "video_note": {"type": "boolean"}},
        "required": ["account_id", "peer", "file"]},
}
_S_EXEC = {
    "name": "tg_exec",
    "description": "ESCAPE HATCH — run an async Python snippet with the connected Telethon `client` (+ `functions`, "
                   "`types`, `tgclient`) in scope and return its value. Do ANYTHING Telegram's API supports without a "
                   "dedicated tool: delete/edit/pin/forward messages, create channels/groups, invite, react, stats, raw "
                   "MTProto. `code` is the async function BODY receiving `client`; `return` a value to get it back. "
                   "Runs on the user's OWN account — powerful; prefer a named tool when one exists.",
    "parameters": {"type": "object", "properties": {
        "account_id": {"type": "integer"},
        "code": {"type": "string", "description": "async body, e.g. `msg=await client.send_message('me','hi'); return msg.id`"},
        "timeout": {"type": "integer"}},
        "required": ["account_id", "code"]},
}

_S_TOOL_DEFINE = {
    "name": "tg_tool_define",
    "description": "SAVE an agent-authored tool (recipe): a named, reusable async Python body receiving "
                   "(client, args) that you wrote from the primitives. Persists on the PVC. Prototype with tg_exec "
                   "first, then crystallize the working code here. `code` example: "
                   "`res = await client(functions.channels.CreateChannelRequest(title=args['title'], about='', broadcast=True)); return res.chats[0].id`",
    "parameters": {"type": "object", "properties": {
        "name": {"type": "string"}, "description": {"type": "string"},
        "code": {"type": "string", "description": "async body receiving (client, args)"}},
        "required": ["name", "code"]},
}
_S_TOOL_RUN = {
    "name": "tg_tool_run",
    "description": "Run a saved agent-authored tool by name on an account, passing args. Returns its result.",
    "parameters": {"type": "object", "properties": {
        "name": {"type": "string"}, "account_id": {"type": "integer"},
        "args": {"type": "object"}, "timeout": {"type": "integer"}},
        "required": ["name", "account_id"]},
}
_S_TOOL_LIST = {"name": "tg_tool_list", "description": "List saved agent-authored tools (name + description).",
                "parameters": {"type": "object", "properties": {}}}
_S_TOOL_DELETE = {"name": "tg_tool_delete", "description": "Delete a saved agent-authored tool by name.",
                  "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}

_S_AP_SET = {
    "name": "tg_autopilot_set",
    "description": "Configure an account as an autopilot WORKER: persona (who it is / how it talks), goal, mode "
                   "(inbound=answer everyone who writes | outreach=only dialogs it started), on=true to enable. In "
                   "inbound mode its open dialogs are flipped to auto so the daemon maintains them.",
    "parameters": {"type": "object", "properties": {
        "account_id": {"type": "integer"}, "persona": {"type": "string"}, "goal": {"type": "string"},
        "mode": {"type": "string", "enum": ["inbound", "outreach"]}, "on": {"type": "boolean"}},
        "required": ["account_id"]},
}
_S_AP_START = {"name": "tg_autopilot_start", "description": "Start the autopilot daemon — it maintains all autopilot accounts' auto dialogs 24/7 (poll → LLM reply → send, paced). Idempotent.", "parameters": {"type": "object", "properties": {}}}
_S_AP_STOP = {"name": "tg_autopilot_stop", "description": "Stop the autopilot daemon.", "parameters": {"type": "object", "properties": {}}}
_S_AP_STATUS = {"name": "tg_autopilot_status", "description": "Autopilot daemon status: running, how many accounts on autopilot, replies sent, errors.", "parameters": {"type": "object", "properties": {}}}
_S_CONV_AUTO = {
    "name": "tg_conversation_auto",
    "description": "Take a specific dialog OFF autopilot (human/agent takeover, on=false) or hand it back to the daemon (on=true).",
    "parameters": {"type": "object", "properties": {
        "conversation_id": {"type": "integer"}, "on": {"type": "boolean"}}, "required": ["conversation_id"]},
}

_TOOLS = (
    ("tg_account_qr_start",   _S_QR_START,    _h_qr_start,     True,  "📲"),
    ("tg_create_bot",     _S_CREATE_BOT,    _h_create_bot,    True,  "🤖"),
    ("tg_send_media",     _S_SEND_MEDIA,    _h_send_media,    True,  "🎬"),
    ("tg_exec",           _S_EXEC,          _h_exec,          True,  "🧩"),
    ("tg_tool_define",    _S_TOOL_DEFINE,   _h_tool_define,   False, "🛠"),
    ("tg_tool_run",       _S_TOOL_RUN,      _h_tool_run,      True,  "▶️"),
    ("tg_tool_list",      _S_TOOL_LIST,     _h_tool_list,     False, "📋"),
    ("tg_tool_delete",    _S_TOOL_DELETE,   _h_tool_delete,   False, "🗑"),
    ("tg_autopilot_set",  _S_AP_SET,        _h_autopilot_set, False, "🎛"),
    ("tg_autopilot_start", _S_AP_START,     _h_autopilot_start, False, "🟢"),
    ("tg_autopilot_stop", _S_AP_STOP,       _h_autopilot_stop, False, "🔴"),
    ("tg_autopilot_status", _S_AP_STATUS,   _h_autopilot_status, False, "📊"),
    ("tg_conversation_auto", _S_CONV_AUTO,  _h_conversation_auto, False, "✋"),
    ("tg_search",         _S_SEARCH,        _h_search,        True,  "🔎"),
    ("tg_dialogs",        _S_DIALOGS,       _h_dialogs,       True,  "🗂"),
    ("tg_read",           _S_READ,          _h_read,          True,  "📖"),
    ("tg_participants",   _S_PARTICIPANTS,  _h_participants,  True,  "👥"),
    ("tg_join",           _S_JOIN,          _h_join,          True,  "➕"),
    ("tg_account_qr_confirm", _S_QR_CONFIRM,  _h_qr_confirm,   True,  "✅"),
    ("tg_account_add",   _S_ACCOUNT_ADD,   _h_account_add,   True,  "➕"),
    ("tg_account_list",  _S_ACCOUNT_LIST,  _h_account_list,  False, "📇"),
    ("tg_account_remove", _S_ACCOUNT_REMOVE, _h_account_remove, True, "🔌"),
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
