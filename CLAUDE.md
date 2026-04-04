# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Единый источник правил

- Главный регламент проекта: `./admin_bot_rules.md`.
- Все правила по архитектуре, стеку, разделению слоёв, тестированию и поведению
  бота брать из `admin_bot_rules.md`.
- При конфликте `admin_bot_rules.md` имеет приоритет.
- Подробную архитектуру см. в `docs/ARCHITECTURE.md`, структуру проекта — в
  `docs/STRUCTURE.md`.

## Язык и инструменты

- Язык общения, комментариев, docstring и кода: русский.
- Стек: Python 3.13+, FastAPI, aiogram 3.x, SQLite, Google Gemini API, uv.
- Линтер и форматер: ruff (конфиг в `pyproject.toml`).
- Тестирование: pytest, pytest-asyncio (конфиг в `pyproject.toml`).

## Частые команды

```bash
# Установка зависимостей
uv sync --extra dev

# Запуск backend
uv run python run.py

# Линтинг и форматирование
uv run ruff check app tests
uv run ruff format app tests

# Тестирование
uv run pytest                          # все тесты
uv run pytest tests/test_spam_service.py::test_name  # конкретный тест
uv run pytest tests -v                # с выводом имён
uv run pytest --cov=app               # с покрытием

# Healthcheck
curl http://127.0.0.1:8000/health
```

## Архитектура в одной строке

FastAPI backend с разделением слоёв `models → repositories → services → API/Telegram`.
Telegram runtime (polling/webhook) в `app/telegram/`, HTTP webhook в
`app/api/routers/telegram.py`. AI-логика (triage/answer агенты, prompts,
orchestration) в `app/ai/`. Правила спама и оскорблений в `app/services/`,
Markdown FAQ/partners в `app/knowledge/`, SQLite логи в `app/databases/`.

## Поток обработки сообщения

1. `app/telegram/handlers/group.py` нормализует сообщение в `IncomingMessage`.
2. `app/services/spam.py` выполняет deterministic pre-filter для явного спама.
3. `app/services/abuse.py` проверяет адресные оскорбления, выдаёт предупреждения
   и формирует mute на 24 часа после 2 предупреждений.
4. `app/ai/orchestration/group_message_orchestrator.py` вызывает `TriageAgent`
   для решения `spam/reply/ignore`.
5. При нужде в ответе `AnswerAgent` использует Markdown FAQ, добавляет историю
   `chat_log`, при отсутствии локального FAQ включает Google Search grounding.
6. `app/telegram/services/group_service.py` сохраняет Q/A в `chat_log`, логирует
   в `spam_log`, обновляет `chat_members` и отдаёт handler-слою `GroupMessageResult`.

## Где менять поведение

- **Spam/abuse классификация**: `app/services/spam.py`, `app/services/abuse.py`,
  `app/core/spam_stop_words.txt`, `app/core/abuse_stop_words.txt`.
- **AI-ответ**: `app/ai/prompts/answer.md`, `app/ai/prompts/triage.md`,
  `app/core/ai_config.py`.
- **FAQ/partners данные**: `app/knowledge/faq/*.md`, `app/knowledge/partners/*.md`.
- **Задержка перед ответом**: `app/core/telegram_config.py`.
- **Telegram mode (polling/webhook)**: `app/core/config.py`, запуск в
  `app/main.py`, lifecycle в `app/telegram/bot.py`.
- **SQLite schema**: `app/databases/sqlite.py`.

## Разделение слоёв

- `models/` — dataclass-сущности без SQL и HTTP.
- `repositories/` — SQL к SQLite, lookup по Markdown.
- `services/` — бизнес-логика без FastAPI/aiogram объектов.
- `ai/` — агенты, prompts, Gemini client, orchestration.
- `api/routers/` — HTTP webhook.
- `telegram/handlers/` — тонкий aiogram слой без SQL.
- `telegram/services/` — orchestration спама/abuse/triage/answer.

## TDD и тестирование

- Перед реализацией писать тест.
- При изменении бизнес-логики обновлять соответствующие тесты в `tests/`.
- Тесты пишутся для `services/`, `repositories/`, `models/` — не мокировать
  SQLite, использовать реальное подключение.
