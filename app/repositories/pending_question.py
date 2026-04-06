"""Репозиторий отложенных вопросов для механизма 5 минут."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class PendingQuestionRepository(BaseRepository):
    """Хранит вопросы, ожидающие ответа от бота или живых участников."""

    def add(
        self,
        *,
        chat_id: int,
        message_id: int,
        user_id: int,
        question: str,
        user_language: str = "ru",
        created_at: datetime | None = None,
    ) -> None:
        """Сохраняет новый вопрос со статусом `pending`."""
        ts = (created_at or datetime.now(UTC)).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO pending_questions
                    (chat_id, message_id, user_id, question, user_language, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (chat_id, message_id, user_id, question, user_language, ts),
            )
        logger.info(
            "PendingQuestion added: chat_id=%s message_id=%s user_id=%s",
            chat_id,
            message_id,
            user_id,
        )

    def find_ready(
        self,
        chat_id: int,
        *,
        cutoff_minutes: int = 5,
    ) -> list[dict]:
        """Возвращает pending-вопросы старше cutoff_minutes минут."""
        cutoff = (datetime.now(UTC) - timedelta(minutes=cutoff_minutes)).isoformat()
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, chat_id, message_id, user_id, question, user_language, created_at
                FROM pending_questions
                WHERE chat_id = ? AND status = 'pending' AND created_at <= ?
                ORDER BY created_at ASC
                """,
                (chat_id, cutoff),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_answered(self, chat_id: int, *, except_user_id: int | None = None) -> int:
        """Помечает pending-вопросы чата как answered (человек ответил).

        Если указан except_user_id — пропускает вопросы, заданные этим пользователем
        (автор вопроса не считается ответившим на свой же вопрос).
        Возвращает количество обновлённых записей.
        """
        now = datetime.now(UTC).isoformat()
        with self._connection() as conn:
            if except_user_id is not None:
                cursor = conn.execute(
                    """
                    UPDATE pending_questions
                    SET status = 'answered', answered_at = ?
                    WHERE chat_id = ? AND status = 'pending' AND user_id != ?
                    """,
                    (now, chat_id, except_user_id),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE pending_questions
                    SET status = 'answered', answered_at = ?
                    WHERE chat_id = ? AND status = 'pending'
                    """,
                    (now, chat_id),
                )
            updated = cursor.rowcount
        if updated:
            logger.info(
                "PendingQuestion marked answered: chat_id=%s count=%s except_user_id=%s",
                chat_id,
                updated,
                except_user_id,
            )
        return updated

    def mark_bot_answered(self, pending_id: int) -> None:
        """Помечает конкретный вопрос как отвеченный ботом."""
        now = datetime.now(UTC).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE pending_questions
                SET status = 'answered', answered_at = ?
                WHERE id = ?
                """,
                (now, pending_id),
            )
        logger.info("PendingQuestion bot-answered: id=%s", pending_id)
