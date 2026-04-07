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

    def mark_bot_answered(self, pending_id: int) -> None:
        """Помечает конкретный вопрос как отвеченный ботом.

        Устанавливает bot_replied_at — по нему можно отличить ответ бота
        от ответа живого участника (answered_by_message_id).
        """
        now = datetime.now(UTC).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE pending_questions
                SET status = 'answered', answered_at = ?, bot_replied_at = ?
                WHERE id = ?
                """,
                (now, now, pending_id),
            )
        logger.info("PendingQuestion bot-answered: id=%s", pending_id)

    def get_open_by_message_id(self, chat_id: int, message_id: int) -> dict | None:
        """Возвращает открытый вопрос по message_id, или None если не найден / уже закрыт."""
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, chat_id, message_id, user_id, question, user_language, created_at
                FROM pending_questions
                WHERE chat_id = ? AND message_id = ? AND status = 'pending'
                """,
                (chat_id, message_id),
            ).fetchone()
        return dict(row) if row else None

    def mark_answered_by_reply(
        self,
        question_id: int,
        answered_by_message_id: int,
        answered_at: datetime | None = None,
    ) -> None:
        """Закрывает конкретный вопрос: участник ответил reply-сообщением."""
        ts = (answered_at or datetime.now(UTC)).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE pending_questions
                SET status = 'answered', answered_at = ?, answered_by_message_id = ?
                WHERE id = ?
                """,
                (ts, answered_by_message_id, question_id),
            )
        logger.info(
            "PendingQuestion answered by reply: id=%s answered_by_message_id=%s",
            question_id,
            answered_by_message_id,
        )

