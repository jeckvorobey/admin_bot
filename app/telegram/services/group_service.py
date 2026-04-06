"""Сервис обработки групповых сообщений."""

from __future__ import annotations

import logging

from app.ai.orchestration import GroupMessageOrchestrator
from app.models.group_action import GroupMessageAction, GroupMessageResult
from app.models.incoming_message import IncomingMessage
from app.repositories.chat_log import ChatLogRepository
from app.repositories.chat_member import ChatMemberRepository
from app.repositories.pending_question import PendingQuestionRepository
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
        pending_question_repository: PendingQuestionRepository | None = None,
    ) -> None:
        self._chat_log_repository = chat_log_repository or ChatLogRepository()
        self._chat_member_repository = chat_member_repository or ChatMemberRepository()
        self._message_orchestrator = message_orchestrator or GroupMessageOrchestrator()
        self._pending_question_repository = (
            pending_question_repository or PendingQuestionRepository()
        )
        self._spam_log_repository = SpamLogRepository()
        self._abuse_moderation_service = abuse_moderation_service or AbuseModerationService(
            chat_member_repository=self._chat_member_repository,
            spam_log_repository=self._spam_log_repository,
        )
        self._spam_service = spam_service or SpamService(
            chat_log_repository=self._chat_log_repository,
            chat_member_repository=self._chat_member_repository,
            spam_log_repository=self._spam_log_repository,
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

        # Любое живое сообщение от другого пользователя = кто-то ответил → снимаем pending
        answered = self._pending_question_repository.mark_answered(
            message.chat_id,
            except_user_id=message.user_id,
        )
        if answered:
            logger.info(
                "GroupService pending questions answered by human activity: "
                "chat_id=%s count=%s user_id=%s",
                message.chat_id,
                answered,
                message.user_id,
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

        # Triage решил REPLY → сохраняем в pending, откладываем на 5 минут
        self._pending_question_repository.add(
            chat_id=message.chat_id,
            message_id=message.message_id,
            user_id=message.user_id,
            question=message.text,
            user_language=message.user_language,
            created_at=message.created_at,
        )
        self._chat_member_repository.touch_member(
            message.chat_id,
            message.user_id,
            message.created_at,
        )
        logger.info(
            "GroupService decision=pending_reply scheduled: chat_id=%s user_id=%s message_id=%s",
            message.chat_id,
            message.user_id,
            message.message_id,
        )
        return GroupMessageResult(
            action=GroupMessageAction.PENDING_REPLY,
            reason=decision.reason,
        )

    async def build_and_send_pending(self, chat_id: int) -> list[tuple[int, str]]:
        """Генерирует ответы на все готовые pending-вопросы.

        Возвращает список (message_id, answer) для отправки handler-слоем.
        """
        ready = self._pending_question_repository.find_ready(chat_id)
        if not ready:
            return []

        results: list[tuple[int, str]] = []
        history = self._chat_log_repository.list_recent(chat_id, limit=20)

        for row in ready:
            answer = await self._message_orchestrator.build_answer(
                row["question"],
                history,
                user_language=row["user_language"],
            )
            self._chat_log_repository.add_entry(
                chat_id=chat_id,
                user_id=row["user_id"],
                question=row["question"],
                answer=answer,
            )
            self._pending_question_repository.mark_bot_answered(row["id"])
            logger.info(
                "GroupService pending reply sent: chat_id=%s message_id=%s answer='%s'",
                chat_id,
                row["message_id"],
                compact_log_text(answer, 700),
            )
            results.append((row["message_id"], answer))

        return results
