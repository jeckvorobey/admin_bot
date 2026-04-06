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

        verdict = ""
        try:
            verdict = (await self._gemini_client.generate_text(prompt)).strip()
        except Exception:
            logger.exception(
                "TriageAgent generate_text failed: chat_id=%s user_id=%s message_id=%s",
                message.chat_id,
                message.user_id,
                message.message_id,
            )
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
        mentions_other_users = bool(message.mention_targets)
        context_lines = [
            "Message for triage:",
            message.text.strip(),
            "",
            f"Has question mark or question word: {'yes' if message.has_question else 'no'}",
            f"Bot explicitly mentioned: {'yes' if message.mentions_bot else 'no'}",
            f"Is reply to bot: {'yes' if message.is_reply_to_bot else 'no'}",
            "Mentions other users (not bot): "
            + (
                "yes — " + ", ".join(f"@{u}" for u in message.mention_targets)
                if mentions_other_users
                else "no"
            ),
            f"Has local knowledge match: {'yes' if has_local_knowledge else 'no'}",
            f"Has links: {'yes' if message.has_links else 'no'}",
            f"Forward source chat id: {message.forward_chat_id or 'none'}",
            f"User language: {message.user_language}",
        ]
        if unanswered_question_minutes is not None:
            context_lines.append(
                f"Unanswered question in chat: {unanswered_question_minutes} min ago"
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
                reason=f"Unanswered question {unanswered_question_minutes} min ago",
            )
        if message.mentions_bot or message.is_reply_to_bot:
            return TriageDecision(action="reply", reason="Bot explicitly addressed")
        # Вопрос, адресованный конкретному пользователю → не вмешиваться
        if message.mention_targets:
            return TriageDecision(action="ignore", reason="Question directed at specific user")
        if message.has_question and has_local_knowledge:
            return TriageDecision(action="reply", reason="Question matches local knowledge base")
        return TriageDecision(action="ignore", reason="No bot mention, no local knowledge match")
