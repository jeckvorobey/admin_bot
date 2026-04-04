"""Repository партнёров из Markdown knowledge base."""

import logging

from app.ai.knowledge import KnowledgeMarkdownStore
from app.models.partner import Partner
from app.utils.exchange import is_exchange_knowledge_item, looks_like_exchange_request
from app.utils.logging import compact_log_text

logger = logging.getLogger(__name__)


class PartnerRepository:
    """Поиск партнёров по Markdown-документам."""

    def __init__(self, knowledge_store: KnowledgeMarkdownStore | None = None) -> None:
        self._knowledge_store = knowledge_store or KnowledgeMarkdownStore()

    def find_by_text(self, text: str) -> Partner | None:
        """Ищет партнёра по trigger words и приоритету."""
        normalized_text = text.casefold()
        items = self._knowledge_store.load_partners()
        for item in items:
            triggers = [
                trigger.strip().casefold()
                for trigger in item.trigger_words.split(",")
                if trigger.strip()
            ]
            if any(trigger in normalized_text for trigger in triggers):
                logger.info(
                    "PartnerRepository.find_by_text matched: partner_id=%s name='%s' "
                    "triggers='%s' text='%s'",
                    item.id,
                    compact_log_text(item.name, 200),
                    compact_log_text(item.trigger_words, 300),
                    compact_log_text(text, 400),
                )
                return item

        if looks_like_exchange_request(text):
            for item in items:
                if is_exchange_knowledge_item(item.trigger_words, category=item.category):
                    logger.info(
                        "PartnerRepository.find_by_text semantic exchange match: "
                        "partner_id=%s name='%s' triggers='%s' text='%s'",
                        item.id,
                        compact_log_text(item.name, 200),
                        compact_log_text(item.trigger_words, 300),
                        compact_log_text(text, 400),
                    )
                    return item
        logger.info(
            "PartnerRepository.find_by_text no match: text='%s'",
            compact_log_text(text, 400),
        )
        return None
