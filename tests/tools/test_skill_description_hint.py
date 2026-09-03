"""A rejected skill description must come back with one that would pass.

Observed live: an agent tried to save what it had just learned, got
"Description is 130 chars", guessed again at 62, then sent a malformed retry
that dropped `name` — three failed tool calls and a lost turn, because the
error stated a rule but never showed a value that satisfies it.
"""

from agent.skill_utils import SKILL_PROMPT_DESC_LIMIT
from tools.skill_manager_tool import _suggest_short_description


def test_suggestion_fits_the_budget_and_is_a_sentence():
    long_desc = (
        "Навык продаж в Telegram: как вести диалог, квалифицировать клиента, "
        "работать с возражениями и доводить человека до заявки"
    )
    out = _suggest_short_description(long_desc)
    assert len(out) <= SKILL_PROMPT_DESC_LIMIT
    assert out.endswith(".")
    assert out.startswith("Навык продаж"), "the routing trigger must survive"


def test_suggestion_cuts_on_a_word_boundary():
    out = _suggest_short_description("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo")
    assert not out.rstrip(".").endswith(("alph", "brav", "charli"))
    assert " " in out
    assert len(out) <= SKILL_PROMPT_DESC_LIMIT


def test_short_description_is_returned_unchanged():
    assert _suggest_short_description("Short one.") == "Short one."


def test_quotes_and_whitespace_are_normalised():
    out = _suggest_short_description("  'Ищет лидов в Telegram и пишет им первым'  ")
    assert not out.startswith(("'", '"', " "))
    assert len(out) <= SKILL_PROMPT_DESC_LIMIT
