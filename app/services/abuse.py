"""Сервис модерации оскорблений и конфликтного общения."""

from __future__ import annotations

import logging
import re
from datetime import timedelta

from app.core.abuse_config import (
    ABUSE_MUTE_DURATION_SECONDS,
    ABUSE_WARNING_LIMIT,
    load_abuse_stop_words,
)
from app.models.group_action import GroupMessageAction, GroupMessageResult
from app.models.incoming_message import IncomingMessage
from app.repositories.chat_member import ChatMemberRepository
from app.repositories.spam_log import SpamLogRepository
from app.utils.logging import compact_log_text

logger = logging.getLogger(__name__)

_DIRECT_ADDRESS_RE = re.compile(
    r"(^|\s)(ты|тебя|тебе|тобой|твой|твоя|твои|вы|вас|вам|вами|ваш|ваша|ваши|"
    r"иди|пошел|пошла|заткнись|сам ты|сама ты)\b",
    re.IGNORECASE,
)


class AbuseModerationService:
    """Выдаёт предупреждения за оскорбления и мут после повторных нарушений."""

    def __init__(
        self,
        chat_member_repository: ChatMemberRepository | None = None,
        spam_log_repository: SpamLogRepository | None = None,
        abuse_words: list[str] | None = None,
        warning_limit: int = ABUSE_WARNING_LIMIT,
        mute_duration_seconds: int = ABUSE_MUTE_DURATION_SECONDS,
    ) -> None:
        self._chat_member_repository = chat_member_repository or ChatMemberRepository()
        self._spam_log_repository = spam_log_repository or SpamLogRepository()
        self._abuse_words = (
            load_abuse_stop_words()
            if abuse_words is None
            else [word.casefold() for word in abuse_words]
        )
        self._abuse_patterns = [
            (word, re.compile(rf"(?<!\w){re.escape(word)}(?!\w)", re.IGNORECASE))
            for word in self._abuse_words
            if word
        ]
        self._warning_limit = warning_limit
        self._mute_duration_seconds = mute_duration_seconds

    def moderate_message(self, message: IncomingMessage) -> GroupMessageResult | None:
        """Возвращает warning/mute результат, если сообщение содержит прямое оскорбление."""
        abuse_reason = self.detect_abuse(message)
        if abuse_reason is None:
            return None

        warning_count = self._chat_member_repository.register_abuse_warning(
            message.chat_id,
            message.user_id,
            message.created_at,
        )
        if warning_count <= self._warning_limit:
            moderation_result = GroupMessageResult(
                action=GroupMessageAction.WARN_USER,
                reply_text=self._build_warning_text(warning_count),
                reason=abuse_reason,
                warning_count=warning_count,
            )
            self._spam_log_repository.add_entry(
                chat_id=message.chat_id,
                user_id=message.user_id,
                text=message.text,
                reason=f"Оскорбление: {abuse_reason}; предупреждение {warning_count}/"
                f"{self._warning_limit}",
                created_at=message.created_at,
            )
            logger.info(
                "Abuse moderation warning: chat_id=%s user_id=%s message_id=%s "
                "warning_count=%s reason='%s'",
                message.chat_id,
                message.user_id,
                message.message_id,
                warning_count,
                compact_log_text(abuse_reason, 400),
            )
            return moderation_result

        mute_until = message.created_at + timedelta(seconds=self._mute_duration_seconds)
        self._chat_member_repository.mute_member_for_abuse(
            message.chat_id,
            message.user_id,
            muted_until=mute_until,
            created_at=message.created_at,
        )
        self._spam_log_repository.add_entry(
            chat_id=message.chat_id,
            user_id=message.user_id,
            text=message.text,
            reason=f"Оскорбление: {abuse_reason}; мут на {self._mute_duration_seconds} секунд",
            created_at=message.created_at,
        )
        logger.info(
            "Abuse moderation mute: chat_id=%s user_id=%s message_id=%s mute_until=%s "
            "reason='%s'",
            message.chat_id,
            message.user_id,
            message.message_id,
            mute_until.isoformat(),
            compact_log_text(abuse_reason, 400),
        )
        return GroupMessageResult(
            action=GroupMessageAction.MUTE_USER,
            reply_text=self._build_mute_text(),
            reason=abuse_reason,
            mute_until=mute_until,
        )

    def detect_abuse(self, message: IncomingMessage) -> str | None:
        """Проверяет, есть ли в сообщении адресное оскорбление."""
        abuse_word = next(
            (word for word, pattern in self._abuse_patterns if pattern.search(message.text)),
            None,
        )
        if abuse_word is None:
            logger.info(
                "Abuse moderation passed: no abuse marker chat_id=%s user_id=%s "
                "message_id=%s",
                message.chat_id,
                message.user_id,
                message.message_id,
            )
            return None

        if not self._has_direct_address(message):
            logger.info(
                "Abuse moderation passed: abuse marker without direct address "
                "chat_id=%s user_id=%s message_id=%s marker='%s' text='%s'",
                message.chat_id,
                message.user_id,
                message.message_id,
                abuse_word,
                compact_log_text(message.text, 500),
            )
            return None

        return f"Адресное оскорбление: {abuse_word}"

    def _has_direct_address(self, message: IncomingMessage) -> bool:
        """Отличает перепалку между участниками от общей эмоциональной реплики."""
        if message.reply_to_user_id is not None and not message.is_reply_to_bot:
            return True
        if message.mention_count > int(message.mentions_bot):
            return True
        return bool(_DIRECT_ADDRESS_RE.search(message.text))

    def _build_warning_text(self, warning_count: int) -> str:
        """Формирует текст предупреждения за оскорбления."""
        return (
            "Пожалуйста, общайтесь уважительно и не оскорбляйте друг друга. "
            f"Это предупреждение {warning_count}/{self._warning_limit}. "
            "Если оскорбления продолжатся, отправка сообщений в группу будет "
            "временно ограничена."
        )

    def _build_mute_text(self) -> str:
        """Формирует текст ответа после мута."""
        return (
            "Пожалуйста, общайтесь уважительно и не оскорбляйте друг друга. "
            "Пользователь временно ограничен в отправке сообщений в группу на 24 часа."
        )
