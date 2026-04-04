"""Схемы webhook-ответов Telegram."""

from pydantic import BaseModel


class TelegramWebhookResponse(BaseModel):
    """Ответ webhook endpoint."""

    ok: bool = True
