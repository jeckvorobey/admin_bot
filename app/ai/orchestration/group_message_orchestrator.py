"""AI orchestration для одного группового сообщения."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.ai.agents import AnswerAgent, TriageAgent
from app.ai.schemas import TriageDecision
from app.models.chat import ChatLogEntry
from app.models.incoming_message import IncomingMessage
from app.repositories.chat_log import ChatLogRepository
from app.repositories.faq import FAQRepository
from app.repositories.partner import PartnerRepository
from app.repositories.pending_question import PendingQuestionRepository
from app.utils.logging import compact_log_text

logger = logging.getLogger(__name__)


class GroupMessageOrchestrator:
    """Координирует triage-агента, локальный markdown lookup и answer-агента."""

    def __init__(
        self,
        faq_repository: FAQRepository | None = None,
        partner_repository: PartnerRepository | None = None,
        triage_agent: TriageAgent | None = None,
        answer_agent: AnswerAgent | None = None,
        chat_log_repository: ChatLogRepository | None = None,
        pending_question_repository: PendingQuestionRepository | None = None,
    ) -> None:
        self._faq_repository = faq_repository or FAQRepository()
        self._partner_repository = partner_repository or PartnerRepository()
        self._triage_agent = triage_agent or TriageAgent()
        self._answer_agent = answer_agent or AnswerAgent()
        self._chat_log_repository = chat_log_repository or ChatLogRepository()
        self._pending_question_repository = (
            pending_question_repository or PendingQuestionRepository()
        )

    async def classify_message(self, message: IncomingMessage) -> TriageDecision:
        """Возвращает решение `spam/reply/ignore`."""
        has_local_knowledge = self.has_local_knowledge(message.text)
        unanswered_question_minutes = self._check_unanswered_question(
            message.chat_id,
            message.created_at,
        )
        logger.info(
            "Orchestrator classify request: chat_id=%s user_id=%s message_id=%s "
            "has_local_knowledge=%s unanswered_question_minutes=%s text='%s'",
            message.chat_id,
            message.user_id,
            message.message_id,
            has_local_knowledge,
            unanswered_question_minutes,
            compact_log_text(message.text, 500),
        )

        decision = await self._triage_agent.classify(
            message,
            has_local_knowledge=has_local_knowledge,
            unanswered_question_minutes=unanswered_question_minutes,
        )
        logger.info(
            "Orchestrator classify response: chat_id=%s user_id=%s message_id=%s "
            "decision=%s reason='%s'",
            message.chat_id,
            message.user_id,
            message.message_id,
            decision.action,
            compact_log_text(decision.reason, 400),
        )
        return decision

    def has_local_knowledge(self, text: str) -> bool:
        """Проверяет, есть ли FAQ/partner trigger в markdown knowledge base."""
        faq = self._faq_repository.find_by_text(text)
        partner = self._partner_repository.find_by_text(text)
        logger.info(
            "Orchestrator local knowledge lookup: has_faq=%s faq_id=%s has_partner=%s "
            "partner_id=%s text='%s'",
            faq is not None,
            faq.id if faq else None,
            partner is not None,
            partner.id if partner else None,
            compact_log_text(text, 500),
        )
        return faq is not None or partner is not None

    def _check_unanswered_question(
        self,
        chat_id: int,
        current_time: datetime,
    ) -> int | None:
        """Проверяет есть ли pending-вопрос более 5 минут без ответа.

        Использует таблицу pending_questions — источник правды о неотвеченных вопросах.
        Возвращает количество минут прошедших с момента вопроса, или None.
        """
        ready = self._pending_question_repository.find_ready(chat_id, cutoff_minutes=5)
        if not ready:
            return None

        oldest = ready[0]
        created_at = datetime.fromisoformat(oldest["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)

        minutes_ago = int((current_time - created_at).total_seconds() / 60)
        logger.info(
            "Orchestrator found unanswered pending question: chat_id=%s "
            "minutes_ago=%s question='%s'",
            chat_id,
            minutes_ago,
            compact_log_text(oldest["question"], 200),
        )
        return minutes_ago

    async def build_answer(
        self,
        question: str,
        history: list[ChatLogEntry],
        *,
        user_language: str = "ru",
    ) -> str:
        """Генерирует ответ через FAQ/partners + web-search fallback."""
        faq = self._faq_repository.find_by_text(question)
        partner = self._partner_repository.find_by_text(question)
        logger.info(
            "Orchestrator answer request: history_size=%s has_faq=%s faq_id=%s "
            "has_partner=%s partner_id=%s user_language=%s question='%s'",
            len(history),
            faq is not None,
            faq.id if faq else None,
            partner is not None,
            partner.id if partner else None,
            user_language,
            compact_log_text(question, 500),
        )

        answer = await self._answer_agent.build_answer(
            question,
            history,
            faq=faq,
            partner=partner,
            user_language=user_language,
        )
        logger.info(
            "Orchestrator answer response: question='%s' answer='%s'",
            compact_log_text(question, 500),
            compact_log_text(answer, 700),
        )
        return answer
