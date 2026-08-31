"""
accounts.py — account registry primitives: add (own/bought) + list.

`add_account` creates the rows, then connects through the pool to VERIFY the session
is authorized and fills identity (tg_id/username/phone). The `source` decides the
warmup rule right here: own (QR) accounts land `ready` and are never warmed; bought
accounts land `cold` — warmup material, but only if a mailing later asks for it.
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

from sqlmodel import select

from .db import (
    Account, AccountSource, AccountStatus, WarmupPhase, Proxy,
    default_app_id, default_app_hash, get_session, now, log_action,
)
from . import pool, tgclient


def _parse_proxy(proxy: str, country: Optional[str]) -> Proxy:
    """Parse a proxy string into a Proxy row (not committed).

    Accepts socks5://user:pass@host:port, user:pass@host:port, host:port:user:pass,
    or host:port. Kind defaults to socks5.
    """
    raw = (proxy or "").strip()
    kind = "socks5"
    m = re.match(r"^(socks5|socks4|http)://", raw, re.I)
    if m:
        kind = m.group(1).lower()
        raw = raw[m.end():]
    user = pwd = None
    if "@" in raw:
        creds, hostport = raw.rsplit("@", 1)
        if ":" in creds:
            user, pwd = creds.split(":", 1)
    else:
        parts = raw.split(":")
        if len(parts) == 4:  # host:port:user:pass
            hostport = f"{parts[0]}:{parts[1]}"
            user, pwd = parts[2], parts[3]
        else:
            hostport = raw
    host, _, port = hostport.partition(":")
    return Proxy(kind=kind, host=host, port=int(port or 1080), username=user or None,
                 password=pwd or None, country=(country or None))


async def add_account(session_str: str, *, source: str = "bought", proxy: Optional[str] = None,
                      country: Optional[str] = None, app_id: Optional[int] = None, app_hash: Optional[str] = None,
                      purpose: Optional[str] = None, group: Optional[str] = None,
                      device: Optional[str] = None) -> dict:
    """Register + verify an account. Returns {ok, account_id, source, me?, error?}."""
    src = AccountSource(source)

    def _create() -> int:
        with get_session() as s:
            proxy_id = None
            if proxy:
                p = _parse_proxy(proxy, country)
                s.add(p)
                s.commit()
                s.refresh(p)
                proxy_id = p.id
            acc = Account(
                session=session_str, app_id=app_id or default_app_id(), app_hash=app_hash or default_app_hash(),
                device=device, country=country, proxy_id=proxy_id, source=src,
                purpose=purpose, group_name=group,
                warmup_phase=WarmupPhase.ready if src == AccountSource.own else WarmupPhase.cold,
            )
            s.add(acc)
            s.commit()
            s.refresh(acc)
            return acc.id

    account_id = await asyncio.to_thread(_create)

    # verify authorized via the pool (connects once, stays cached)
    try:
        client = await pool.get(account_id)
        me = await tgclient.whoami(client)
    except tgclient.AccountError as e:
        def _mark_dead():
            with get_session() as s:
                acc = s.get(Account, account_id)
                if acc is not None:
                    acc.status = AccountStatus.dead if e.reason == "dead" else AccountStatus.unknown
                    acc.is_active = False
                    acc.deactivated_reason = e.reason
                    acc.last_health_check = now()
                    s.add(acc)
                    s.commit()
        await asyncio.to_thread(_mark_dead)
        log_action(account_id, "ingest", f"{source} FAILED:{e.reason}", ok=False)
        return {"ok": False, "account_id": account_id, "source": source, "error": e.reason}

    def _fill():
        with get_session() as s:
            acc = s.get(Account, account_id)
            acc.tg_id = me.get("id")
            acc.username = me.get("username")
            acc.phone = me.get("phone")
            acc.first_name = me.get("first_name")
            acc.status = AccountStatus.active
            acc.is_active = True
            acc.last_health_check = now()
            s.add(acc)
            s.commit()

    await asyncio.to_thread(_fill)
    log_action(account_id, "ingest", source, ok=True)
    return {"ok": True, "account_id": account_id, "source": source, "me": me}


def list_accounts(source: Optional[str] = None, status: Optional[str] = None,
                  group: Optional[str] = None) -> list[dict]:
    """List accounts with health + source, newest first. Never returns the session."""
    with get_session() as s:
        rows = list(s.exec(select(Account)).all())
    out = []
    for a in rows:
        if source and a.source.value != source:
            continue
        if status and a.status.value != status:
            continue
        if group and a.group_name != group:
            continue
        out.append({
            "account_id": a.id, "source": a.source.value, "tg_id": a.tg_id,
            "username": a.username, "phone": a.phone, "country": a.country,
            "status": a.status.value, "warmup_phase": a.warmup_phase.value,
            "is_active": a.is_active, "purpose": a.purpose, "group": a.group_name,
            "proxy_id": a.proxy_id,
        })
    out.sort(key=lambda r: r["account_id"] or 0, reverse=True)
    return out
