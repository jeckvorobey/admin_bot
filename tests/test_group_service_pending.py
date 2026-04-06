"""Тесты механизма отложенных ответов (5-минутное правило)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.ai.schemas import TriageDecision
from app.core.config import settings
from app.databases.sqlite import init_db
from app.models.group_action import GroupMessageAction
from app.models.incoming_message import IncomingMessage
from app.repositories.chat_log import ChatLogRepository
from app.repositories.chat_member import ChatMemberRepository
from app.repositories.pending_question import PendingQuestionRepository
from app.repositories.spam_log import SpamLogRepository
from app.services.abuse import AbuseModerationService
from app.services.spam import SpamService
from app.telegram.services.group_service import GroupService


class FakeOrchestrator:
    """Stub оркестратора с детерминированными ответами."""

    async def classify_message(self, message: IncomingMessage) -> TriageDecision:
        if message.has_question:
            return TriageDecision(action="reply", reason="Есть вопрос")
        return TriageDecision(action="ignore", reason="Нет вопроса")

    async def build_answer(self, text, history, *, user_language="ru"):
        return f"Ответ на: {text}"


@pytest.fixture()
def services(tmp_path, monkeypatch):
    """Создаёт GroupService и репозитории на временной SQLite базе."""
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "knowledge.db"))
    init_db()
    chat_log = ChatLogRepository()
    chat_member = ChatMemberRepository()
    spam_log = SpamLogRepository()
    pending = PendingQuestionRepository()
    service = GroupService(
        chat_log_repository=chat_log,
        chat_member_repository=chat_member,
        message_orchestrator=FakeOrchestrator(),
        pending_question_repository=pending,
        abuse_moderation_service=AbuseModerationService(
            chat_member_repository=chat_member,
            spam_log_repository=spam_log,
        ),
        spam_service=SpamService(
            chat_log_repository=chat_log,
            chat_member_repository=chat_member,
            spam_log_repository=spam_log,
        ),
    )
    return service, pending


@pytest.mark.asyncio
async def test_question_returns_pending_reply(services) -> None:
    """Вопрос с FAQ-триггером должен возвращать PENDING_REPLY, не REPLY."""
    service, _ = services
    result = await service.process_message(
        IncomingMessage.build(
            chat_id=1, user_id=10, message_id=1,
            text="Где поменять деньги?",
            has_question=True,
        )
    )

    assert result.action == GroupMessageAction.PENDING_REPLY


@pytest.mark.asyncio
async def test_human_reply_cancels_pending(services) -> None:
    """Ответ другого пользователя должен снять pending-вопрос."""
    service, pending = services

    # Сохраняем старый вопрос от user_id=10
    pending.add(
        chat_id=1, message_id=1, user_id=10,
        question="Старый вопрос",
        created_at=datetime.now(UTC) - timedelta(minutes=6),
    )

    # user_id=20 пишет что-то — закрывает pending
    await service.process_message(
        IncomingMessage.build(
            chat_id=1, user_id=20, message_id=2,
            text="Ок, я знаю ответ",
            has_question=False,
        )
    )

    assert pending.find_ready(chat_id=1, cutoff_minutes=5) == []


@pytest.mark.asyncio
async def test_own_followup_does_not_cancel_pending(services) -> None:
    """Follow-up сообщение от того же автора вопроса не закрывает его pending."""
    service, pending = services

    old_time = datetime.now(UTC) - timedelta(minutes=6)
    pending.add(
        chat_id=1, message_id=1, user_id=10,
        question="Мой вопрос",
        created_at=old_time,
    )

    # тот же user_id=10 пишет снова — не должно закрыть
    await service.process_message(
        IncomingMessage.build(
            chat_id=1, user_id=10, message_id=2,
            text="Кто-нибудь знает?",
            has_question=True,
        )
    )

    # Первый вопрос должен остаться ready
    ready = pending.find_ready(chat_id=1, cutoff_minutes=5)
    assert any(r["message_id"] == 1 for r in ready)


@pytest.mark.asyncio
async def test_build_and_send_pending_returns_answers(services) -> None:
    """build_and_send_pending должен генерировать ответы на все готовые вопросы."""
    service, pending = services

    pending.add(
        chat_id=1, message_id=5, user_id=10,
        question="Где такси?",
        user_language="ru",
        created_at=datetime.now(UTC) - timedelta(minutes=7),
    )
    pending.add(
        chat_id=1, message_id=6, user_id=11,
        question="Где еда?",
        user_language="en",
        created_at=datetime.now(UTC) - timedelta(minutes=6),
    )

    replies = await service.build_and_send_pending(chat_id=1)

    assert len(replies) == 2
    message_ids = {r[0] for r in replies}
    assert 5 in message_ids
    assert 6 in message_ids
    # После отправки все pending должны быть закрыты
    assert pending.find_ready(chat_id=1, cutoff_minutes=5) == []
