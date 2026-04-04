"""Утилиты форматирования данных для логов."""

from __future__ import annotations


def compact_log_text(text: str | None, max_length: int = 1200) -> str:
    """Возвращает однострочный текст с ограничением длины для логов."""
    if text is None:
        return ""

    compact_text = " ".join(text.split())
    if len(compact_text) <= max_length:
        return compact_text
    return f"{compact_text[:max_length]}... [truncated, total={len(compact_text)}]"
