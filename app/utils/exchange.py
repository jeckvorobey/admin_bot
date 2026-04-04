"""Хелперы распознавания exchange-запросов и странового контекста."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExchangeCountryProfile:
    """Профиль страны для человекоподобного exchange-ответа."""

    name: str
    where_phrase: str
    currency_hint: str
    rate_hint: str
    aliases: tuple[str, ...]


EXCHANGE_COUNTRY_PROFILES: tuple[ExchangeCountryProfile, ...] = (
    ExchangeCountryProfile(
        name="Вьетнам",
        where_phrase="Во Вьетнаме",
        currency_hint="вьетнамские донги",
        rate_hint="ориентир по рынку: 1 USDT ≈ 26 000-26 500 VND",
        aliases=(
            "вьетнам",
            "вьетнаме",
            "дананг",
            "нячанг",
            "хошимин",
            "ханой",
            "фукуок",
            "донг",
            "донги",
            "vnd",
        ),
    ),
    ExchangeCountryProfile(
        name="Таиланд",
        where_phrase="В Таиланде",
        currency_hint="тайские баты",
        rate_hint="ориентир по рынку: 1 USDT ≈ 31-33 THB",
        aliases=(
            "таиланд",
            "таиланде",
            "тайланд",
            "тайланде",
            "пхукет",
            "паттайя",
            "бангкок",
            "самуи",
            "бат",
            "баты",
            "thb",
        ),
    ),
    ExchangeCountryProfile(
        name="Грузия",
        where_phrase="В Грузии",
        currency_hint="грузинские лари",
        rate_hint="ориентир по рынку: 1 USDT ≈ 2.7 GEL",
        aliases=(
            "грузия",
            "грузии",
            "тбилиси",
            "батуми",
            "кутаиси",
            "лари",
            "gel",
        ),
    ),
)

_EXCHANGE_INTENT_MARKERS = (
    "обмен",
    "обменя",
    "поменя",
    "размен",
    "курс",
    "конверт",
    "налич",
    "деньг",
    "рубл",
    "usdt",
    "btc",
    "eth",
    "крипт",
    "букинг",
    "booking",
    "оплат",
)

_EXCHANGE_CONTEXT_MARKERS = (
    "деньг",
    "налич",
    "рубл",
    "usdt",
    "btc",
    "eth",
    "крипт",
    "донг",
    "vnd",
    "бат",
    "thb",
    "лари",
    "gel",
    "вьетнам",
    "дананг",
    "нячанг",
    "хошимин",
    "ханой",
    "фукуок",
    "таиланд",
    "тайланд",
    "пхукет",
    "паттайя",
    "бангкок",
    "самуи",
    "груз",
    "тбилиси",
    "батуми",
    "букинг",
    "booking",
    "аренд",
    "квартир",
    "оплат",
)


def detect_exchange_country(text: str) -> ExchangeCountryProfile | None:
    """Определяет страну exchange-запроса по текстовым маркерам."""
    normalized_text = text.casefold()
    for profile in EXCHANGE_COUNTRY_PROFILES:
        if any(alias in normalized_text for alias in profile.aliases):
            return profile
    return None


def looks_like_exchange_request(text: str) -> bool:
    """Проверяет, что пользователь по смыслу спрашивает про обмен/оплату."""
    normalized_text = text.casefold()
    has_intent = any(marker in normalized_text for marker in _EXCHANGE_INTENT_MARKERS)
    has_context = any(marker in normalized_text for marker in _EXCHANGE_CONTEXT_MARKERS)
    return has_intent and has_context


def is_exchange_knowledge_item(trigger_words: str, category: str | None = None) -> bool:
    """Проверяет, что markdown-карточка относится к обмену валют/крипты."""
    normalized_triggers = trigger_words.casefold()
    return category == "exchange" or any(
        marker in normalized_triggers
        for marker in ("обмен", "курс", "usdt", "btc", "eth", "крипт")
    )
