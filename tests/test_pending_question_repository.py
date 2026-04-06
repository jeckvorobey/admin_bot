"""Тесты репозитория отложенных вопросов."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.databases.sqlite import init_db
from app.repositories.pending_question import PendingQuestionRepository


@pytest.fixture()
def repo(tmp_path, monkeypatch) -> PendingQuestionRepository:
    """Создаёт репозиторий на временной SQLite базе."""
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "knowledge.db"))
    init_db()
    return PendingQuestionRepository()


def test_add_and_find_ready_after_cutoff(repo: PendingQuestionRepository) -> None:
    """Вопрос старше cutoff_minutes должен попасть в find_ready."""
    old_time = datetime.now(UTC) - timedelta(minutes=6)
    repo.add(
        chat_id=1,
        message_id=10,
        user_id=100,
        question="Где поменять деньги?",
        user_language="ru",
        created_at=old_time,
    )

    ready = repo.find_ready(chat_id=1, cutoff_minutes=5)

    assert len(ready) == 1
    assert ready[0]["question"] == "Где поменять деньги?"
    assert ready[0]["user_language"] == "ru"
    assert ready[0]["message_id"] == 10


def test_find_ready_ignores_fresh_question(repo: PendingQuestionRepository) -> None:
    """Свежий вопрос (< cutoff) не должен попадать в find_ready."""
    repo.add(
        chat_id=1,
        message_id=11,
        user_id=101,
        question="Свежий вопрос",
        created_at=datetime.now(UTC) - timedelta(minutes=2),
    )

    ready = repo.find_ready(chat_id=1, cutoff_minutes=5)

    assert ready == []


def test_find_ready_ignores_other_chat(repo: PendingQuestionRepository) -> None:
    """find_ready не должен возвращать вопросы из другого чата."""
    repo.add(
        chat_id=999,
        message_id=12,
        user_id=102,
        question="Вопрос из другого чата",
        created_at=datetime.now(UTC) - timedelta(minutes=10),
    )

    ready = repo.find_ready(chat_id=1, cutoff_minutes=5)

    assert ready == []


def test_mark_answered_by_other_user(repo: PendingQuestionRepository) -> None:
    """Другой пользователь может закрыть pending-вопрос."""
    repo.add(
        chat_id=1,
        message_id=13,
        user_id=100,
        question="Вопрос от user_id=100",
        created_at=datetime.now(UTC) - timedelta(minutes=6),
    )

    # user_id=200 отвечает — не тот, кто спросил
    count = repo.mark_answered(chat_id=1, except_user_id=200)

    assert count == 1
    assert repo.find_ready(chat_id=1, cutoff_minutes=5) == []


def test_mark_answered_skips_own_message(repo: PendingQuestionRepository) -> None:
    """Автор вопроса не должен закрывать свой же pending-вопрос."""
    repo.add(
        chat_id=1,
        message_id=14,
        user_id=100,
        question="Вопрос от user_id=100",
        created_at=datetime.now(UTC) - timedelta(minutes=6),
    )

    # тот же user_id=100 пишет снова — не должно закрыть
    count = repo.mark_answered(chat_id=1, except_user_id=100)

    assert count == 0
    assert len(repo.find_ready(chat_id=1, cutoff_minutes=5)) == 1


def test_mark_bot_answered_removes_from_ready(repo: PendingQuestionRepository) -> None:
    """После mark_bot_answered вопрос не должен возвращаться в find_ready."""
    repo.add(
        chat_id=1,
        message_id=15,
        user_id=100,
        question="Бот ответит через 5 мин",
        created_at=datetime.now(UTC) - timedelta(minutes=6),
    )
    ready_before = repo.find_ready(chat_id=1, cutoff_minutes=5)
    assert len(ready_before) == 1

    repo.mark_bot_answered(ready_before[0]["id"])

    assert repo.find_ready(chat_id=1, cutoff_minutes=5) == []


def test_find_ready_returns_oldest_first(repo: PendingQuestionRepository) -> None:
    """find_ready должен возвращать вопросы по хронологии (старший первым)."""
    repo.add(
        chat_id=1,
        message_id=16,
        user_id=100,
        question="Старый вопрос",
        created_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    repo.add(
        chat_id=1,
        message_id=17,
        user_id=101,
        question="Менее старый вопрос",
        created_at=datetime.now(UTC) - timedelta(minutes=7),
    )

    ready = repo.find_ready(chat_id=1, cutoff_minutes=5)

    assert len(ready) == 2
    assert ready[0]["question"] == "Старый вопрос"
    assert ready[1]["question"] == "Менее старый вопрос"
