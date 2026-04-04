"""Repository активности участников группы."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ChatMemberRepository(BaseRepository):
    """Доступ к таблице `chat_members`."""

    def touch_member(
        self,
        chat_id: int,
        user_id: int,
        created_at: datetime | None = None,
    ) -> None:
        """Создаёт или обновляет активность участника."""
        event_at = (created_at or datetime.now(UTC)).isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO chat_members (
                    chat_id,
                    user_id,
                    first_seen_at,
                    last_seen_at,
                    abuse_warning_count,
                    muted_until_at
                )
                VALUES (?, ?, ?, ?, 0, NULL)
                ON CONFLICT(chat_id, user_id)
                DO UPDATE SET last_seen_at = excluded.last_seen_at
                """,
                (chat_id, user_id, event_at, event_at),
            )
        logger.info(
            "ChatMemberRepository.touch_member: chat_id=%s user_id=%s event_at=%s",
            chat_id,
            user_id,
            event_at,
        )

    def get_member_age_seconds(
        self,
        chat_id: int,
        user_id: int,
        now: datetime | None = None,
    ) -> int:
        """Возвращает возраст участника в секундах."""
        current_time = now or datetime.now(UTC)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT first_seen_at
                FROM chat_members
                WHERE chat_id = ? AND user_id = ?
                """,
                (chat_id, user_id),
            ).fetchone()
        if row is None:
            logger.info(
                "ChatMemberRepository.get_member_age_seconds: chat_id=%s user_id=%s "
                "first_seen_at=None age_seconds=0",
                chat_id,
                user_id,
            )
            return 0
        age_seconds = int(
            (current_time - datetime.fromisoformat(row["first_seen_at"])).total_seconds()
        )
        logger.info(
            "ChatMemberRepository.get_member_age_seconds: chat_id=%s user_id=%s "
            "first_seen_at=%s age_seconds=%s",
            chat_id,
            user_id,
            row["first_seen_at"],
            age_seconds,
        )
        return age_seconds

    def register_abuse_warning(
        self,
        chat_id: int,
        user_id: int,
        created_at: datetime | None = None,
    ) -> int:
        """Увеличивает счётчик warning за оскорбления и возвращает новое значение."""
        event_at = (created_at or datetime.now(UTC)).isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO chat_members (
                    chat_id,
                    user_id,
                    first_seen_at,
                    last_seen_at,
                    abuse_warning_count,
                    muted_until_at
                )
                VALUES (?, ?, ?, ?, 1, NULL)
                ON CONFLICT(chat_id, user_id)
                DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    abuse_warning_count = chat_members.abuse_warning_count + 1
                """,
                (chat_id, user_id, event_at, event_at),
            )
            row = connection.execute(
                """
                SELECT abuse_warning_count
                FROM chat_members
                WHERE chat_id = ? AND user_id = ?
                """,
                (chat_id, user_id),
            ).fetchone()

        warning_count = int(row["abuse_warning_count"]) if row is not None else 0
        logger.info(
            "ChatMemberRepository.register_abuse_warning: chat_id=%s user_id=%s "
            "warning_count=%s",
            chat_id,
            user_id,
            warning_count,
        )
        return warning_count

    def mute_member_for_abuse(
        self,
        chat_id: int,
        user_id: int,
        *,
        muted_until: datetime,
        created_at: datetime | None = None,
    ) -> None:
        """Сбрасывает warning-счётчик и сохраняет срок мута."""
        event_at = (created_at or datetime.now(UTC)).isoformat()
        muted_until_at = muted_until.isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO chat_members (
                    chat_id,
                    user_id,
                    first_seen_at,
                    last_seen_at,
                    abuse_warning_count,
                    muted_until_at
                )
                VALUES (?, ?, ?, ?, 0, ?)
                ON CONFLICT(chat_id, user_id)
                DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    abuse_warning_count = 0,
                    muted_until_at = excluded.muted_until_at
                """,
                (chat_id, user_id, event_at, event_at, muted_until_at),
            )
        logger.info(
            "ChatMemberRepository.mute_member_for_abuse: chat_id=%s user_id=%s "
            "muted_until_at=%s",
            chat_id,
            user_id,
            muted_until_at,
        )
