"""Security helper для Telegram webhook."""

from __future__ import annotations

import hmac

from fastapi import HTTPException

from app.core.config import settings


def validate_webhook_secret(provided_secret: str | None) -> None:
    """Проверяет Telegram webhook secret, если он задан."""
    if settings.webhook_secret and not hmac.compare_digest(
        provided_secret or "",
        settings.webhook_secret,
    ):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")
