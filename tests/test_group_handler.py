"""Тесты aiogram handler слоя."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.group_action import GroupMessageAction, GroupMessageResult
from app.telegram.handlers import group as group_handlers


class FakeSpamGroupService:
    """Stub GroupService для проверки ban-flow."""

    async def process_message(self, message):
        return GroupMessageResult(action=GroupMessageAction.DELETE_SPAM)


class FakeMuteGroupService:
    """Stub GroupService для проверки mute-flow."""

    async def process_message(self, message):
        return GroupMessageResult(
            action=GroupMessageAction.MUTE_USER,
            reply_text="Пожалуйста, общайтесь уважительно. Пользователь временно ограничен.",
            mute_until=datetime.now(UTC) + timedelta(hours=24),
        )


class FakeBot:
    """Stub Telegram Bot."""

    def __init__(self) -> None:
        self.banned_user_id: int | None = None
        self.banned_chat_id: int | None = None
        self.restricted_user_id: int | None = None
        self.restricted_chat_id: int | None = None
        self.restricted_permissions = None
        self.restricted_until = None

    async def ban_chat_member(self, chat_id: int, user_id: int) -> None:
        self.banned_chat_id = chat_id
        self.banned_user_id = user_id

    async def restrict_chat_member(
        self,
        chat_id,
        user_id,
        permissions,
        until_date=None,
    ) -> None:
        self.restricted_chat_id = chat_id
        self.restricted_user_id = user_id
        self.restricted_permissions = permissions
        self.restricted_until = until_date


class FakeMessage:
    """Минимальный Message-like объект для handler test."""

    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=100, type="supergroup")
        self.from_user = SimpleNamespace(id=200)
        self.text = "free USDT"
        self.message_id = 10
        self.entities = []
        self.reply_to_message = None
        self.forward_origin = None
        self.forward_from_chat = None
        self.bot = FakeBot()
        self.deleted = False
        self.reply_text = None

    async def delete(self) -> None:
        self.deleted = True

    async def reply(self, text: str) -> None:
        self.reply_text = text


@pytest.mark.asyncio
async def test_group_message_delete_and_ban_spammer(monkeypatch) -> None:
    """Spam-message должен удаляться, а автор — блокироваться."""
    fake_message = FakeMessage()
    monkeypatch.setattr(group_handlers, "group_service", FakeSpamGroupService())

    await group_handlers.group_message(fake_message)

    assert fake_message.deleted is True
    assert fake_message.bot.banned_chat_id == 100
    assert fake_message.bot.banned_user_id == 200


@pytest.mark.asyncio
async def test_group_message_warn_and_mute_user(monkeypatch) -> None:
    """Mute-result должен ограничивать отправку сообщений и отправлять предупреждение."""
    fake_message = FakeMessage()
    fake_message.text = "Ты дурак"
    monkeypatch.setattr(group_handlers, "group_service", FakeMuteGroupService())

    await group_handlers.group_message(fake_message)

    assert fake_message.deleted is False
    assert fake_message.reply_text is not None
    assert "уважительно" in fake_message.reply_text.casefold()
    assert fake_message.bot.restricted_chat_id == 100
    assert fake_message.bot.restricted_user_id == 200
    assert fake_message.bot.restricted_permissions.can_send_messages is False
    assert fake_message.bot.restricted_until is not None
