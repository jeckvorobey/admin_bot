"""Модель FAQ записи."""

from dataclasses import dataclass

from app.models.base import BaseEntity


@dataclass(frozen=True)
class FAQ(BaseEntity):
    """FAQ-ответ по триггер-словам."""

    trigger_words: str
    answer: str
    link: str
    priority: int
