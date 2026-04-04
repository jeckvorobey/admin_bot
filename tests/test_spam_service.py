"""Тесты правил антиспама."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.databases.sqlite import init_db
from app.models.incoming_message import IncomingMessage
from app.repositories.chat_log import ChatLogRepository
from app.repositories.chat_member import ChatMemberRepository
from app.repositories.spam_log import SpamLogRepository
from app.services.spam import SpamService


@pytest.fixture()
def spam_service(tmp_path, monkeypatch) -> SpamService:
    """Создаёт SpamService на временной SQLite базе."""
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "knowledge.db"))
    init_db()
    return SpamService(
        chat_log_repository=ChatLogRepository(),
        chat_member_repository=ChatMemberRepository(),
        spam_log_repository=SpamLogRepository(),
        stop_words=["airdrop", "nft", "free usdt", "x100"],
        blacklisted_domains=("bad-domain.com",),
        forward_whitelist_chat_ids=frozenset({777}),
    )


@pytest.mark.asyncio
async def test_new_member_link_is_spam(spam_service: SpamService) -> None:
    """Ссылка от нового участника должна удаляться."""
    message = IncomingMessage.build(
        chat_id=1,
        user_id=10,
        message_id=1,
        text="Залетай https://promo.example",
        has_links=True,
    )

    assert await spam_service.detect_spam(message) == "Ссылка от нового участника"


@pytest.mark.asyncio
async def test_many_mentions_is_spam(spam_service: SpamService) -> None:
    """5+ упоминаний должно считаться спамом."""
    message = IncomingMessage.build(
        chat_id=1,
        user_id=10,
        message_id=1,
        text="@a @b @c @d @e",
        mention_count=5,
    )

    assert await spam_service.detect_spam(message) == "Слишком много упоминаний"


@pytest.mark.asyncio
async def test_blacklisted_domain_is_spam(spam_service: SpamService) -> None:
    """Домен из чёрного списка должен удаляться."""
    ChatMemberRepository().touch_member(1, 10, datetime.now(UTC) - timedelta(days=2))
    message = IncomingMessage.build(
        chat_id=1,
        user_id=10,
        message_id=1,
        text="Смотри https://bad-domain.com/page",
        has_links=True,
    )

    assert await spam_service.detect_spam(message) == "Домен из чёрного списка"


@pytest.mark.asyncio
async def test_duplicate_text_from_another_user_is_spam(spam_service: SpamService) -> None:
    """Одинаковый текст от другого юзера за 10 минут должен удаляться."""
    now = datetime.now(UTC)
    ChatMemberRepository().touch_member(1, 10, now - timedelta(days=2))
    ChatMemberRepository().touch_member(1, 20, now - timedelta(days=2))
    ChatLogRepository().add_entry(
        chat_id=1,
        user_id=10,
        question="Одинаковый текст",
        answer="",
        created_at=now - timedelta(minutes=1),
    )
    message = IncomingMessage(
        chat_id=1,
        user_id=20,
        message_id=1,
        text="Одинаковый текст",
        created_at=now,
    )

    assert (
        await spam_service.detect_spam(message)
        == "Одинаковый текст от разных пользователей за 10 минут"
    )


@pytest.mark.asyncio
async def test_clean_message_without_prefilter_hit_is_not_spam(tmp_path, monkeypatch) -> None:
    """Если pre-filter не сработал, решение отдаётся triage-агенту, а не SpamService."""
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "knowledge.db"))
    init_db()
    service = SpamService(
        chat_log_repository=ChatLogRepository(),
        chat_member_repository=ChatMemberRepository(),
        spam_log_repository=SpamLogRepository(),
        stop_words=[],
    )
    message = IncomingMessage.build(
        chat_id=1,
        user_id=10,
        message_id=1,
        text="Где рядом нормальный кофе?",
        has_question=True,
    )

    assert await service.detect_spam(message) is None
