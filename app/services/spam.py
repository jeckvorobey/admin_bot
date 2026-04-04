"""Сервис антиспама."""

from __future__ import annotations

import logging
import re

from app.core.spam_config import (
    SPAM_BLACKLISTED_DOMAINS,
    SPAM_DUPLICATE_WINDOW_SECONDS,
    SPAM_FORWARD_WHITELIST_CHAT_IDS,
    SPAM_MAX_MENTIONS,
    SPAM_NEW_MEMBER_TTL_SECONDS,
    load_spam_stop_words,
)
from app.models.incoming_message import IncomingMessage
from app.repositories.chat_log import ChatLogRepository
from app.repositories.chat_member import ChatMemberRepository
from app.repositories.spam_log import SpamLogRepository
from app.utils.logging import compact_log_text

_DOMAIN_RE = re.compile(r"(?:https?://)?(?:www\.)?([a-z0-9а-яё.-]+\.[a-zа-яё]{2,})", re.IGNORECASE)
logger = logging.getLogger(__name__)


class SpamService:
    """Правила удаления спама и запись причин в `spam_log`."""

    def __init__(
        self,
        chat_log_repository: ChatLogRepository | None = None,
        chat_member_repository: ChatMemberRepository | None = None,
        spam_log_repository: SpamLogRepository | None = None,
        stop_words: list[str] | None = None,
        blacklisted_domains: tuple[str, ...] = SPAM_BLACKLISTED_DOMAINS,
        forward_whitelist_chat_ids: frozenset[int] = SPAM_FORWARD_WHITELIST_CHAT_IDS,
        new_member_ttl_seconds: int = SPAM_NEW_MEMBER_TTL_SECONDS,
        duplicate_window_seconds: int = SPAM_DUPLICATE_WINDOW_SECONDS,
        max_mentions: int = SPAM_MAX_MENTIONS,
    ) -> None:
        self._chat_log_repository = chat_log_repository or ChatLogRepository()
        self._chat_member_repository = chat_member_repository or ChatMemberRepository()
        self._spam_log_repository = spam_log_repository or SpamLogRepository()
        self._stop_words = load_spam_stop_words() if stop_words is None else stop_words
        self._blacklisted_domains = tuple(domain.casefold() for domain in blacklisted_domains)
        self._forward_whitelist_chat_ids = forward_whitelist_chat_ids
        self._new_member_ttl_seconds = new_member_ttl_seconds
        self._duplicate_window_seconds = duplicate_window_seconds
        self._max_mentions = max_mentions

    async def detect_spam(self, message: IncomingMessage) -> str | None:
        """Детерминированный spam pre-filter до triage-агента."""
        member_age = self._chat_member_repository.get_member_age_seconds(
            chat_id=message.chat_id,
            user_id=message.user_id,
            now=message.created_at,
        )
        logger.info(
            "Spam pre-filter started: chat_id=%s user_id=%s message_id=%s "
            "member_age_seconds=%s has_links=%s mention_count=%s "
            "forward_chat_id=%s text='%s'",
            message.chat_id,
            message.user_id,
            message.message_id,
            member_age,
            message.has_links,
            message.mention_count,
            message.forward_chat_id,
            compact_log_text(message.text, 500),
        )
        if message.has_links and member_age < self._new_member_ttl_seconds:
            logger.info(
                "Spam pre-filter matched: reason='Ссылка от нового участника' "
                "chat_id=%s user_id=%s message_id=%s",
                message.chat_id,
                message.user_id,
                message.message_id,
            )
            return "Ссылка от нового участника"

        if message.mention_count >= self._max_mentions:
            logger.info(
                "Spam pre-filter matched: reason='Слишком много упоминаний' "
                "chat_id=%s user_id=%s message_id=%s mention_count=%s",
                message.chat_id,
                message.user_id,
                message.message_id,
                message.mention_count,
            )
            return "Слишком много упоминаний"

        if (
            message.forward_chat_id is not None
            and message.forward_chat_id not in self._forward_whitelist_chat_ids
        ):
            logger.info(
                "Spam pre-filter matched: reason='Форвард не из белого списка' "
                "chat_id=%s user_id=%s message_id=%s forward_chat_id=%s",
                message.chat_id,
                message.user_id,
                message.message_id,
                message.forward_chat_id,
            )
            return "Форвард не из белого списка"

        normalized_text = message.text.casefold()
        if any(stop_word in normalized_text for stop_word in self._stop_words):
            logger.info(
                "Spam pre-filter matched: reason='Стоп-слово антиспама' "
                "chat_id=%s user_id=%s message_id=%s",
                message.chat_id,
                message.user_id,
                message.message_id,
            )
            return "Стоп-слово антиспама"

        if self._contains_blacklisted_domain(normalized_text):
            logger.info(
                "Spam pre-filter matched: reason='Домен из чёрного списка' "
                "chat_id=%s user_id=%s message_id=%s",
                message.chat_id,
                message.user_id,
                message.message_id,
            )
            return "Домен из чёрного списка"

        duplicates = self._chat_log_repository.count_duplicate_questions(
            chat_id=message.chat_id,
            user_id=message.user_id,
            question=message.text,
            window_seconds=self._duplicate_window_seconds,
            now=message.created_at,
        )
        if duplicates > 0:
            logger.info(
                "Spam pre-filter matched: reason='Одинаковый текст от разных пользователей "
                "за 10 минут' chat_id=%s user_id=%s message_id=%s duplicates=%s",
                message.chat_id,
                message.user_id,
                message.message_id,
                duplicates,
            )
            return "Одинаковый текст от разных пользователей за 10 минут"

        logger.info(
            "Spam pre-filter passed: chat_id=%s user_id=%s message_id=%s",
            message.chat_id,
            message.user_id,
            message.message_id,
        )
        return None

    def log_spam(self, message: IncomingMessage, reason: str) -> None:
        """Пишет удалённое сообщение в `spam_log`."""
        self._spam_log_repository.add_entry(
            chat_id=message.chat_id,
            user_id=message.user_id,
            text=message.text,
            reason=reason,
            created_at=message.created_at,
        )
        logger.info(
            "Spam log saved: chat_id=%s user_id=%s message_id=%s reason='%s' text='%s'",
            message.chat_id,
            message.user_id,
            message.message_id,
            compact_log_text(reason, 300),
            compact_log_text(message.text, 500),
        )

    def _contains_blacklisted_domain(self, text: str) -> bool:
        """Проверяет домены из чёрного списка."""
        domains = {match.group(1).casefold() for match in _DOMAIN_RE.finditer(text)}
        return any(
            domain == blocked or domain.endswith(f".{blocked}")
            for domain in domains
            for blocked in self._blacklisted_domains
        )
