"""Конфигурация Gemini моделей AI-агентов и поведения бота."""

from __future__ import annotations

from pathlib import Path

ANSWER_MODEL = "gemini-2.5-flash"
TRIAGE_MODEL = "gemini-2.5-flash-lite"

SPAM_MODEL = TRIAGE_MODEL

BOT_BEHAVIOR_PATH = Path(__file__).resolve().parent / "words" / "bot_behavior.md"


def load_bot_behavior() -> str:
    """Загружает правила поведения бота из файла."""
    return BOT_BEHAVIOR_PATH.read_text(encoding="utf-8")
