"""Лёгкий triage-агент для решения `spam/reply/ignore`."""

from __future__ import annotations

import logging

from app.ai.clients import GeminiClient
from app.ai.prompts import load_prompt
from app.ai.schemas import TriageDecision
from app.core.ai_config import TRIAGE_MODEL, load_bot_behavior
from app.models.incoming_message import IncomingMessage
from app.utils.logging import compact_log_text

logger = logging.getLogger(__name__)


class TriageAgent:
    """Классифицирует сообщение после локального spam pre-filter."""

    def __init__(self, gemini_client: GeminiClient | None = None) -> None:
        self._gemini_client = gemini_client or GeminiClient(
            model=TRIAGE_MODEL,
            system_instruction=load_prompt("triage.md"),
            temperature=1,
            max_output_tokens=96,
        )

    async def classify(
        self,
        message: IncomingMessage,
        *,
        has_local_knowledge: bool,
        unanswered_question_minutes: int | None = None,
    ) -> TriageDecision:
        """Возвращает решение triage-агента."""
        prompt = self._build_prompt(
            message,
            has_local_knowledge=has_local_knowledge,
            unanswered_question_minutes=unanswered_question_minutes,
        )
        logger.info(
            "TriageAgent prompt built: chat_id=%s user_id=%s message_id=%s prompt='%s'",
            message.chat_id,
            message.user_id,
            message.message_id,
            compact_log_text(prompt),
        )

        verdict = (await self._gemini_client.generate_text(prompt)).strip()
        if not verdict:
            decision = self._fallback_decision(
                message,
                has_local_knowledge=has_local_knowledge,
                unanswered_question_minutes=unanswered_question_minutes,
            )
            logger.info(
                "TriageAgent fallback decision: chat_id=%s user_id=%s message_id=%s "
                "action=%s reason='%s'",
                message.chat_id,
                message.user_id,
                message.message_id,
                decision.action,
                compact_log_text(decision.reason, 400),
            )
            return decision

        logger.info(
            "TriageAgent raw verdict: chat_id=%s user_id=%s message_id=%s verdict='%s'",
            message.chat_id,
            message.user_id,
            message.message_id,
            compact_log_text(verdict, 400),
        )

        decision = self._parse_verdict(
            verdict,
            message,
            has_local_knowledge=has_local_knowledge,
            unanswered_question_minutes=unanswered_question_minutes,
        )
        logger.info(
            "TriageAgent parsed decision: chat_id=%s user_id=%s message_id=%s "
            "action=%s reason='%s'",
            message.chat_id,
            message.user_id,
            message.message_id,
            decision.action,
            compact_log_text(decision.reason, 400),
        )
        return decision

    @staticmethod
    def _build_prompt(
        message: IncomingMessage,
        *,
        has_local_knowledge: bool,
        unanswered_question_minutes: int | None = None,
    ) -> str:
        """Собирает краткий triage prompt с контекстом поведения."""
        behavior = load_bot_behavior()
        context_lines = [
            "Сообщение для triage:",
            message.text.strip(),
            "",
            f"Есть вопрос: {'да' if message.has_question else 'нет'}",
            f"Есть упоминание бота: {'да' if message.mentions_bot else 'нет'}",
            f"Это reply на бота: {'да' if message.is_reply_to_bot else 'нет'}",
            f"Есть локальный knowledge trigger: {'да' if has_local_knowledge else 'нет'}",
            f"Есть ссылки: {'да' if message.has_links else 'нет'}",
            f"Количество упоминаний: {message.mention_count}",
            f"ID источника форварда: {message.forward_chat_id or 'нет'}",
        ]
        if unanswered_question_minutes is not None:
            context_lines.append(
                f"Неотвеченный вопрос в чате: {unanswered_question_minutes} мин назад"
            )

        return "\n".join(context_lines).strip() + "\n\n" + behavior.strip()

    def _parse_verdict(
        self,
        verdict: str,
        message: IncomingMessage,
        *,
        has_local_knowledge: bool,
        unanswered_question_minutes: int | None = None,
    ) -> TriageDecision:
        """Парсит LLM-ответ и безопасно падает в deterministic fallback."""
        normalized = verdict.strip()
        if normalized.casefold().startswith("spam:"):
            reason = normalized.split(":", 1)[1].strip()
            return TriageDecision(action="spam", reason=reason or "AI triage определил спам")
        if normalized.casefold().startswith("reply:"):
            reason = normalized.split(":", 1)[1].strip()
            return TriageDecision(action="reply", reason=reason or "Нужен ответ")
        if normalized.casefold().startswith("ignore:"):
            reason = normalized.split(":", 1)[1].strip()
            return TriageDecision(action="ignore", reason=reason or "Ответ не нужен")
        return self._fallback_decision(
            message,
            has_local_knowledge=has_local_knowledge,
            unanswered_question_minutes=unanswered_question_minutes,
        )

    @staticmethod
    def _fallback_decision(
        message: IncomingMessage,
        *,
        has_local_knowledge: bool,
        unanswered_question_minutes: int | None = None,
    ) -> TriageDecision:
        """Детерминированное решение без LLM-ответа."""
        if unanswered_question_minutes is not None and unanswered_question_minutes >= 5:
            return TriageDecision(
                action="reply",
                reason=f"Неотвеченный вопрос {unanswered_question_minutes} мин назад",
            )
        if message.mentions_bot or message.is_reply_to_bot:
            return TriageDecision(action="reply", reason="Есть обращение к боту")
        if message.has_question:
            if has_local_knowledge:
                return TriageDecision(action="reply", reason="Есть вопрос по локальной базе знаний")
            return TriageDecision(action="reply", reason="Есть вопрос без локального FAQ")
        return TriageDecision(action="ignore", reason="Нет вопроса и обращения к боту")
