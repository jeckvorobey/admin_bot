"""Сервис обработки групповых сообщений."""

from __future__ import annotations

import asyncio
import logging
import random

from app.ai.orchestration import GroupMessageOrchestrator
from app.core.telegram_config import (
    REPLY_DELAY_MAX_SECONDS,
    REPLY_DELAY_MIN_SECONDS,
)
from app.models.group_action import GroupMessageAction, GroupMessageResult
from app.models.incoming_message import IncomingMessage
from app.repositories.chat_log import ChatLogRepository
from app.repositories.chat_member import ChatMemberRepository
from app.repositories.spam_log import SpamLogRepository
from app.services.abuse import AbuseModerationService
from app.services.spam import SpamService
from app.utils.logging import compact_log_text

logger = logging.getLogger(__name__)


class GroupService:
    """Координирует spam pre-filter, triage-agent и answer-agent для группы."""

    def __init__(
        self,
        chat_log_repository: ChatLogRepository | None = None,
        chat_member_repository: ChatMemberRepository | None = None,
        message_orchestrator: GroupMessageOrchestrator | None = None,
        abuse_moderation_service: AbuseModerationService | None = None,
        spam_service: SpamService | None = None,
        reply_delay_seconds: tuple[float, float] = (
            REPLY_DELAY_MIN_SECONDS,
            REPLY_DELAY_MAX_SECONDS,
        ),
    ) -> None:
        self._chat_log_repository = chat_log_repository or ChatLogRepository()
        self._chat_member_repository = chat_member_repository or ChatMemberRepository()
        self._message_orchestrator = message_orchestrator or GroupMessageOrchestrator()
        self._reply_delay_seconds = reply_delay_seconds
        spam_log_repository = SpamLogRepository()
        self._abuse_moderation_service = abuse_moderation_service or AbuseModerationService(
            chat_member_repository=self._chat_member_repository,
            spam_log_repository=spam_log_repository,
        )
        self._spam_service = spam_service or SpamService(
            chat_log_repository=self._chat_log_repository,
            chat_member_repository=self._chat_member_repository,
            spam_log_repository=spam_log_repository,
        )

    async def process_message(self, message: IncomingMessage) -> GroupMessageResult:
        """Возвращает типизированное действие для входящего сообщения."""
        logger.info(
            "GroupService processing started: chat_id=%s user_id=%s message_id=%s text='%s'",
            message.chat_id,
            message.user_id,
            message.message_id,
            compact_log_text(message.text, 500),
        )

        spam_reason = await self._spam_service.detect_spam(message)
        if spam_reason is not None:
            self._spam_service.log_spam(message, spam_reason)
            self._chat_member_repository.touch_member(
                message.chat_id,
                message.user_id,
                message.created_at,
            )
            logger.info(
                "GroupService decision=delete source=pre_filter reason='%s' "
                "chat_id=%s user_id=%s message_id=%s",
                spam_reason,
                message.chat_id,
                message.user_id,
                message.message_id,
            )
            return GroupMessageResult(
                action=GroupMessageAction.DELETE_SPAM,
                reason=spam_reason,
            )

        abuse_result = self._abuse_moderation_service.moderate_message(message)
        if abuse_result is not None:
            logger.info(
                "GroupService decision=%s source=abuse_moderation reason='%s' "
                "warning_count=%s chat_id=%s user_id=%s message_id=%s",
                abuse_result.action,
                compact_log_text(abuse_result.reason, 400),
                abuse_result.warning_count,
                message.chat_id,
                message.user_id,
                message.message_id,
            )
            return abuse_result

        decision = await self._message_orchestrator.classify_message(message)
        logger.info(
            "GroupService triage decision=%s reason='%s' chat_id=%s user_id=%s "
            "message_id=%s",
            decision.action,
            compact_log_text(decision.reason, 400),
            message.chat_id,
            message.user_id,
            message.message_id,
        )

        if decision.action == "spam":
            self._spam_service.log_spam(message, decision.reason)
            self._chat_member_repository.touch_member(
                message.chat_id,
                message.user_id,
                message.created_at,
            )
            logger.info(
                "GroupService decision=delete source=triage reason='%s' "
                "chat_id=%s user_id=%s message_id=%s",
                compact_log_text(decision.reason, 400),
                message.chat_id,
                message.user_id,
                message.message_id,
            )
            return GroupMessageResult(
                action=GroupMessageAction.DELETE_SPAM,
                reason=decision.reason,
            )

        if decision.action == "ignore":
            self._chat_member_repository.touch_member(
                message.chat_id,
                message.user_id,
                message.created_at,
            )
            logger.info(
                "GroupService decision=ignore chat_id=%s user_id=%s message_id=%s",
                message.chat_id,
                message.user_id,
                message.message_id,
            )
            return GroupMessageResult(
                action=GroupMessageAction.IGNORE,
                reason=decision.reason,
            )

        reply_delay = random.uniform(*self._reply_delay_seconds)
        logger.info(
            "GroupService decision=reply waiting_before_answer_seconds=%.2f "
            "chat_id=%s user_id=%s message_id=%s",
            reply_delay,
            message.chat_id,
            message.user_id,
            message.message_id,
        )
        await asyncio.sleep(reply_delay)

        history = self._chat_log_repository.list_recent(message.chat_id, limit=20)
        logger.info(
            "GroupService history loaded: chat_id=%s entries=%s message_id=%s",
            message.chat_id,
            len(history),
            message.message_id,
        )

        answer = await self._message_orchestrator.build_answer(message.text, history)
        self._chat_log_repository.add_entry(
            chat_id=message.chat_id,
            user_id=message.user_id,
            question=message.text,
            answer=answer,
            created_at=message.created_at,
        )
        self._chat_member_repository.touch_member(
            message.chat_id,
            message.user_id,
            message.created_at,
        )
        logger.info(
            "GroupService decision=reply completed: chat_id=%s user_id=%s message_id=%s "
            "answer='%s'",
            message.chat_id,
            message.user_id,
            message.message_id,
            compact_log_text(answer, 700),
        )
        return GroupMessageResult(
            action=GroupMessageAction.REPLY,
            reply_text=answer,
            reason=decision.reason,
        )
