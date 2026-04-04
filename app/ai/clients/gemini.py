"""Клиент Gemini SDK для AI-агентов."""

from __future__ import annotations

import logging
from time import monotonic

from google import genai
from google.genai import types

from app.core.config import settings
from app.utils.logging import compact_log_text

logger = logging.getLogger(__name__)


class GeminiClient:
    """Обёртка над Google GenAI SDK с опциональным Google Search grounding."""

    def __init__(
        self,
        model: str,
        system_instruction: str,
        *,
        temperature: float = 1,
        max_output_tokens: int,
        use_google_search: bool = False,
    ) -> None:
        self._model = model
        self._system_instruction = system_instruction
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._use_google_search = use_google_search
        self._client = (
            genai.Client(
                api_key=settings.gemini_api_key,
                http_options=self._build_http_options(),
            )
            if settings.gemini_api_key
            else None
        )

    async def generate_text(self, prompt: str) -> str:
        """Генерирует текст Gemini или возвращает пустую строку без API key."""
        if self._client is None:
            logger.info(
                "Gemini request skipped: api_key_configured=False model=%s "
                "use_google_search=%s prompt='%s'",
                self._model,
                self._use_google_search,
                compact_log_text(prompt),
            )
            return ""

        started_at = monotonic()
        logger.info(
            "Gemini request started: model=%s temperature=%s max_output_tokens=%s "
            "use_google_search=%s proxy_enabled=%s prompt='%s'",
            self._model,
            self._temperature,
            self._max_output_tokens,
            self._use_google_search,
            bool(settings.outbound_proxy_url),
            compact_log_text(prompt),
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=self._build_config(),
            )
        except Exception:
            duration_ms = int((monotonic() - started_at) * 1000)
            logger.exception(
                "Gemini request failed: model=%s duration_ms=%s prompt='%s'",
                self._model,
                duration_ms,
                compact_log_text(prompt),
            )
            return ""

        response_text = (response.text or "").strip()
        duration_ms = int((monotonic() - started_at) * 1000)
        logger.info(
            "Gemini response received: model=%s duration_ms=%s response_length=%s "
            "response='%s'",
            self._model,
            duration_ms,
            len(response_text),
            compact_log_text(response_text),
        )
        return response_text

    def _build_config(self) -> types.GenerateContentConfig:
        """Собирает runtime config модели."""
        tools = None
        if self._use_google_search:
            tools = [types.Tool(google_search=types.GoogleSearch())]

        return types.GenerateContentConfig(
            system_instruction=self._system_instruction,
            temperature=self._temperature,
            max_output_tokens=self._max_output_tokens,
            tools=tools,
        )

    @staticmethod
    def _build_http_options() -> types.HttpOptions | None:
        """Собирает proxy-настройки HTTP клиента Gemini."""
        if not settings.outbound_proxy_url:
            return None

        proxy_args = {"proxy": settings.outbound_proxy_url}
        return types.HttpOptions(
            client_args=proxy_args,
            async_client_args=proxy_args,
        )
