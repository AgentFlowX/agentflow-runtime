"""Topic allowlist + /bind admin commands (multi-bot-per-group topic routing).

Pins the pieces that let several bots share one forum group, each answering only
in its own topic(s):

1. ``_telegram_allowed_topics`` — parse the whitelist from list / csv / env.
2. ``_topic_scoped_enabled`` — the "silent until bound" default flag.
3. ``_set_allowed_topics`` — in-memory update + persist delegation.
4. ``_persist_allowed_topics`` — writes ``platforms.telegram.extra.allowed_topics``.
5. Wiring guards — the gate consults ``_topic_scoped_enabled`` and ``_handle_command``
   intercepts /bind BEFORE the topic gate (so a scoped bot can be bound to a NEW topic).
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest


def _bare_adapter(extra=None):
    """A TelegramAdapter shell with just ``platform`` + ``config`` (no PTB init)."""
    from gateway.config import Platform
    from plugins.platforms.telegram.adapter import TelegramAdapter

    adapter = object.__new__(TelegramAdapter)
    adapter.platform = Platform.TELEGRAM
    adapter.config = SimpleNamespace(extra=dict(extra or {}))
    return adapter


class TestAllowedTopicsParse:
    def test_list_of_mixed_types(self):
        a = _bare_adapter({"allowed_topics": [1, "2", " 3 "]})
        assert a._telegram_allowed_topics() == {"1", "2", "3"}

    def test_csv_string(self):
        a = _bare_adapter({"allowed_topics": "5, 6 ,7"})
        assert a._telegram_allowed_topics() == {"5", "6", "7"}

    def test_empty_when_unset(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_ALLOWED_TOPICS", raising=False)
        assert _bare_adapter({})._telegram_allowed_topics() == set()


class TestTopicScopedFlag:
    @pytest.mark.parametrize("val", ["true", "1", "yes", "on", True])
    def test_truthy(self, val):
        assert _bare_adapter({"topic_scoped": val})._topic_scoped_enabled() is True

    @pytest.mark.parametrize("val", ["false", "0", "no", "off"])
    def test_falsey(self, val):
        assert _bare_adapter({"topic_scoped": val})._topic_scoped_enabled() is False

    def test_unset_is_false(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_TOPIC_SCOPED", raising=False)
        assert _bare_adapter({})._topic_scoped_enabled() is False


class TestSetAllowedTopics:
    def test_updates_memory_and_persists(self, monkeypatch):
        a = _bare_adapter({})
        captured = {}
        monkeypatch.setattr(a, "_persist_allowed_topics", lambda t: captured.setdefault("t", t))
        a._set_allowed_topics({"7", "1", "10"})
        # sorted by (len, value): "1","7" (len1) then "10" (len2)
        assert a.config.extra["allowed_topics"] == ["1", "7", "10"]
        assert captured["t"] == ["1", "7", "10"]


class TestPersist:
    def test_writes_allowed_topics_to_config_yaml(self, tmp_path, monkeypatch):
        import hermes_constants

        monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: tmp_path)
        (tmp_path / "config.yaml").write_text("platforms:\n  telegram:\n    extra: {}\n")

        _bare_adapter({})._persist_allowed_topics(["1", "7"])

        import yaml
        cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert cfg["platforms"]["telegram"]["extra"]["allowed_topics"] == ["1", "7"]

    def test_no_crash_when_config_missing(self, tmp_path, monkeypatch):
        import hermes_constants

        monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: tmp_path)
        # no config.yaml present — must warn + return, never raise
        _bare_adapter({})._persist_allowed_topics(["1"])


class TestWiringGuards:
    def test_gate_consults_topic_scoped(self):
        from plugins.platforms.telegram.adapter import TelegramAdapter

        src = inspect.getsource(TelegramAdapter._should_process_message)
        assert "_topic_scoped_enabled" in src

    def test_bind_intercepted_before_topic_gate(self):
        from plugins.platforms.telegram.adapter import TelegramAdapter

        src = inspect.getsource(TelegramAdapter._handle_command)
        assert "_maybe_handle_topic_bind_command" in src
        assert src.index("_maybe_handle_topic_bind_command") < src.index("_should_process_message")

    def test_bind_command_recognizes_the_three_verbs(self):
        from plugins.platforms.telegram.adapter import TelegramAdapter

        src = inspect.getsource(TelegramAdapter._maybe_handle_topic_bind_command)
        assert '"bind"' in src and '"unbind"' in src and '"topics"' in src
        # must reject commands addressed to a DIFFERENT bot (multi-bot group)
        assert "_current_bot_username" in src


class _FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)


def _group_msg(text, *, chat_id=-1001234, thread_id=7):
    chat = SimpleNamespace(id=chat_id, type="supergroup", is_forum=True)
    return SimpleNamespace(
        text=text, chat=chat, message_thread_id=thread_id,
        from_user=SimpleNamespace(id=555),
    )


def _prep_adapter(username="landing_bot", extra=None):
    a = _bare_adapter(extra or {})
    a._current_bot_username = lambda: username
    a._is_group_chat = lambda m: True
    a._is_user_authorized_from_message = lambda m: True
    a._effective_message_thread_id = lambda m: getattr(m, "message_thread_id", None)
    a._persist_allowed_topics = lambda t: None  # no disk write in tests
    return a


def _call(adapter, msg):
    import asyncio
    bot = _FakeBot()
    ctx = SimpleNamespace(bot=bot)
    handled = asyncio.run(adapter._maybe_handle_topic_bind_command(msg, ctx))
    return handled, bot


class TestBindAddressing:
    def test_bind_at_self_binds_and_replies(self):
        a = _prep_adapter("landing_bot")
        handled, bot = _call(a, _group_msg("/bind@landing_bot", thread_id=7))
        assert handled is True
        assert a.config.extra.get("allowed_topics") == ["7"]
        assert len(bot.sent) == 1  # confirmation sent

    def test_bind_at_other_bot_is_silent_noop(self):
        a = _prep_adapter("video_bot", {"allowed_topics": ["3"]})
        handled, bot = _call(a, _group_msg("/bind@landing_bot", thread_id=7))
        assert handled is True                    # consumed (not forwarded to agent)
        assert a.config.extra.get("allowed_topics") == ["3"]  # unchanged
        assert bot.sent == []                     # NO reaction

    def test_bare_bind_is_silent_noop(self):
        a = _prep_adapter("landing_bot")
        handled, bot = _call(a, _group_msg("/bind", thread_id=7))
        assert handled is True                    # consumed
        assert "allowed_topics" not in a.config.extra  # nothing bound
        assert bot.sent == []                     # no bot reacts to a bare /bind

    def test_non_bind_command_falls_through(self):
        a = _prep_adapter("landing_bot")
        handled, bot = _call(a, _group_msg("/status", thread_id=7))
        assert handled is False                   # normal command handling proceeds

    def test_unbind_at_self_removes_topic(self):
        a = _prep_adapter("landing_bot", {"allowed_topics": ["7", "9"]})
        handled, bot = _call(a, _group_msg("/unbind@landing_bot", thread_id=7))
        assert handled is True
        assert a.config.extra.get("allowed_topics") == ["9"]
        assert len(bot.sent) == 1
