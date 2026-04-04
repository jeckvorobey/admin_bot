"""Repository истории чата."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.models.chat import ChatLogEntry
from app.repositories.base import BaseRepository
from app.utils.logging import compact_log_text

logger = logging.getLogger(__name__)


class ChatLogRepository(BaseRepository):
    """Доступ к таблице `chat_log`."""

    def add_entry(
        self,
        chat_id: int,
        user_id: int,
        question: str,
        answer: str,
        created_at: datetime | None = None,
    ) -> None:
        """Сохраняет вопрос пользователя и ответ бота."""
        event_at = (created_at or datetime.now(UTC)).isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO chat_log (chat_id, user_id, question, answer, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chat_id, user_id, question, answer, event_at),
            )
        logger.info(
            "ChatLogRepository.add_entry: chat_id=%s user_id=%s question='%s' answer='%s'",
            chat_id,
            user_id,
            compact_log_text(question, 400),
            compact_log_text(answer, 600),
        )

    def list_recent(self, chat_id: int, limit: int = 20) -> list[ChatLogEntry]:
        """Возвращает последние записи истории чата."""
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, chat_id, user_id, question, answer, created_at
                FROM chat_log
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
        logger.info(
            "ChatLogRepository.list_recent: chat_id=%s limit=%s rows=%s",
            chat_id,
            limit,
            len(rows),
        )
        return [
            ChatLogEntry(
                id=row["id"],
                chat_id=row["chat_id"],
                user_id=row["user_id"],
                question=row["question"],
                answer=row["answer"],
                created_at=row["created_at"],
            )
            for row in reversed(rows)
        ]

    def count_duplicate_questions(
        self,
        chat_id: int,
        user_id: int,
        question: str,
        window_seconds: int,
        now: datetime | None = None,
    ) -> int:
        """Считает одинаковые вопросы от других пользователей за временное окно."""
        threshold = (
            (now or datetime.now(UTC)) - timedelta(seconds=window_seconds)
        ).isoformat()
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(DISTINCT user_id) AS total
                FROM chat_log
                WHERE chat_id = ?
                  AND user_id != ?
                  AND LOWER(TRIM(question)) = LOWER(TRIM(?))
                  AND created_at >= ?
                """,
                (chat_id, user_id, question, threshold),
            ).fetchone()
        total = int(row["total"])
        logger.info(
            "ChatLogRepository.count_duplicate_questions: chat_id=%s user_id=%s "
            "window_seconds=%s duplicates=%s question='%s'",
            chat_id,
            user_id,
            window_seconds,
            total,
            compact_log_text(question, 400),
        )
        return total
