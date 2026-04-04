"""Тесты triage и answer AI-агентов."""

from __future__ import annotations

import pytest

from app.ai.agents import AnswerAgent, TriageAgent
from app.models.faq import FAQ
from app.models.incoming_message import IncomingMessage
from app.models.partner import Partner


class FakeGeminiClient:
    """Stub Gemini клиента с фиксированным ответом и сбором prompt."""

    def __init__(self, response: str = "") -> None:
        self.response = response
        self.prompts: list[str] = []

    async def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def _exchange_faq() -> FAQ:
    """Возвращает FAQ-карточку обмена для тестов."""
    return FAQ(
        id=1,
        trigger_words="обмен,usdt,вьетнам",
        answer=(
            "Обменник AntEx меняет онлайн-рубли и крипту на THB, VND и GEL. "
            "За обменом пиши @AntEx_support, отзывы здесь:"
        ),
        link="https://t.me/+ui-tQ4T-jrNlNmQy",
        priority=1,
    )


def _exchange_partner() -> Partner:
    """Возвращает partner-карточку обмена для тестов."""
    return Partner(
        id=1,
        name="AntEx Support",
        category="exchange",
        trigger_words="обмен,usdt,вьетнам",
        link="https://t.me/AntEx_support",
        description="Если нужен обмен во Вьетнаме — можно написать сюда:",
        priority=1,
    )


@pytest.mark.asyncio
async def test_triage_agent_parses_reply_verdict() -> None:
    """TriageAgent должен возвращать `reply`, если модель так решила."""
    agent = TriageAgent(gemini_client=FakeGeminiClient("REPLY: есть вопрос"))

    decision = await agent.classify(
        IncomingMessage.build(
            chat_id=1,
            user_id=2,
            message_id=3,
            text="Подскажите, где обменять USDT?",
            has_question=True,
        ),
        has_local_knowledge=True,
    )

    assert decision.action == "reply"
    assert decision.reason == "есть вопрос"


@pytest.mark.asyncio
async def test_triage_agent_fallback_ignores_plain_message_without_model_response() -> None:
    """Без LLM-ответа обычная реплика без вопроса должна игнорироваться."""
    agent = TriageAgent(gemini_client=FakeGeminiClient(""))

    decision = await agent.classify(
        IncomingMessage.build(
            chat_id=1,
            user_id=2,
            message_id=3,
            text="Просто обсуждаем новости",
        ),
        has_local_knowledge=False,
    )

    assert decision.action == "ignore"


@pytest.mark.asyncio
async def test_answer_agent_returns_local_faq_without_web_search_call() -> None:
    """Если найден локальный FAQ, web-search клиент не должен вызываться."""
    client = FakeGeminiClient("AI answer")
    agent = AnswerAgent(web_search_client=client)

    answer = await agent.build_answer(
        "Где арендовать байк?",
        [],
        faq=FAQ(
            id=2,
            trigger_words="байк,скутер",
            answer="По байку обычно проще написать ребятам из локального проката.",
            link="https://example.com/bike",
            priority=10,
        ),
        partner=Partner(
            id=2,
            name="Прокат байков",
            category="bike",
            trigger_words="байк,скутер",
            link="https://example.com/bike",
            description="Если нужен байк, обычно советуют этих ребят:",
            priority=10,
        ),
    )

    assert "По байку обычно проще написать ребятам из локального проката." in answer
    assert "https://example.com/bike" in answer
    assert client.prompts == []


@pytest.mark.asyncio
async def test_answer_agent_builds_human_exchange_answer_via_gemini() -> None:
    """Для exchange-вопроса агент должен просить Gemini собрать живой ответ."""
    client = FakeGeminiClient(
        "Во Вьетнаме можно спокойно обменять деньги через AntEx Support. "
        "Ориентир по курсу сейчас около 26 000 VND за 1 USDT, а ещё ребята "
        "помогают с оплатой Booking и аренды квартиры. "
        "Написать можно сюда: https://t.me/AntEx_support, отзывы — "
        "https://t.me/+ui-tQ4T-jrNlNmQy"
    )
    agent = AnswerAgent(web_search_client=client)

    answer = await agent.build_answer(
        "Подскажите, как поменять деньги во Вьетнаме?",
        [],
        faq=_exchange_faq(),
        partner=_exchange_partner(),
    )

    assert "Во Вьетнаме" in answer
    assert "26 000 VND" in answer
    assert "Booking" in answer
    assert "https://t.me/AntEx_support" in answer
    assert len(client.prompts) == 1
    assert "Собери очень живой, дружелюбный ответ" in client.prompts[0]
    assert "Вьетнам" in client.prompts[0]


@pytest.mark.asyncio
async def test_answer_agent_falls_back_to_local_exchange_copy_when_gemini_is_empty() -> None:
    """Если Gemini недоступен, exchange-ответ должен собираться локально и по-человечески."""
    agent = AnswerAgent(web_search_client=FakeGeminiClient(""))

    answer = await agent.build_answer(
        "Как разменять наличку в Дананге?",
        [],
        faq=_exchange_faq(),
        partner=_exchange_partner(),
    )

    assert "Во Вьетнаме" in answer
    assert "1 USDT" in answer
    assert "Booking" in answer
    assert "аренды квартиры" in answer
    assert "https://t.me/AntEx_support" in answer
    assert "https://t.me/+ui-tQ4T-jrNlNmQy" in answer


@pytest.mark.asyncio
async def test_answer_agent_uses_web_search_fallback_when_local_faq_missing() -> None:
    """Если локального FAQ нет, агент должен вызвать web-search клиента."""
    client = FakeGeminiClient("Свежий ответ из поиска")
    agent = AnswerAgent(web_search_client=client)

    answer = await agent.build_answer("Что нового с визовыми правилами?", [])

    assert answer == "Свежий ответ из поиска"
    assert len(client.prompts) == 1
    assert "Локального FAQ ответа нет." in client.prompts[0]
