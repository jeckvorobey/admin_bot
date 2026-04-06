"""Тесты orchestration слоя AI-агентов."""

from __future__ import annotations

import pytest

from app.ai.agents import AnswerAgent, TriageAgent
from app.ai.orchestration import GroupMessageOrchestrator
from app.ai.schemas import TriageDecision
from app.models.incoming_message import IncomingMessage
from app.repositories.chat_log import ChatLogRepository
from app.repositories.faq import FAQRepository
from app.repositories.partner import PartnerRepository


class FakeAnswerAgent(AnswerAgent):
    """Детерминированный answer-agent stub для проверки orchestration."""

    def __init__(self) -> None:
        pass

    async def build_answer(self, question, history, *, faq=None, partner=None, user_language="ru"):
        if faq is not None:
            answer = f"{faq.answer}\n{faq.link}".strip()
        else:
            answer = f"AI: {question} / history={len(history)}"

        if partner is not None and partner.link not in answer:
            answer = f"{answer}\n\n{partner.description} {partner.name}: {partner.link}"
        return answer


class FakeTriageAgent(TriageAgent):
    """Stub triage-агента с fallback логикой без внешнего API."""

    def __init__(self) -> None:
        pass

    async def classify(
        self,
        message: IncomingMessage,
        *,
        has_local_knowledge: bool,
        unanswered_question_minutes: int | None = None,
    ) -> TriageDecision:
        if (
            message.mentions_bot
            or message.is_reply_to_bot
            or has_local_knowledge
            or (unanswered_question_minutes is not None and unanswered_question_minutes >= 5)
        ):
            return TriageDecision(action="reply", reason="Нужен ответ")
        if message.has_question:
            return TriageDecision(action="reply", reason="Обычный вопрос")
        return TriageDecision(action="ignore", reason="Ответ не нужен")


@pytest.fixture()
def orchestrator() -> GroupMessageOrchestrator:
    """Создаёт orchestrator с markdown-backed repositories и stub агентами."""
    return GroupMessageOrchestrator(
        faq_repository=FAQRepository(),
        partner_repository=PartnerRepository(),
        triage_agent=FakeTriageAgent(),
        answer_agent=FakeAnswerAgent(),
    )


@pytest.mark.asyncio
async def test_orchestrator_replies_with_local_faq(orchestrator: GroupMessageOrchestrator) -> None:
    """FAQ trigger должен вернуть локальный Markdown-ответ и ссылку."""
    decision = await orchestrator.classify_message(
        IncomingMessage.build(
            chat_id=1,
            user_id=2,
            message_id=3,
            text="Где обменять USDT?",
            has_question=True,
        )
    )
    answer = await orchestrator.build_answer("Где обменять USDT?", [])

    assert decision.action == "reply"
    assert "обменник" in answer.lower()
    assert "https://t.me/+ui-tQ4T-jrNlNmQy" in answer


@pytest.mark.asyncio
async def test_orchestrator_matches_semantic_exchange_question(
    orchestrator: GroupMessageOrchestrator,
) -> None:
    """Фраза без слова `обмен` должна всё равно матчиться на exchange FAQ."""
    message = IncomingMessage.build(
        chat_id=1,
        user_id=2,
        message_id=3,
        text="Ребят, а как поменять деньги в Дананге?",
        has_question=True,
    )

    decision = await orchestrator.classify_message(message)
    answer = await orchestrator.build_answer(message.text, [])

    assert decision.action == "reply"
    assert "AntEx" in answer
    assert "t.me/+ui-tQ4T-jrNlNmQy" in answer


@pytest.mark.asyncio
async def test_orchestrator_uses_ai_fallback_without_local_faq(
    orchestrator: GroupMessageOrchestrator,
) -> None:
    """Если FAQ нет, должен использоваться AnswerAgent fallback."""
    answer = await orchestrator.build_answer("Где купить SIM карту?", [])

    assert answer.startswith("AI: Где купить SIM карту?")


@pytest.mark.asyncio
async def test_orchestrator_appends_partner_recommendation_for_triggered_category(
    tmp_path,
    monkeypatch,
    orchestrator: GroupMessageOrchestrator,
) -> None:
    """Партнёрская рекомендация должна добавляться в конец ответа."""
    from app.core.config import settings
    from app.databases.sqlite import init_db

    monkeypatch.setattr(settings, "database_path", str(tmp_path / "knowledge.db"))
    init_db()
    ChatLogRepository().add_entry(
        chat_id=1,
        user_id=10,
        question="старый вопрос",
        answer="старый ответ",
    )

    answer = await orchestrator.build_answer(
        "Где аренда квартиры?",
        ChatLogRepository().list_recent(1, 20),
    )

    assert answer.startswith("AI: Где аренда квартиры?")
    assert "Партнёр Б" in answer
    assert "https://example.com/rent" in answer
