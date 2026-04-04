# Развёртывание

## Локальный запуск

```bash
cp .env.example .env
uv sync --extra dev
uv run python run.py
```

Проверка healthcheck:

```bash
curl http://127.0.0.1:8000/health
```

## Проверка Telegram-бота и группы

### Что должно быть настроено в Telegram

1. Бот создан в `@BotFather`.
2. Privacy Mode отключён, иначе бот не увидит обычные сообщения группы.
3. Бот добавлен администратором в группу.
4. У бота есть права `can_delete_messages` и `can_restrict_members`.

### Что должно быть настроено в `.env`

- `BOT_TOKEN` — токен бота.
- `BOT_USERNAME` — username бота без `@`.
- `TELEGRAM_MODE=polling` — для локальной разработки.
- `TELEGRAM_MODE=webhook` — для деплоя.
- `WEBHOOK_URL` — публичный HTTPS URL backend, нужен только в `webhook`-режиме.
- `WEBHOOK_PATH` — путь webhook, по умолчанию `/telegram/webhook`.
- `WEBHOOK_SECRET` — секрет для проверки webhook заголовка, если нужен.
- `GEMINI_API_KEY` — ключ Gemini для AI-ответов.
- `DATABASE_PATH` — путь к SQLite базе.
- `KNOWLEDGE_BASE_DIR` — путь к Markdown базе FAQ/partners.

`SPAM_*`, `REPLY_DELAY_*` и `GEMINI_MODEL` в `.env` больше не задаются.
Теперь это обычные конфиги в коде:

- `app/core/spam_config.py`
- `app/core/spam_stop_words.txt`
- `app/core/telegram_config.py`
- `app/core/ai_config.py`

Если backend запущен локально, ставь `TELEGRAM_MODE=polling` — тогда публичный
`WEBHOOK_URL` не нужен. Для деплоя ставь `TELEGRAM_MODE=webhook` и указывай
публичный HTTPS адрес в `WEBHOOK_URL`.

### Как проверить сценарии в группе

1. Запусти backend и убедись, что `/health` возвращает `{"status":"ok","app":"admin_bot"}`.
2. Напиши в группе `/start` — бот должен ответить `Бот запущен.`.
3. Напиши `Какой сейчас курс usdt?` — это совпадает с FAQ trigger из
   `app/knowledge/faq/exchange.md`, поэтому бот должен ответить через reply.
4. Напиши `@<BOT_USERNAME> подскажи, где лучше обменять usdt?` — бот должен
   ответить, потому что есть явное упоминание.
5. Ответь reply на сообщение бота обычным вопросом — бот должен продолжить
   диалог, потому что reply на бота тоже считается сигналом ответа.
6. Отправь спам-текст вроде `free usdt airdrop` — сообщение должно удалиться,
   пользователь должен быть заблокирован, а причина должна попасть в `spam_log`.

### Если бот не отвечает

- Проверь, что `BOT_USERNAME` в `.env` указан без `@` и совпадает с username
  бота в Telegram.
- Проверь, что `WEBHOOK_URL + WEBHOOK_PATH` указывает на публичный HTTPS endpoint.
- Если задан `WEBHOOK_SECRET`, Telegram должен присылать тот же секрет в
  `X-Telegram-Bot-Api-Secret-Token`.
- Проверь, что сообщение отправлено именно в `group`/`supergroup`, а не в личный
  чат: текущий group handler личные сообщения не обрабатывает.
- Проверь, что у бота выключен Privacy Mode и есть админские права на удаление
  сообщений и блокировку участников.

## Coolify

1. Подключить репозиторий и выбрать сборку по `Dockerfile`.
2. Задать env переменные из `.env.example`.
3. Если нужна сохранность SQLite между релизами — примонтировать volume в `/app/data`.
4. Healthcheck endpoint: `/health`.
5. В `WEBHOOK_URL` указать публичный HTTPS домен Coolify.
6. В `TELEGRAM_MODE` указать `webhook`.

## Telegram настройки

- Отключить Privacy Mode в `@BotFather`.
- Добавить бота админом группы.
- Выдать `can_delete_messages`.
- Выдать `can_restrict_members`, чтобы бот мог блокировать спамеров.
