"""Конфигурация правил антиспама."""

from __future__ import annotations

from pathlib import Path

SPAM_NEW_MEMBER_TTL_SECONDS = 86400
SPAM_DUPLICATE_WINDOW_SECONDS = 600
SPAM_MAX_MENTIONS = 5

SPAM_BLACKLISTED_DOMAINS: tuple[str, ...] = ()
SPAM_FORWARD_WHITELIST_CHAT_IDS: frozenset[int] = frozenset()

SPAM_STOP_WORDS_PATH = Path(__file__).resolve().parent / "words" / "spam_stop_words.txt"


def load_spam_stop_words() -> list[str]:
    """Загружает стоп-слова антиспама из файла."""
    return [
        line.strip().casefold()
        for line in SPAM_STOP_WORDS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
