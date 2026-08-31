"""
usertools.py — the agent-authored tool registry (recipes).

The agent prototypes with tg_exec, then CRYSTALLIZES a working snippet into a named,
persistent tool here. A saved tool is an async body receiving (client, args); it runs
on any account via tg_tool_run. Saved on the PVC → survives restarts → a curated set
= a shippable TEMPLATE toolset the agent grew itself.
"""
from __future__ import annotations

import asyncio
import re

from sqlmodel import select
from telethon.tl import functions, types

from .db import SavedTool, get_session, now
from . import pool, tgclient
from .ops import _stringify


def _compile(code: str):
    """Wrap + compile the recipe body; raise SyntaxError if it doesn't parse."""
    src = "async def __tool(client, args):\n" + "\n".join("    " + ln for ln in (code or "").splitlines())
    compile(src, "<tg_tool>", "exec")
    return src


def define(name: str, code: str, description: str = "") -> dict:
    """Save (create or overwrite) an agent-authored tool. Validates it compiles."""
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "name required"}
    try:
        _compile(code)
    except SyntaxError as e:
        return {"ok": False, "error": f"code does not compile: {e}"}
    with get_session() as s:
        row = s.exec(select(SavedTool).where(SavedTool.name == name)).first()
        if row is None:
            row = SavedTool(name=name, description=description or None, code=code)
        else:
            row.code = code
            row.description = description or row.description
            row.updated_at = now()
        s.add(row)
        s.commit()
        s.refresh(row)
        return {"ok": True, "name": row.name, "saved": True}


def list_tools() -> list[dict]:
    with get_session() as s:
        rows = s.exec(select(SavedTool)).all()
        return [{"name": r.name, "description": r.description,
                 "updated_at": r.updated_at.isoformat() if r.updated_at else None} for r in rows]


def delete(name: str) -> dict:
    with get_session() as s:
        row = s.exec(select(SavedTool).where(SavedTool.name == name)).first()
        if row is None:
            return {"ok": False, "error": "not found"}
        s.delete(row)
        s.commit()
        return {"ok": True, "deleted": name}


def _load_code(name: str):
    with get_session() as s:
        row = s.exec(select(SavedTool).where(SavedTool.name == name)).first()
        return row.code if row else None


async def run(name: str, account_id: int, args: dict | None = None, timeout: int = 90) -> dict:
    """Run a saved tool on an account. Returns {ok, result} or {ok:false, error}."""
    code = await asyncio.to_thread(_load_code, name)
    if code is None:
        return {"ok": False, "error": f"tool '{name}' not found"}
    client = await pool.get(account_id)
    glb = {"client": client, "functions": functions, "types": types,
           "asyncio": asyncio, "tgclient": tgclient, "re": re}
    loc: dict = {}
    try:
        exec(_compile(code), glb, loc)  # noqa: S102 — agent-authored recipe on own account
        res = await asyncio.wait_for(loc["__tool"](client, args or {}), timeout=max(5, timeout))
    except tgclient.AccountError:
        raise
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "tool": name}
    return {"ok": True, "tool": name, "result": _stringify(res)}
