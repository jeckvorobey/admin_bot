"""Тесты извлечения упоминаний пользователей из Telegram сообщений."""

from __future__ import annotations

from types import SimpleNamespace

from app.telegram.handlers.group import _extract_mention_targets


def _entity(entity_type: str, offset: int, length: int, user=None):
    """Вспомогательная фабрика MessageEntity-подобного объекта."""
    return SimpleNamespace(type=entity_type, offset=offset, length=length, user=user)


def test_extract_single_mention_excluding_bot() -> None:
    """@username должен попасть в targets, @bot — нет."""
    text = "@someuser @mybot"
    # "@someuser" offset=0 length=9, "@mybot" offset=10 length=6
    entities = [
        _entity("mention", 0, 9),   # @someuser
        _entity("mention", 10, 6),  # @mybot
    ]

    targets = _extract_mention_targets(text, entities, bot_username="mybot")

    assert targets == ("someuser",)


def test_extract_multiple_non_bot_mentions() -> None:
    """Несколько не-бот упоминаний должны все попасть в targets."""
    text = "@alice @bob привет"
    entities = [
        _entity("mention", 0, 6),   # @alice
        _entity("mention", 7, 4),   # @bob
    ]

    targets = _extract_mention_targets(text, entities, bot_username="adminbot")

    assert set(targets) == {"alice", "bob"}


def test_extract_text_mention_by_entity_user() -> None:
    """text_mention (пользователь без username) должен извлекаться через entity.user."""
    text = "Привет Иван"
    user = SimpleNamespace(username="ivan_user")
    entities = [_entity("text_mention", 7, 4, user=user)]

    targets = _extract_mention_targets(text, entities, bot_username="bot")

    assert targets == ("ivan_user",)


def test_extract_empty_when_no_mentions() -> None:
    """Без упоминаний targets должен быть пустым кортежем."""
    targets = _extract_mention_targets("Просто текст без упоминаний", [], bot_username="bot")

    assert targets == ()


def test_bot_username_case_insensitive() -> None:
    """Сравнение с bot_username должно быть регистронезависимым."""
    text = "@AdminBot привет"
    entities = [_entity("mention", 0, 9)]  # @AdminBot

    targets = _extract_mention_targets(text, entities, bot_username="adminbot")

    assert targets == ()
