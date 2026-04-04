"""Результат обработки группового сообщения."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class GroupMessageAction(StrEnum):
    """Действие handler-слоя для одного сообщения группы."""

    IGNORE = "ignore"
    REPLY = "reply"
    DELETE_SPAM = "delete_spam"
    WARN_USER = "warn_user"
    MUTE_USER = "mute_user"


@dataclass(frozen=True)
class GroupMessageResult:
    """Типизированный результат `GroupService.process_message`."""

    action: GroupMessageAction
    reply_text: str | None = None
    reason: str = ""
    mute_until: datetime | None = None
    warning_count: int = 0
