"""Модель участника чата."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatMember:
    """Хранит активность участника и состояние moderation warning/mute."""

    chat_id: int
    user_id: int
    first_seen_at: str
    last_seen_at: str
    abuse_warning_count: int = 0
    muted_until_at: str | None = None
