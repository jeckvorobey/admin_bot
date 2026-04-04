"""Загрузка системных промптов AI-агентов."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=16)
def load_prompt(prompt_name: str) -> str:
    """Читает `.md` prompt из `app/ai/prompts`."""
    return (_PROMPTS_DIR / prompt_name).read_text(encoding="utf-8").strip()
