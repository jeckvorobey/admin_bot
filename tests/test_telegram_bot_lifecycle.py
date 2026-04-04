"""Регрессионные тесты lifecycle Telegram-бота."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app import main
from app.telegram import bot as telegram_bot


class FakeSession:
    """Stub HTTP session aiogram bot."""

    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeBot:
    """Stub Bot с ошибкой сети при delete_webhook."""

    def __init__(self) -> None:
        self.session = FakeSession()
        self.delete_webhook_calls = 0

    async def delete_webhook(self, drop_pending_updates: bool) -> bool:
        self.delete_webhook_calls += 1
        raise OSError("network is unavailable")


class FakeDispatcher:
    """Stub Dispatcher для stop_bot."""

    async def stop_polling(self) -> None:
        return None


@pytest.mark.asyncio
async def test_start_polling_survives_delete_webhook_network_error(monkeypatch) -> None:
    """Сбой delete_webhook не должен срывать запуск FastAPI."""
    fake_bot = FakeBot()
    monkeypatch.setattr(telegram_bot, "bot", fake_bot)
    monkeypatch.setattr(telegram_bot, "dp", FakeDispatcher())
    monkeypatch.setattr(telegram_bot, "polling_task", None)

    async def fake_run_polling_with_retry() -> None:
        return None

    monkeypatch.setattr(
        telegram_bot,
        "_run_polling_with_retry",
        fake_run_polling_with_retry,
    )

    await telegram_bot.start_polling()

    assert fake_bot.delete_webhook_calls == 1
    assert telegram_bot.polling_task is not None

    await telegram_bot.stop_bot()
    assert fake_bot.session.closed is True


@pytest.mark.asyncio
async def test_lifespan_stops_bot_after_startup_failure(monkeypatch) -> None:
    """lifespan должен закрывать Telegram bot даже при ошибке startup."""
    stop_called = False
    monkeypatch.setattr(main.settings, "bot_token", "123:token")
    monkeypatch.setattr(main.settings, "telegram_mode", "polling")

    async def fake_init_bot() -> None:
        return None

    async def fake_start_polling() -> None:
        raise OSError("telegram startup failed")

    async def fake_stop_bot() -> None:
        nonlocal stop_called
        stop_called = True

    monkeypatch.setattr(main.telegram_bot, "init_bot", fake_init_bot)
    monkeypatch.setattr(main.telegram_bot, "start_polling", fake_start_polling)
    monkeypatch.setattr(main.telegram_bot, "stop_bot", fake_stop_bot)

    with pytest.raises(OSError, match="telegram startup failed"):
        async with main.lifespan(FastAPI()):
            pass

    assert stop_called is True
