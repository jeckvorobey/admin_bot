"""Базовые dataclass-модели проекта."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BaseEntity:
    """Базовая сущность с идентификатором."""

    id: int
