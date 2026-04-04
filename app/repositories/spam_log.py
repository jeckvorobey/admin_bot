"""Repository логов антиспама."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.repositories.base import BaseRepository
from app.utils.logging import compact_log_text

logger = logging.getLogger(__name__)


class SpamLogRepository(BaseRepository):
    """Доступ к таблице `spam_log`."""

    def add_entry(
        self,
        chat_id: int,
        user_id: int,
        text: str,
        reason: str,
        created_at: datetime | None = None,
    ) -> None:
        """Сохраняет причину удаления спама."""
        event_at = (created_at or datetime.now(UTC)).isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO spam_log (chat_id, user_id, text, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chat_id, user_id, text, reason, event_at),
            )
        logger.info(
            "SpamLogRepository.add_entry: chat_id=%s user_id=%s reason='%s' text='%s'",
            chat_id,
            user_id,
            compact_log_text(reason, 300),
            compact_log_text(text, 500),
        )
