"""Роутер Telegram webhook."""

from __future__ import annotations

import logging

from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import settings
from app.core.security import validate_webhook_secret
from app.telegram import bot as telegram_bot

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    """Принимает Telegram updates и передаёт их в aiogram dispatcher."""
    if settings.telegram_mode != "webhook":
        logger.warning("Received Telegram webhook while TELEGRAM_MODE is not webhook")
        return {"ok": True}

    validate_webhook_secret(x_telegram_bot_api_secret_token)

    if telegram_bot.bot is None or telegram_bot.dp is None:
        logger.error("Telegram webhook rejected: bot is not initialized")
        raise HTTPException(status_code=503, detail="Bot is not initialized")

    payload = await request.json()
    logger.info(
        "Telegram webhook update received: update_id=%s keys=%s",
        payload.get("update_id"),
        sorted(payload.keys()),
    )

    update = Update.model_validate(payload, context={"bot": telegram_bot.bot})
    await telegram_bot.dp.feed_update(bot=telegram_bot.bot, update=update)
    logger.info("Telegram webhook update processed: update_id=%s", update.update_id)
    return {"ok": True}
