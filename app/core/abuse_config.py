"""Конфигурация модерации оскорблений."""

from __future__ import annotations

from pathlib import Path

ABUSE_WARNING_LIMIT = 2
ABUSE_MUTE_DURATION_SECONDS = 86400

ABUSE_STOP_WORDS_PATH = Path(__file__).resolve().parent / "words" / "abuse_stop_words.txt"


def load_abuse_stop_words() -> list[str]:
    """Загружает маркеры оскорблений из файла."""
    return [
        line.strip().casefold()
        for line in ABUSE_STOP_WORDS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
