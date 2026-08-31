"""
humanize.py — make an account BEHAVE like a person, not a bot.

Telegram's anti-spam watches behaviour: instant replies, no typing indicator, no
read receipts, uniform timing = bot. These helpers add the human signals:
  • read the incoming message (send_read_acknowledge) before answering
  • a reading pause, then a "typing…" indicator for a duration proportional to the
    reply length, then send
  • the right "recording voice / uploading video" indicator before media
All durations are jittered. Any failure to show an action never blocks the send.
"""
from __future__ import annotations

import asyncio
import random


def typing_seconds(text: str) -> float:
    """Human typing time for `text` — ~40 wpm with jitter, clamped to a sane range."""
    n = len(text or "")
    base = n / 4.5
    return max(1.2, min(base, 12.0)) * random.uniform(0.85, 1.3)


def read_seconds(incoming: str | None) -> float:
    """Pause as if reading the incoming message before starting to type."""
    n = len(incoming or "")
    return min(0.8 + n / 40.0, 6.0) * random.uniform(0.8, 1.3)


async def _read_ack(client, peer) -> None:
    try:
        await client.send_read_acknowledge(peer)
    except Exception:  # noqa: BLE001
        pass


async def type_and_send(client, peer, text: str, *, incoming: str | None = None,
                        instant: bool = False):
    """Read → pause → show 'typing…' for a realistic time → send. Returns the message."""
    if not instant:
        await _read_ack(client, peer)
        if incoming:
            await asyncio.sleep(read_seconds(incoming))
        try:
            async with client.action(peer, "typing"):
                await asyncio.sleep(typing_seconds(text))
        except Exception:  # noqa: BLE001 — indicator best-effort; still pause + send
            await asyncio.sleep(min(len(text or "") / 4.5, 8.0))
    return await client.send_message(peer, text)


async def record_and_send_file(client, peer, file, *, caption: str = "", voice: bool = False,
                               video_note: bool = False, instant: bool = False):
    """Show the right recording/uploading indicator before sending media."""
    if voice:
        action, hold = "record-voice", random.uniform(2.5, 7.0)
    elif video_note:
        action, hold = "record-round", random.uniform(3.0, 8.0)
    else:
        action, hold = "video", random.uniform(2.0, 5.0)
    if not instant:
        await _read_ack(client, peer)
        try:
            async with client.action(peer, action):
                await asyncio.sleep(hold)
        except Exception:  # noqa: BLE001
            await asyncio.sleep(random.uniform(2.0, 4.0))
    return await client.send_file(peer, file, caption=(caption or None),
                                  voice_note=voice, video_note=video_note)
