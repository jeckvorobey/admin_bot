"""Настройка прикладного логирования."""

from __future__ import annotations

import logging


def setup_logging(log_level: str) -> None:
    """Настраивает единый формат логов приложения."""
    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
