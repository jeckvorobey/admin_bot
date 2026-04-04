"""Тесты proxy-конфигурации внешних HTTP клиентов."""

from __future__ import annotations

import pytest
from google.genai import types

from app.ai.clients.gemini import GeminiClient
from app.core.config import Settings
from app.telegram import bot as telegram_bot


class FakeDispatcher:
    """Stub Dispatcher."""

    def __init__(self) -> None:
        self.message = self

    def middleware(self, _middleware: object) -> None:
        return None

    def include_router(self, _router: object) -> None:
        return None


class FakeTelegramSession:
    """Stub AiohttpSession с сохранением proxy URL."""

    def __init__(self, proxy: str | None = None) -> None:
        self.proxy = proxy


class FakeTelegramBot:
    """Stub Bot с сохранением session."""

    def __init__(self, token: str, session: FakeTelegramSession | None = None) -> None:
        self.token = token
        self.session = session


@pytest.mark.asyncio
async def test_init_bot_uses_proxy_session(monkeypatch) -> None:
    """Telegram Bot должен создаваться с proxy-aware session."""
    monkeypatch.setattr(telegram_bot.settings, "bot_token", "123:token")
    monkeypatch.setattr(telegram_bot.settings, "proxy_http", "127.0.0.1:3128:user:pass")
    monkeypatch.setattr(telegram_bot.settings, "proxy_url", None)
    monkeypatch.setattr(telegram_bot, "bot", None)
    monkeypatch.setattr(telegram_bot, "dp", None)
    monkeypatch.setattr(telegram_bot, "Bot", FakeTelegramBot)
    monkeypatch.setattr(telegram_bot, "Dispatcher", FakeDispatcher)
    monkeypatch.setattr(telegram_bot, "AiohttpSession", FakeTelegramSession)

    bot, _ = await telegram_bot.init_bot()

    assert isinstance(bot, FakeTelegramBot)
    assert isinstance(bot.session, FakeTelegramSession)
    assert bot.session.proxy == "http://user:pass@127.0.0.1:3128"


def test_gemini_client_uses_proxy_http_options(monkeypatch) -> None:
    """Gemini SDK должен получать proxy в http_options."""
    captured_kwargs: dict[str, object] = {}

    class FakeGenAIClient:
        def __init__(self, **kwargs: object) -> None:
            captured_kwargs.update(kwargs)

    monkeypatch.setattr("app.ai.clients.gemini.settings.gemini_api_key", "gemini-key")
    monkeypatch.setattr(
        "app.ai.clients.gemini.settings.proxy_http",
        "127.0.0.1:3128:user:pass",
    )
    monkeypatch.setattr(
        "app.ai.clients.gemini.settings.proxy_url",
        None,
    )
    monkeypatch.setattr("app.ai.clients.gemini.genai.Client", FakeGenAIClient)

    GeminiClient(
        model="gemini-test",
        system_instruction="system",
        temperature=0.0,
        max_output_tokens=32,
    )

    assert captured_kwargs["api_key"] == "gemini-key"
    assert isinstance(captured_kwargs["http_options"], types.HttpOptions)
    assert captured_kwargs["http_options"].client_args == {
        "proxy": "http://user:pass@127.0.0.1:3128"
    }
    assert captured_kwargs["http_options"].async_client_args == {
        "proxy": "http://user:pass@127.0.0.1:3128"
    }


def test_settings_builds_outbound_proxy_url_from_proxy_http() -> None:
    """Settings должен преобразовывать PROXY_HTTP в HTTP proxy URL."""
    proxy_settings = Settings(
        proxy_http="135.106.25.252:63488:jhtD1E2e:jUWKgx2U",
        proxy_url=None,
    )

    assert (
        proxy_settings.outbound_proxy_url
        == "http://jhtD1E2e:jUWKgx2U@135.106.25.252:63488"
    )
