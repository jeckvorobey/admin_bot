"""Тесты orchestration слоя Telegram-группы."""

from __future__ import annotations

import pytest

from app.ai.schemas import TriageDecision
from app.core.config import settings
from app.databases.sqlite import init_db
from app.models.group_action import GroupMessageAction
from app.models.incoming_message import IncomingMessage
from app.repositories.chat_log import ChatLogRepository
from app.repositories.chat_member import ChatMemberRepository
from app.repositories.spam_log import SpamLogRepository
from app.services.abuse import AbuseModerationService
from app.services.spam import SpamService
from app.telegram.services.group_service import GroupService


class FakeMessageOrchestrator:
    """Stub нового AI-orchestrator контракта."""

    async def classify_message(self, message: IncomingMessage) -> TriageDecision:
        has_exchange_trigger = (
            "usdt" in message.text.casefold() or "обмен" in message.text.casefold()
        )
        if message.has_question and has_exchange_trigger:
            return TriageDecision(action="reply", reason="Есть вопрос по локальной базе знаний")
        return TriageDecision(action="ignore", reason="Ответ не нужен")

    async def build_answer(self, text, history):
        return f"Ответ: {text}"


@pytest.fixture()
def group_service(tmp_path, monkeypatch) -> GroupService:
    """Создаёт GroupService без задержки ответа."""
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "knowledge.db"))
    init_db()
    chat_log = ChatLogRepository()
    chat_member = ChatMemberRepository()
    spam_log = SpamLogRepository()
    return GroupService(
        chat_log_repository=chat_log,
        chat_member_repository=chat_member,
        message_orchestrator=FakeMessageOrchestrator(),
        reply_delay_seconds=(0, 0),
        abuse_moderation_service=AbuseModerationService(
            chat_member_repository=chat_member,
            spam_log_repository=spam_log,
            abuse_words=["дурак", "идиот"],
            warning_limit=2,
        ),
        spam_service=SpamService(
            chat_log_repository=chat_log,
            chat_member_repository=chat_member,
            spam_log_repository=spam_log,
            stop_words=["free usdt"],
        ),
    )


@pytest.mark.asyncio
async def test_reply_on_question_with_trigger(group_service: GroupService) -> None:
    """Если есть явный вопрос и trigger, бот должен ответить."""
    result = await group_service.process_message(
        IncomingMessage.build(
            chat_id=1,
            user_id=10,
            message_id=1,
            text="Где обменять USDT?",
            has_question=True,
        )
    )

    assert result.action == GroupMessageAction.REPLY
    assert result.reply_text == "Ответ: Где обменять USDT?"


@pytest.mark.asyncio
async def test_ignore_non_question_without_mention(group_service: GroupService) -> None:
    """Если это не вопрос и бота не звали, бот должен молчать."""
    result = await group_service.process_message(
        IncomingMessage.build(
            chat_id=1,
            user_id=10,
            message_id=1,
            text="Просто болтаем",
            has_question=False,
        )
    )

    assert result.action == GroupMessageAction.IGNORE
    assert result.reply_text is None


@pytest.mark.asyncio
async def test_delete_spam_and_do_not_reply(group_service: GroupService) -> None:
    """Спам должен удаляться без ответа."""
    result = await group_service.process_message(
        IncomingMessage.build(
            chat_id=1,
            user_id=10,
            message_id=1,
            text="free USDT",
        )
    )

    assert result.action == GroupMessageAction.DELETE_SPAM
    assert result.reply_text is None


@pytest.mark.asyncio
async def test_warn_twice_then_mute_on_third_direct_insult(group_service: GroupService) -> None:
    """За 1-е и 2-е оскорбление нужен warning, за 3-е — мут на сутки."""
    first_result = await group_service.process_message(
        IncomingMessage.build(
            chat_id=1,
            user_id=10,
            message_id=1,
            text="Ты дурак",
        )
    )
    second_result = await group_service.process_message(
        IncomingMessage.build(
            chat_id=1,
            user_id=10,
            message_id=2,
            text="Ты идиот",
        )
    )
    third_message = IncomingMessage.build(
        chat_id=1,
        user_id=10,
        message_id=3,
        text="Ты дурак",
    )
    third_result = await group_service.process_message(third_message)

    assert first_result.action == GroupMessageAction.WARN_USER
    assert first_result.reply_text is not None
    assert "уважительно" in first_result.reply_text.casefold()
    assert "предупреждение 1/2" in first_result.reply_text.casefold()

    assert second_result.action == GroupMessageAction.WARN_USER
    assert second_result.reply_text is not None
    assert "предупреждение 2/2" in second_result.reply_text.casefold()

    assert third_result.action == GroupMessageAction.MUTE_USER
    assert third_result.reply_text is not None
    assert "временно ограничен" in third_result.reply_text.casefold()
    assert third_result.mute_until is not None
    assert int((third_result.mute_until - third_message.created_at).total_seconds()) == 86400


@pytest.mark.asyncio
async def test_do_not_warn_on_abuse_word_without_direct_address(
    group_service: GroupService,
) -> None:
    """Мат без обращения к другому участнику не должен давать ложный warning."""
    result = await group_service.process_message(
        IncomingMessage.build(
            chat_id=1,
            user_id=10,
            message_id=1,
            text="ну и дурак этот баг",
            has_question=False,
        )
    )

    assert result.action == GroupMessageAction.IGNORE
    assert result.reply_text is None
