"""Инициализация и управление aiogram bot."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiohttp import ClientError

from app.core.config import settings
from app.telegram.handlers import group
from app.telegram.middlewares.logging import LoggingMiddleware

logger = logging.getLogger(__name__)
DEFAULT_POLLING_RETRY_DELAY = 1.0
MAX_POLLING_RETRY_DELAY = 30.0

bot: Bot | None = None
dp: Dispatcher | None = None
polling_task: asyncio.Task[None] | None = None


async def init_bot() -> tuple[Bot, Dispatcher]:
    """Создаёт singleton Bot и Dispatcher."""
    global bot, dp

    if bot is not None and dp is not None:
        return bot, dp

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    logger.info(
        "Initializing aiogram Bot: proxy_enabled=%s telegram_mode=%s",
        bool(settings.outbound_proxy_url),
        settings.telegram_mode,
    )
    bot = Bot(
        token=settings.bot_token,
        session=AiohttpSession(proxy=settings.outbound_proxy_url),
    )
    dp = Dispatcher()
    dp.message.middleware(LoggingMiddleware())
    dp.include_router(group.router)
    return bot, dp


async def start_webhook() -> None:
    """Регистрирует Telegram webhook."""
    if bot is None:
        raise RuntimeError("Telegram bot is not initialized")
    if not settings.telegram_webhook_url:
        raise RuntimeError("WEBHOOK_URL is not configured")

    await bot.set_webhook(
        url=settings.telegram_webhook_url,
        secret_token=settings.webhook_secret,
    )
    logger.info("Telegram webhook registered: url=%s", settings.telegram_webhook_url)


async def start_polling() -> None:
    """Запускает Telegram polling в фоне."""
    global polling_task

    if bot is None or dp is None:
        raise RuntimeError("Telegram bot is not initialized")
    if polling_task is not None and not polling_task.done():
        return

    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except (TelegramNetworkError, ClientError, OSError) as exc:
        logger.warning(
            "Telegram delete_webhook failed before polling start, retrying in background: %s",
            exc,
        )

    polling_task = asyncio.create_task(
        _run_polling_with_retry(),
        name="telegram-polling",
    )
    polling_task.add_done_callback(_log_polling_task_result)
    logger.info("Telegram polling background task created")


async def _run_polling_with_retry() -> None:
    """Держит polling активным и переподключается после сетевых ошибок."""
    if bot is None or dp is None:
        raise RuntimeError("Telegram bot is not initialized")

    delay = DEFAULT_POLLING_RETRY_DELAY
    while True:
        try:
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
                handle_signals=False,
                close_bot_session=False,
            )
            logger.info("Telegram polling stopped normally")
            return
        except asyncio.CancelledError:
            raise
        except (TelegramNetworkError, ClientError, OSError) as exc:
            logger.warning("Telegram polling connection failed: %s", exc)
            await bot.session.close()
            logger.info("Telegram polling retry scheduled in %.1f seconds", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_POLLING_RETRY_DELAY)


def _log_polling_task_result(task: asyncio.Task[None]) -> None:
    """Логирует исключение polling task, если она завершилась аварийно."""
    if task.cancelled():
        logger.info("Telegram polling task cancelled")
        return

    try:
        exception = task.exception()
    except asyncio.CancelledError:
        return

    if exception is not None:
        logger.error("Telegram polling task failed", exc_info=exception)
    else:
        logger.info("Telegram polling task finished")


async def stop_bot() -> None:
    """Останавливает бота и закрывает HTTP session."""
    global bot, dp, polling_task

    current_polling_task = polling_task
    if current_polling_task is not None:
        logger.info("Stopping Telegram polling task")
        if dp is not None and not current_polling_task.done():
            try:
                await dp.stop_polling()
            except RuntimeError:
                logger.warning("Telegram polling was not running during shutdown")

        if not current_polling_task.done():
            current_polling_task.cancel()

        try:
            await asyncio.wait_for(current_polling_task, timeout=3.0)
        except (TimeoutError, asyncio.CancelledError):
            pass
        except Exception:
            logger.warning("Telegram polling task had already failed before shutdown")

    if bot is not None:
        try:
            if settings.telegram_mode == "webhook":
                await bot.delete_webhook(drop_pending_updates=False)
                logger.info("Telegram webhook deleted during shutdown")
        except (TelegramNetworkError, ClientError, OSError) as exc:
            logger.warning("Telegram delete_webhook failed during shutdown: %s", exc)
        finally:
            await bot.session.close()
            logger.info("Telegram bot session closed")

    polling_task = None
    bot = None
    dp = None
