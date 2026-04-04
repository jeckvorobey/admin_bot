"""Тесты startup bootstrap FastAPI приложения."""

from __future__ import annotations

from fastapi import FastAPI

from app import main
from app.core.config import settings
from app.databases.sqlite import get_connection


async def test_lifespan_initializes_sqlite_schema(tmp_path, monkeypatch) -> None:
    """lifespan должен создавать таблицы SQLite до обработки сообщений."""
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "knowledge.db"))
    monkeypatch.setattr(settings, "bot_token", None)

    async with main.lifespan(FastAPI()):
        with get_connection() as connection:
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }

    assert {"spam_log", "chat_log", "chat_members"}.issubset(tables)
