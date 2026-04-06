"""Нормализованное входящее сообщение Telegram."""

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class IncomingMessage:
    """Сообщение группы в виде, удобном для services."""

    chat_id: int
    user_id: int
    message_id: int
    text: str
    created_at: datetime
    is_reply_to_bot: bool = False
    mentions_bot: bool = False
    has_question: bool = False
    has_links: bool = False
    mention_count: int = 0
    forward_chat_id: int | None = None
    reply_to_user_id: int | None = None
    mention_targets: tuple[str, ...] = ()
    user_language: str = "ru"

    @classmethod
    def build(
        cls,
        chat_id: int,
        user_id: int,
        message_id: int,
        text: str,
        *,
        is_reply_to_bot: bool = False,
        mentions_bot: bool = False,
        has_question: bool = False,
        has_links: bool = False,
        mention_count: int = 0,
        forward_chat_id: int | None = None,
        reply_to_user_id: int | None = None,
        mention_targets: tuple[str, ...] = (),
        user_language: str = "ru",
    ) -> "IncomingMessage":
        """Создаёт входящее сообщение с текущим UTC timestamp."""
        return cls(
            chat_id=chat_id,
            user_id=user_id,
            message_id=message_id,
            text=text,
            created_at=datetime.now(UTC),
            is_reply_to_bot=is_reply_to_bot,
            mentions_bot=mentions_bot,
            has_question=has_question,
            has_links=has_links,
            mention_count=mention_count,
            forward_chat_id=forward_chat_id,
            reply_to_user_id=reply_to_user_id,
            mention_targets=mention_targets,
            user_language=user_language,
        )
