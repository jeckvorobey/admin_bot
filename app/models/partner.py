"""Модель партнёра."""

from dataclasses import dataclass

from app.models.base import BaseEntity


@dataclass(frozen=True)
class Partner(BaseEntity):
    """Партнёрская рекомендация."""

    name: str
    category: str
    trigger_words: str
    link: str
    description: str
    priority: int
