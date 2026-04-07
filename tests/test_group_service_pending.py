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
        # Вопрос адресован конкретному пользователю → ignore (как в реальном triage)
        if message.mention_targets:
            return TriageDecision(action="ignore", reason="Вопрос адресован пользователю")
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
            chat_id=1,
            user_id=10,
            message_id=1,
            text="Где поменять деньги?",
            has_question=True,
        )
    )

    assert result.action == GroupMessageAction.PENDING_REPLY


@pytest.mark.asyncio
async def test_human_reply_cancels_pending(services) -> None:
    """Reply другого пользователя на вопрос должен снять этот конкретный pending-вопрос."""
    service, pending = services

    # Сохраняем старый вопрос от user_id=10, message_id=1
    pending.add(
        chat_id=1,
        message_id=1,
        user_id=10,
        question="Старый вопрос",
        created_at=datetime.now(UTC) - timedelta(minutes=6),
    )

    # user_id=20 делает reply именно на message_id=1 — закрывает pending
    await service.process_message(
        IncomingMessage.build(
            chat_id=1,
            user_id=20,
            message_id=2,
            text="Ок, я знаю ответ",
            has_question=False,
            reply_to_message_id=1,
        )
    )

    assert pending.find_ready(chat_id=1, cutoff_minutes=5) == []


@pytest.mark.asyncio
async def test_two_questions_same_author_both_stay_pending(services) -> None:
    """Два вопроса от одного автора — оба остаются в pending, никто не закрывает друг друга."""
    service, pending = services

    old_time = datetime.now(UTC) - timedelta(minutes=6)
    pending.add(
        chat_id=1,
        message_id=1,
        user_id=10,
        question="Первый вопрос",
        created_at=old_time,
    )

    # тот же user_id=10 задаёт новый вопрос — первый должен остаться в pending
    await service.process_message(
        IncomingMessage.build(
            chat_id=1,
            user_id=10,
            message_id=2,
            text="Второй вопрос?",
            has_question=True,
        )
    )

    # cutoff_minutes=0 чтобы получить все pending, включая только что добавленный
    ready = pending.find_ready(chat_id=1, cutoff_minutes=0)
    message_ids = {r["message_id"] for r in ready}
    assert 1 in message_ids  # первый вопрос остался
    assert 2 in message_ids  # новый вопрос добавился


@pytest.mark.asyncio
async def test_non_question_not_saved_to_pending(services) -> None:
    """Сообщение без вопроса не должно попадать в pending_questions."""
    service, pending = services

    await service.process_message(
        IncomingMessage.build(
            chat_id=1,
            user_id=10,
            message_id=1,
            text="Спасибо всем, всё понятно",
            has_question=False,
        )
    )

    assert pending.find_ready(chat_id=1, cutoff_minutes=0) == []


@pytest.mark.asyncio
async def test_question_directed_at_user_not_saved_to_pending(services) -> None:
    """Вопрос, адресованный конкретному участнику, не должен попадать в pending_questions."""
    service, pending = services

    await service.process_message(
        IncomingMessage.build(
            chat_id=1,
            user_id=10,
            message_id=1,
            text="@ivan_petrov где ты сейчас?",
            has_question=True,
            mention_targets=("ivan_petrov",),
        )
    )

    assert pending.find_ready(chat_id=1, cutoff_minutes=0) == []


@pytest.mark.asyncio
async def test_reply_to_question_closes_only_that_question(services) -> None:
    """Reply к message_id вопроса закрывает только его, другие pending остаются открытыми."""
    service, pending = services

    old_time = datetime.now(UTC) - timedelta(minutes=6)

    # Q1 — вопрос 1, Q2 — вопрос 2
    pending.add(chat_id=1, message_id=10, user_id=10, question="Пляж?", created_at=old_time)
    pending.add(chat_id=1, message_id=20, user_id=11, question="Такси?", created_at=old_time)

    # Участник отвечает именно на Q2 (reply_to_message_id=20)
    await service.process_message(
        IncomingMessage.build(
            chat_id=1,
            user_id=99,
            message_id=30,
            text="На такси — вызывай через Grab",
            has_question=False,
            reply_to_message_id=20,
        )
    )

    # Q2 закрыт — не попадает в ready
    assert pending.get_open_by_message_id(chat_id=1, message_id=20) is None
    # Q1 остался открытым
    ready = pending.find_ready(chat_id=1, cutoff_minutes=5)
    assert any(r["message_id"] == 10 for r in ready)


@pytest.mark.asyncio
async def test_non_reply_message_does_not_close_pending(services) -> None:
    """Обычное сообщение без reply не должно закрывать pending-вопросы."""
    service, pending = services

    old_time = datetime.now(UTC) - timedelta(minutes=6)
    pending.add(chat_id=1, message_id=10, user_id=10, question="Вопрос?", created_at=old_time)

    # Сообщение без reply_to_message_id от другого пользователя
    await service.process_message(
        IncomingMessage.build(
            chat_id=1,
            user_id=99,
            message_id=11,
            text="Отличная погода сегодня!",
            has_question=False,
        )
    )

    # Вопрос остался открытым
    ready = pending.find_ready(chat_id=1, cutoff_minutes=5)
    assert any(r["message_id"] == 10 for r in ready)


@pytest.mark.asyncio
async def test_author_reply_to_own_question_does_not_close_it(services) -> None:
    """Автор не может закрыть свой же вопрос через reply."""
    service, pending = services

    old_time = datetime.now(UTC) - timedelta(minutes=6)
    pending.add(chat_id=1, message_id=10, user_id=10, question="Мой вопрос?", created_at=old_time)

    # Тот же user_id=10 делает reply на свой вопрос
    await service.process_message(
        IncomingMessage.build(
            chat_id=1,
            user_id=10,
            message_id=11,
            text="Никто не знает?",
            has_question=True,
            reply_to_message_id=10,
        )
    )

    # Вопрос должен остаться открытым
    assert pending.get_open_by_message_id(chat_id=1, message_id=10) is not None


@pytest.mark.asyncio
async def test_bot_does_not_answer_twice(services) -> None:
    """После mark_bot_answered бот не отвечает повторно на тот же вопрос."""
    service, pending = services

    old_time = datetime.now(UTC) - timedelta(minutes=6)
    pending.add(chat_id=1, message_id=5, user_id=10, question="Где пляж?", created_at=old_time)

    # Первый вызов — бот отвечает
    replies_first = await service.build_and_send_pending(chat_id=1)
    assert len(replies_first) == 1

    # Второй вызов — вопрос уже закрыт, ответа нет
    replies_second = await service.build_and_send_pending(chat_id=1)
    assert replies_second == []


@pytest.mark.asyncio
async def test_build_and_send_pending_returns_answers(services) -> None:
    """build_and_send_pending должен генерировать ответы на все готовые вопросы."""
    service, pending = services

    pending.add(
        chat_id=1,
        message_id=5,
        user_id=10,
        question="Где такси?",
        user_language="ru",
        created_at=datetime.now(UTC) - timedelta(minutes=7),
    )
    pending.add(
        chat_id=1,
        message_id=6,
        user_id=11,
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
