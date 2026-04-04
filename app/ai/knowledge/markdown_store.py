"""Загрузка FAQ и партнёров из Markdown-файлов."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.models.faq import FAQ
from app.models.partner import Partner
from app.utils.logging import compact_log_text

logger = logging.getLogger(__name__)


class KnowledgeMarkdownStore:
    """Читает frontmatter-документы из локального каталога knowledge base."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self._base_dir = Path(base_dir or settings.knowledge_base_dir).expanduser().resolve()
        logger.info("KnowledgeMarkdownStore initialized: base_dir=%s", self._base_dir)

    def load_faq(self) -> list[FAQ]:
        """Возвращает FAQ записи из `faq/*.md` по приоритету."""
        items: list[FAQ] = []
        faq_paths = sorted((self._base_dir / "faq").glob("*.md"))
        logger.info(
            "Loading FAQ knowledge: base_dir=%s files=%s",
            self._base_dir / "faq",
            len(faq_paths),
        )
        for index, path in enumerate(faq_paths, start=1):
            metadata, body = _parse_markdown_document(path)
            items.append(
                FAQ(
                    id=_parse_int(metadata.get("id"), index),
                    trigger_words=_join_trigger_words(metadata.get("trigger_words")),
                    answer=_parse_text(metadata.get("answer")) or body,
                    link=_parse_text(metadata.get("link")),
                    priority=_parse_int(metadata.get("priority"), 100),
                )
            )
            logger.info(
                "FAQ markdown loaded: path=%s id=%s triggers='%s' answer='%s' link='%s'",
                path,
                items[-1].id,
                compact_log_text(items[-1].trigger_words, 300),
                compact_log_text(items[-1].answer, 400),
                compact_log_text(items[-1].link, 300),
            )
        sorted_items = sorted(items, key=lambda item: (item.priority, item.id))
        logger.info("FAQ knowledge loaded: total=%s", len(sorted_items))
        return sorted_items

    def load_partners(self) -> list[Partner]:
        """Возвращает партнёрские записи из `partners/*.md` по приоритету."""
        items: list[Partner] = []
        partner_paths = sorted((self._base_dir / "partners").glob("*.md"))
        logger.info(
            "Loading partner knowledge: base_dir=%s files=%s",
            self._base_dir / "partners",
            len(partner_paths),
        )
        for index, path in enumerate(partner_paths, start=1):
            metadata, body = _parse_markdown_document(path)
            items.append(
                Partner(
                    id=_parse_int(metadata.get("id"), index),
                    name=_parse_text(metadata.get("name")),
                    category=_parse_text(metadata.get("category")),
                    trigger_words=_join_trigger_words(metadata.get("trigger_words")),
                    link=_parse_text(metadata.get("link")),
                    description=_parse_text(metadata.get("description")) or body,
                    priority=_parse_int(metadata.get("priority"), 100),
                )
            )
            logger.info(
                "Partner markdown loaded: path=%s id=%s name='%s' category='%s' "
                "triggers='%s' link='%s'",
                path,
                items[-1].id,
                compact_log_text(items[-1].name, 200),
                compact_log_text(items[-1].category, 200),
                compact_log_text(items[-1].trigger_words, 300),
                compact_log_text(items[-1].link, 300),
            )
        sorted_items = sorted(items, key=lambda item: (item.priority, item.id))
        logger.info("Partner knowledge loaded: total=%s", len(sorted_items))
        return sorted_items


def _parse_markdown_document(path: Path) -> tuple[dict[str, Any], str]:
    """Разбирает Markdown файл с YAML-подобным frontmatter."""
    content = path.read_text(encoding="utf-8").strip()
    if not content.startswith("---\n"):
        return {}, content

    lines = content.splitlines()
    metadata_lines: list[str] = []
    body_start_index = 0
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_start_index = index + 1
            break
        metadata_lines.append(line)
    else:
        return {}, content

    return _parse_frontmatter(metadata_lines), "\n".join(lines[body_start_index:]).strip()


def _parse_frontmatter(lines: list[str]) -> dict[str, Any]:
    """Поддерживает scalar-поля и списки в формате `- value`."""
    metadata: dict[str, Any] = {}
    current_key: str | None = None

    for line in lines:
        if not line.strip():
            continue

        if line.startswith("  - ") and current_key is not None:
            current_value = metadata.setdefault(current_key, [])
            if isinstance(current_value, list):
                current_value.append(line[4:].strip())
            continue

        key, separator, value = line.partition(":")
        if separator != ":":
            continue

        current_key = key.strip()
        scalar = value.strip()
        metadata[current_key] = _parse_scalar(scalar) if scalar else []

    return metadata


def _parse_scalar(value: str) -> str | int:
    """Преобразует целые числа, остальное оставляет строкой."""
    if value.isdigit():
        return int(value)
    return value.strip().strip('"').strip("'")


def _parse_int(value: Any, fallback: int) -> int:
    """Возвращает int из frontmatter со значением по умолчанию."""
    return value if isinstance(value, int) else fallback


def _parse_text(value: Any) -> str:
    """Возвращает строковое frontmatter поле."""
    return value.strip() if isinstance(value, str) else ""


def _join_trigger_words(value: Any) -> str:
    """Нормализует `trigger_words` к формату текущей доменной модели."""
    if isinstance(value, list):
        return ",".join(item.strip() for item in value if isinstance(item, str) and item.strip())
    if isinstance(value, str):
        return value.strip()
    return ""
