"""Агент генерации ответа с локальным knowledge lookup и web-search fallback."""

from __future__ import annotations

import logging

from app.ai.clients import GeminiClient
from app.ai.prompts import load_prompt
from app.core.ai_config import ANSWER_MODEL
from app.models.chat import ChatLogEntry
from app.models.faq import FAQ
from app.models.partner import Partner
from app.utils.exchange import (
    detect_exchange_country,
    is_exchange_knowledge_item,
    looks_like_exchange_request,
)
from app.utils.logging import compact_log_text

logger = logging.getLogger(__name__)


class AnswerAgent:
    """Генерирует ответ из `.md` knowledge base, истории чата и Google Search."""

    def __init__(self, web_search_client: GeminiClient | None = None) -> None:
        self._web_search_client = web_search_client or GeminiClient(
            model=ANSWER_MODEL,
            system_instruction=load_prompt("answer.md"),
            temperature=0.7,
            max_output_tokens=500,
            use_google_search=True,
        )

    async def build_answer(
        self,
        question: str,
        history: list[ChatLogEntry],
        *,
        faq: FAQ | None = None,
        partner: Partner | None = None,
    ) -> str:
        """Возвращает локальный FAQ ответ или web-search ответ с partner рекомендацией."""
        if self._should_build_exchange_answer(question, faq=faq, partner=partner):
            exchange_answer = await self._build_exchange_answer(
                question,
                history,
                faq=faq,
                partner=partner,
            )
            if exchange_answer:
                logger.info(
                    "AnswerAgent exchange answer built: question='%s' answer='%s'",
                    compact_log_text(question, 500),
                    compact_log_text(exchange_answer, 700),
                )
                return exchange_answer

        base_answer = self._build_local_answer(faq)
        if not base_answer:
            prompt = self._build_prompt(question, history, partner=partner)
            logger.info(
                "AnswerAgent requesting Gemini fallback: history_size=%s "
                "has_partner=%s question='%s' prompt='%s'",
                len(history),
                partner is not None,
                compact_log_text(question, 500),
                compact_log_text(prompt),
            )
            base_answer = (await self._web_search_client.generate_text(prompt)).strip()
        else:
            logger.info(
                "AnswerAgent using local FAQ: faq_id=%s question='%s' answer='%s'",
                faq.id if faq else None,
                compact_log_text(question, 500),
                compact_log_text(base_answer, 700),
            )

        if not base_answer:
            base_answer = self._fallback_answer(question)
            logger.info(
                "AnswerAgent using deterministic fallback: question='%s' answer='%s'",
                compact_log_text(question, 500),
                compact_log_text(base_answer, 700),
            )

        final_answer = self._append_partner(base_answer, partner)
        logger.info(
            "AnswerAgent final answer built: has_partner=%s answer='%s'",
            partner is not None,
            compact_log_text(final_answer, 700),
        )
        return final_answer

    async def _build_exchange_answer(
        self,
        question: str,
        history: list[ChatLogEntry],
        *,
        faq: FAQ | None,
        partner: Partner | None,
    ) -> str:
        """Генерирует человекоподобный exchange-ответ через Gemini или локальный fallback."""
        prompt = self._build_exchange_prompt(
            question,
            history,
            faq=faq,
            partner=partner,
        )
        logger.info(
            "AnswerAgent requesting Gemini exchange rewrite: history_size=%s "
            "question='%s' prompt='%s'",
            len(history),
            compact_log_text(question, 500),
            compact_log_text(prompt),
        )

        model_answer = (await self._web_search_client.generate_text(prompt)).strip()
        if model_answer:
            return self._append_review_link(
                self._append_partner(model_answer, partner),
                faq,
            )

        logger.info(
            "AnswerAgent Gemini exchange rewrite empty, using local fallback: question='%s'",
            compact_log_text(question, 500),
        )
        return self._build_local_exchange_answer(question, faq=faq, partner=partner)

    @staticmethod
    def _build_local_answer(faq: FAQ | None) -> str:
        """Собирает прямой ответ из FAQ, если локальное знание найдено."""
        if faq is None:
            return ""
        return f"{faq.answer}\n{faq.link}".strip()

    @staticmethod
    def _should_build_exchange_answer(
        question: str,
        *,
        faq: FAQ | None,
        partner: Partner | None,
    ) -> bool:
        """Проверяет, что для ответа нужен exchange-режим."""
        return (
            looks_like_exchange_request(question)
            or (faq is not None and is_exchange_knowledge_item(faq.trigger_words))
            or (
                partner is not None
                and is_exchange_knowledge_item(partner.trigger_words, category=partner.category)
            )
        )

    @staticmethod
    def _build_exchange_prompt(
        question: str,
        history: list[ChatLogEntry],
        *,
        faq: FAQ | None,
        partner: Partner | None,
    ) -> str:
        """Собирает prompt для динамического exchange-ответа."""
        history_block = "\n".join(
            f"Пользователь: {entry.question}\nБот: {entry.answer}".strip()
            for entry in history[-10:]
            if entry.question.strip() or entry.answer.strip()
        ).strip()
        country = detect_exchange_country(question)
        faq_block = ""
        if faq is not None:
            faq_block = "\n".join(
                [
                    "Локальная FAQ-карточка AntEx:",
                    faq.answer.strip(),
                    f"Ссылка на отзывы: {faq.link}".strip(),
                ]
            ).strip()
        partner_block = ""
        if partner is not None:
            partner_block = "\n".join(
                [
                    "Локальная partner-карточка AntEx:",
                    f"Название: {partner.name}",
                    f"Описание: {partner.description}",
                    f"Контакт: {partner.link}",
                ]
            ).strip()

        parts = [
            "Собери очень живой, дружелюбный ответ как участник Telegram-чата.",
            "Пиши 2-4 естественных предложения, без канцелярита и без markdown-таблиц.",
            "Если вопрос про Вьетнам, Таиланд или Грузию, явно назови страну.",
            "Дай примерный ориентир по местному курсу через Google Search grounding и "
            "мягко уточни, что точный курс лучше проверить в момент обмена.",
            "Обязательно скажи, что AntEx помогает не только с обменом валют/крипты, "
            "но и с оплатой Booking и аренды квартиры.",
            "Контакт AntEx и ссылку на отзывы бери только из локальных карточек ниже, "
            "не подменяй их другими ссылками.",
        ]
        if country is not None:
            parts.append(f"Страна из вопроса: {country.name}.")
        if history_block:
            parts.extend(["", "История чата:", history_block])
        if faq_block:
            parts.extend(["", faq_block])
        if partner_block:
            parts.extend(["", partner_block])
        parts.extend(["", f"Новый вопрос пользователя: {question.strip()}"])
        return "\n".join(parts).strip()

    @staticmethod
    def _build_local_exchange_answer(
        question: str,
        *,
        faq: FAQ | None,
        partner: Partner | None,
    ) -> str:
        """Собирает локальный человекоподобный exchange-ответ без Gemini."""
        country = detect_exchange_country(question)
        if country is not None:
            intro = (
                f"{country.where_phrase} можно спокойно обратиться в AntEx Support — "
                f"они помогают поменять рубли и крипту на {country.currency_hint}."
            )
            rate = (
                f"По курсу сейчас можно держать в голове такой примерный ориентир: "
                f"{country.rate_hint}, а точную цифру лучше уточнить прямо перед обменом."
            )
        else:
            intro = (
                "Если нужно поменять деньги, можно спокойно написать в AntEx Support — "
                "они помогают с обменом рублей и крипты во Вьетнаме, Таиланде и Грузии."
            )
            rate = (
                "По курсу обычно дают рыночный ориентир уже под вашу страну и сумму, "
                "а точную цифру лучше уточнить перед обменом."
            )

        support_link = partner.link if partner is not None else "https://t.me/AntEx_support"
        reviews_link = faq.link if faq is not None else "https://t.me/+ui-tQ4T-jrNlNmQy"
        return "\n".join(
            [
                intro,
                rate,
                "Плюс у них же можно попросить помощь с оплатой Booking и аренды квартиры, "
                "если нужна локальная оплата без лишней нервотрёпки.",
                f"Написать можно сюда: {support_link}",
                f"Отзывы ребят: {reviews_link}",
            ]
        ).strip()

    @staticmethod
    def _build_prompt(
        question: str,
        history: list[ChatLogEntry],
        *,
        partner: Partner | None,
    ) -> str:
        """Собирает prompt с историей и подсказкой по партнёру, если trigger найден."""
        history_block = "\n".join(
            f"Пользователь: {entry.question}\nБот: {entry.answer}".strip()
            for entry in history[-10:]
            if entry.question.strip() or entry.answer.strip()
        ).strip()
        partner_block = ""
        if partner is not None:
            partner_block = (
                "Локальная партнёрская рекомендация:\n"
                f"{partner.description} {partner.name}: {partner.link}"
            )

        parts = []
        if history_block:
            parts.extend(["История чата:", history_block, ""])
        if partner_block:
            parts.extend([partner_block, ""])
        parts.extend(
            [
                "Локального FAQ ответа нет.",
                "Найди актуальный ответ через интернет-поиск, "
                "если вопрос требует свежей информации.",
                f"Новый вопрос пользователя: {question.strip()}",
            ]
        )
        return "\n".join(parts).strip()

    @staticmethod
    def _append_partner(answer: str, partner: Partner | None) -> str:
        """Добавляет партнёрскую рекомендацию, если её ещё нет в ответе."""
        if partner is None or partner.link in answer:
            return answer
        return f"{answer}\n\n{partner.description} {partner.name}: {partner.link}"

    @staticmethod
    def _append_review_link(answer: str, faq: FAQ | None) -> str:
        """Добавляет ссылку на отзывы из FAQ, если модель её пропустила."""
        if faq is None or not faq.link or faq.link in answer:
            return answer
        return f"{answer}\nОтзывы: {faq.link}"

    @staticmethod
    def _fallback_answer(question: str) -> str:
        """Детерминированный fallback, если Gemini недоступен."""
        return f"По вопросу «{question.strip()}» — могу подсказать, но лучше чуть уточнить 🙂"
