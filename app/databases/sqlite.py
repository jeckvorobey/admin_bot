"""Инициализация SQLite логов и Q/A истории."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    """Открывает SQLite connection."""
    db_path = Path(settings.database_path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.debug("Opening SQLite connection: db_path=%s", db_path)
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    """Создаёт базовые таблицы проекта."""
    logger.info("Initializing SQLite schema: database_path=%s", settings.database_path)
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS spam_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chat_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chat_members (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                abuse_warning_count INTEGER NOT NULL DEFAULT 0,
                muted_until_at TEXT,
                PRIMARY KEY (chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS pending_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                user_language TEXT NOT NULL DEFAULT 'ru',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                answered_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_pending_questions_chat_status
            ON pending_questions (chat_id, status, created_at);
            """
        )
        _ensure_chat_member_columns(connection)
        _ensure_pending_question_columns(connection)
    logger.info(
        "SQLite schema ready: tables=%s",
        ["spam_log", "chat_log", "chat_members", "pending_questions"],
    )


def _ensure_pending_question_columns(connection: sqlite3.Connection) -> None:
    """Добавляет audit-колонки в pending_questions (миграции для существующих БД).

    answered_by_message_id — message_id reply-сообщения, закрывшего вопрос участником.
    bot_replied_at — timestamp ответа бота; NULL означает, что бот ещё не ответил.
    Эти два поля позволяют различать, кто именно закрыл вопрос.
    """
    rows = connection.execute("PRAGMA table_info(pending_questions)").fetchall()
    existing_columns = {row["name"] for row in rows}
    if "answered_by_message_id" not in existing_columns:
        connection.execute(
            "ALTER TABLE pending_questions ADD COLUMN answered_by_message_id INTEGER"
        )
        logger.info("SQLite migration applied: pending_questions.answered_by_message_id")
    if "bot_replied_at" not in existing_columns:
        connection.execute(
            "ALTER TABLE pending_questions ADD COLUMN bot_replied_at TEXT"
        )
        logger.info("SQLite migration applied: pending_questions.bot_replied_at")


def _ensure_chat_member_columns(connection: sqlite3.Connection) -> None:
    """Добавляет moderation-колонки в старую `chat_members` схему."""
    rows = connection.execute("PRAGMA table_info(chat_members)").fetchall()
    existing_columns = {row["name"] for row in rows}
    if "abuse_warning_count" not in existing_columns:
        connection.execute(
            """
            ALTER TABLE chat_members
            ADD COLUMN abuse_warning_count INTEGER NOT NULL DEFAULT 0
            """
        )
        logger.info("SQLite migration applied: chat_members.abuse_warning_count")
    if "muted_until_at" not in existing_columns:
        connection.execute(
            """
            ALTER TABLE chat_members
            ADD COLUMN muted_until_at TEXT
            """
        )
        logger.info("SQLite migration applied: chat_members.muted_until_at")
