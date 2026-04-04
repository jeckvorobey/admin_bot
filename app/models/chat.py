"""Модели chat log и spam log."""

from dataclasses import dataclass
from datetime import datetime

from app.models.base import BaseEntity


@dataclass(frozen=True)
class ChatLogEntry(BaseEntity):
    """Запись вопроса и ответа бота."""

    chat_id: int
    user_id: int
    question: str
    answer: str
    created_at: datetime


@dataclass(frozen=True)
class SpamLogEntry(BaseEntity):
    """Запись удаления спама."""

    chat_id: int
    user_id: int
    text: str
    reason: str
    created_at: datetime
