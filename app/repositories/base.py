"""Базовый repository helper."""

from sqlite3 import Connection

from app.databases.sqlite import get_connection


class BaseRepository:
    """Базовый репозиторий с фабрикой SQLite connection."""

    def _connection(self) -> Connection:
        return get_connection()
