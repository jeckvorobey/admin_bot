# Архитектура admin_bot

## Кратко

Проект использует стандартный FastAPI backend layout: HTTP слой в
`app/api/routers`, AI-агенты и orchestration в `app/ai`, бизнес-логика в
`app/services`, SQLite/Markdown доступ в `app/repositories`, Telegram lifecycle
и aiogram handlers в `app/telegram`.

## Основной поток

1. `app/main.py` при старте выбирает Telegram runtime по `TELEGRAM_MODE`.
2. В `polling`-режиме `app/telegram/bot.py` сам забирает updates из Telegram.
3. В `webhook`-режиме Telegram отправляет update в `POST /telegram/webhook`, а
   `app/api/routers/telegram.py` проверяет webhook secret и передаёт update в
   aiogram dispatcher.
4. `app/telegram/handlers/group.py` нормализует сообщение в `IncomingMessage`.
5. `app/services/spam.py` выполняет deterministic pre-filter для явного спама.
6. `app/services/abuse.py` проверяет адресные оскорбления по словарю и контексту,
   даёт 2 предупреждения и на 3-м нарушении формирует mute на 24 часа.
7. `app/ai/orchestration/group_message_orchestrator.py` вызывает `TriageAgent`
   и получает решение `spam/reply/ignore`.
8. Если нужен ответ, `AnswerAgent` берёт FAQ/partners из Markdown, добавляет
   историю `chat_log`, при необходимости включает Google Search grounding и
   возвращает текст ответа.
9. `app/telegram/services/group_service.py` пишет Q/A в `chat_log`,
   spam/abuse-причины в `spam_log`, обновляет `chat_members` и отдаёт
   `GroupMessageResult` handler-слою.

## Где лежит промпт и как строится ответ

- `app/ai/prompts/triage.md` и `app/ai/prompts/answer.md` содержат системные
  инструкции агентов.
- `app/core/ai_config.py` содержит имена Gemini-моделей.
- `app/repositories/faq.py` и `app/repositories/partner.py` читают
  `app/knowledge/*/*.md` через markdown frontmatter.
- `AnswerAgent` добавляет к новому вопросу историю `chat_log`, локальный partner
  контекст и при отсутствии FAQ использует Google Search grounding.

## Где менять поведение

- Стиль AI-ответа, spam-классификация и имена Gemini-моделей:
  `app/ai/prompts/*.md` и `app/core/ai_config.py`.
- Формат prompt, fallback и partner-append:
  `app/ai/agents/answer.py` и `app/ai/agents/triage.py`.
- FAQ/partner данные: `app/knowledge/faq/*.md` и
  `app/knowledge/partners/*.md`.
- Стоп-слова и числовые параметры антиспама: `app/core/spam_config.py` и
  `app/core/spam_stop_words.txt`.
- Стоп-слова, лимит предупреждений и длительность мута за оскорбления:
  `app/core/abuse_config.py`, `app/core/abuse_stop_words.txt`,
  `app/services/abuse.py`.
- Задержка перед ответом: `app/core/telegram_config.py`.
- Условия `spam/reply/ignore`: `TriageAgent` +
  `app/ai/orchestration/group_message_orchestrator.py`.
- Режим Telegram runtime `polling/webhook`: `telegram_mode` в
  `app/core/config.py`, запуск в `app/main.py`, lifecycle в `app/telegram/bot.py`.
- Распознавание mention/reply/question и извлечение metadata сообщения:
  `app/telegram/handlers/group.py`.
- Антиспам-эвристики: `app/services/spam.py`.
- Модерация оскорблений: `app/services/abuse.py` +
  `app/repositories/chat_member.py`.

## Разделение слоёв

- `models` — dataclass-сущности без SQL и HTTP.
- `repositories` — SQL к SQLite и lookup по Markdown.
- `ai` — агенты, prompts, Gemini client, markdown loader и orchestration.
- `services` — бизнес-сервисы без FastAPI/aiogram объектов.
- `api/routers` — HTTP webhook.
- `telegram/handlers` — тонкий aiogram слой без SQL.

## База данных

SQLite таблицы создаются в `app/databases/sqlite.py`. FAQ/partners данные
хранятся не в SQLite, а в `app/knowledge/faq/*.md` и
`app/knowledge/partners/*.md`.

Таблицы:

- `spam_log`
- `chat_log`
- `chat_members`

`chat_members` также хранит `abuse_warning_count` и `muted_until_at` для
предупреждений и временных ограничений.

## Правила проекта

Единый источник правил — [../admin_bot_rules.md](../admin_bot_rules.md).
