"""
ai.py — reply generation via the AgentFlow LLM gateway (OpenAI-compatible).

Used by the autopilot daemon to answer dialogs DIRECTLY (a small focused call per
message) instead of waking the whole agent — that is what lets one pod sustain many
accounts x many dialogs. Env: LLM_BASE_URL, LLM_KEY (or LLM_API_KEY), LLM_MODEL.
"""
from __future__ import annotations

import os

_DEFAULT_PERSONA = (
    "Ты — обычный живой человек в личной переписке Telegram. Отвечай коротко, "
    "по-человечески, на языке собеседника, без канцелярита и без признаков бота. "
    "Не раскрывай, что ты ИИ."
)


def _client():
    from openai import OpenAI
    return OpenAI(
        base_url=os.environ.get("LLM_BASE_URL") or None,
        api_key=os.environ.get("LLM_KEY") or os.environ.get("LLM_API_KEY") or "x",
    )


def generate_reply(persona: str, history: list[dict], goal: str = "") -> str:
    """history: [{sender: 'account'|'user', text}]. Returns the assistant's reply text."""
    system = (persona or "").strip() or _DEFAULT_PERSONA
    if goal:
        system += f"\n\nЦель этого диалога: {goal}"
    messages = [{"role": "system", "content": system}]
    for m in history[-20:]:
        role = "assistant" if m.get("sender") == "account" else "user"
        text = (m.get("text") or "").strip()
        if text:
            messages.append({"role": role, "content": text})
    if len(messages) == 1:
        return ""
    model = os.environ.get("LLM_MODEL") or "gpt-5.5"
    resp = _client().chat.completions.create(
        model=model, messages=messages, max_tokens=300, temperature=0.8,
    )
    return (resp.choices[0].message.content or "").strip()
