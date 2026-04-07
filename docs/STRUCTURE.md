# Структура проекта

## `app/api/`

**Назначение**: HTTP слой FastAPI.

**Ключевые файлы**:
- `routers/telegram.py` — webhook endpoint Telegram.
- `deps.py` — общие зависимости HTTP слоя.

## `app/ai/`

**Назначение**: triage/answer агенты, prompts, Gemini client, markdown loader и orchestration.

**Ключевые файлы**:
- `agents/triage.py` — лёгкий агент решения `spam/reply/ignore`.
- `agents/answer.py` — агент ответа с локальным Markdown FAQ и Google Search fallback.
- `orchestration/group_message_orchestrator.py` — orchestration одного сообщения.
- `clients/gemini.py` — обёртка над Google GenAI SDK.
- `knowledge/markdown_store.py` — загрузка FAQ/partners из Markdown frontmatter.
- `prompts/*.md` — системные инструкции агентов.

## `app/core/`

**Назначение**: конфигурация и security helpers.

**Ключевые файлы**:
- `abuse_config.py` — лимит предупреждений, длительность мута и загрузка
  abuse stop-words.
- `abuse_stop_words.txt` — пополняемый список маркеров оскорблений.
- `ai_config.py` — имена Gemini-моделей triage/answer агентов.
- `config.py` — `Settings` из `.env`.
- `spam_config.py` — числовые параметры антиспама и загрузка stop-words.
- `spam_stop_words.txt` — пополняемый список стоп-слов антиспама.
- `security.py` — проверка webhook secret.
- `telegram_config.py` — задержка перед ответом в группе.
- `exceptions.py` — базовые доменные исключения.

## `app/databases/`

**Назначение**: SQLite schema/init для `spam_log`, `chat_log`, `chat_members`, `pending_questions`.

**Ключевые файлы**:
- `sqlite.py` — создание таблиц, connection factory и миграции (`_ensure_*_columns`).

## `app/knowledge/`

**Назначение**: Markdown база FAQ и партнёров.

**Ключевые файлы**:
- `faq/*.md` — локальные FAQ записи с frontmatter и ответом.
- `partners/*.md` — партнёрские карточки с frontmatter и описанием.

## `app/models/`

**Назначение**: dataclass модели домена.

**Ключевые файлы**:
- `group_action.py` — результат обработки группового сообщения для handler-слоя.
- `faq.py`, `partner.py` — база знаний и партнёры.
- `chat.py`, `chat_member.py`, `incoming_message.py` — история, участники, входящее сообщение.

## `app/repositories/`

**Назначение**: слой доступа к SQLite и Markdown knowledge.

**Ключевые файлы**:
- `faq.py`, `partner.py` — lookup по Markdown trigger words.
- `chat_log.py`, `spam_log.py`, `chat_member.py` — история чата, логи спама, активность участников.
- `pending_question.py` — поштучный трекинг вопросов: `add`, `find_ready`,
  `get_open_by_message_id`, `mark_answered_by_reply`, `mark_bot_answered`,
  `exists_open_question`.

## `app/services/`

**Назначение**: бизнес-логика без FastAPI/aiogram объектов.

**Ключевые файлы**:
- `abuse.py` — предупреждения и мут за адресные оскорбления между участниками.
- `spam.py` — deterministic spam pre-filter и логирование.

## `app/telegram/`

**Назначение**: aiogram runtime и handler слой.

**Ключевые файлы**:
- `bot.py` — init/start_webhook/stop_bot.
- `handlers/group.py` — обработка групповых сообщений.
- `services/group_service.py` — pre-filter + AI triage/answer orchestration.
- `middlewares/logging.py` — middleware-заглушка под логирование.

## `tests/`

**Назначение**: pytest проверки структуры и бизнес-логики.
