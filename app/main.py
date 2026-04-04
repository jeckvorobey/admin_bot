"""FastAPI приложение admin_bot."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import telegram
from app.core.config import settings
from app.core.logging import setup_logging
from app.databases.sqlite import init_db
from app.telegram import bot as telegram_bot

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Управляет жизненным циклом Telegram-бота."""
    try:
        logger.info(
            "Startup admin_bot: env=%s telegram_mode=%s bot_enabled=%s",
            settings.app_env,
            settings.telegram_mode,
            bool(settings.bot_token),
        )
        init_db()
        logger.info("SQLite schema initialized: database_path=%s", settings.database_path)

        if settings.bot_token:
            await telegram_bot.init_bot()
            logger.info("Telegram bot initialized")
            if settings.telegram_mode == "polling":
                logger.info("Starting Telegram polling")
                await telegram_bot.start_polling()
            else:
                logger.info("Starting Telegram webhook")
                await telegram_bot.start_webhook()
        yield
    finally:
        logger.info("Shutdown admin_bot: stopping Telegram bot")
        await telegram_bot.stop_bot()
        logger.info("Shutdown admin_bot completed")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(telegram.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Healthcheck для локального запуска и Coolify."""
    return {"status": "ok", "app": settings.app_name}
