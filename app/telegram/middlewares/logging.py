"""Logging middleware для aiogram."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.utils.logging import compact_log_text

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """Логирует входящие Telegram events и длительность обработки."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        started_at = monotonic()
        logger.info("Telegram event received: %s", _describe_event(event))
        try:
            result = await handler(event, data)
        except Exception:
            logger.exception("Telegram event failed: %s", _describe_event(event))
            raise

        duration_ms = int((monotonic() - started_at) * 1000)
        logger.info(
            "Telegram event handled: %s duration_ms=%s",
            _describe_event(event),
            duration_ms,
        )
        return result


def _describe_event(event: TelegramObject) -> str:
    """Возвращает краткое описание Telegram event."""
    if isinstance(event, Message):
        return (
            f"type=Message chat_id={event.chat.id} user_id="
            f"{event.from_user.id if event.from_user else None} "
            f"message_id={event.message_id} text='{compact_log_text(event.text, 400)}'"
        )
    return f"type={event.__class__.__name__}"
