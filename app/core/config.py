"""Конфигурация приложения."""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Глобальные настройки backend и Telegram-бота."""

    app_name: str = "admin_bot"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_env: str = "dev"
    log_level: str = "INFO"

    backend_cors_origins: list[str] | str = []

    bot_token: str | None = None
    bot_username: str | None = None
    telegram_mode: Literal["polling", "webhook"] = "polling"
    webhook_url: str | None = None
    webhook_path: str = "/telegram/webhook"
    webhook_secret: str | None = None

    gemini_api_key: str | None = None
    proxy_http: str | None = None
    proxy_url: str | None = None

    database_path: str = "./data/knowledge.db"
    knowledge_base_dir: str = "./app/knowledge"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def telegram_webhook_url(self) -> str | None:
        """Полный публичный webhook URL Telegram."""
        if self.webhook_url:
            return f"{self.webhook_url.rstrip('/')}{self.webhook_path}"
        return None

    @property
    def outbound_proxy_url(self) -> str | None:
        """Возвращает proxy URL для внешних HTTP клиентов."""
        if self.proxy_url:
            return self.proxy_url
        if not self.proxy_http:
            return None
        if "://" in self.proxy_http:
            return self.proxy_http

        parts = self.proxy_http.split(":", maxsplit=3)
        if len(parts) == 2:
            host, port = parts
            return f"http://{host}:{port}"
        if len(parts) == 4:
            host, port, username, password = parts
            return (
                f"http://{quote(username, safe='')}:{quote(password, safe='')}"
                f"@{host}:{port}"
            )
        raise ValueError(
            "PROXY_HTTP должен быть в формате host:port или host:port:username:password"
        )


settings = Settings()
