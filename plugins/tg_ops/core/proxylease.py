"""
proxylease.py — lease a sticky proxy from the AgentFlow proxy reseller.

The tenant pod's NetworkPolicy blocks a DIRECT connection to Telegram, so every
Telethon client (QR login included) must go THROUGH a proxy — otherwise the connect
fails and the QR looks "invalid". Env (injected by CP): PROXY_URL, PROXY_TOKEN,
PROXY_USER_ID. Returns a socks5://user:pass@host:port string, or None if unconfigured.
"""
from __future__ import annotations

import json
import os
import urllib.request


def lease(country: str | None = None, sticky: bool = True) -> str | None:
    base = os.environ.get("PROXY_URL")
    if not base:
        return None
    body: dict = {"userId": os.environ.get("PROXY_USER_ID") or "agent", "sticky": sticky}
    if country:
        body["country"] = country.strip().lower()
    req = urllib.request.Request(
        base.rstrip("/") + "/lease",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    token = os.environ.get("PROXY_TOKEN")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            d = json.load(resp)
    except Exception:  # noqa: BLE001 — no proxy is a soft failure; caller decides
        return None
    host = d.get("host")
    port = d.get("socksPort") or d.get("port")
    user = d.get("username")
    pwd = d.get("password")
    if not host or not port:
        return None
    if user:
        return f"socks5://{user}:{pwd}@{host}:{port}"
    return f"socks5://{host}:{port}"
