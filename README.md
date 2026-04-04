# admin_bot

Telegram-бот-администратор для групп. Работает как FastAPI backend + aiogram webhook,
видит сообщения группы, удаляет спам, блокирует спамеров, предупреждает за
оскорбления, временно ограничивает отправку сообщений после повторных нарушений,
отвечает на релевантные вопросы, использует Markdown FAQ/partners, Gemini API
с Google Search grounding и SQLite для Q/A истории и логов.

## Стек

- Python 3.13+
- FastAPI
- aiogram 3.x
- SQLite
- Google Gemini API
- uv

## Структура проекта

```text
.
├── app/
│   ├── api/routers/          # FastAPI routers
│   ├── ai/                   # triage/answer agents, prompts, orchestration, clients
│   ├── core/                 # настройки и security helpers
│   ├── databases/            # SQLite init для chat/spam логов
│   ├── knowledge/            # markdown FAQ и partners
│   ├── models/               # dataclass модели домена
│   ├── repositories/         # доступ к SQLite и markdown knowledge
│   ├── schemas/              # Pydantic схемы HTTP слоя
│   ├── services/             # бизнес-сервисы без FastAPI/aiogram объектов
│   ├── telegram/             # lifecycle, handlers, middlewares, bot-facing services
│   ├── utils/                # утилиты
│   └── main.py               # FastAPI app entrypoint
├── tests/
├── docs/
├── admin_bot_rules.md        # единый SSOT правил проекта
├── AGENTS.md                 # agent-specific инструкции со ссылкой на SSOT
├── .env.example
├── Dockerfile
├── pyproject.toml
└── run.py
```

## Быстрый старт

```bash
cp .env.example .env
uv sync --extra dev
uv run python run.py
```

Healthcheck:

```bash
curl http://127.0.0.1:8000/health
```

## Проверка бота в уже созданной группе

1. В `@BotFather` отключи Privacy Mode для бота.
2. Добавь бота администратором в группу и выдай права `can_delete_messages`
   и `can_restrict_members`.
3. Заполни `.env`:
   - `BOT_TOKEN` — токен созданного бота;
   - `BOT_USERNAME` — username бота без `@`;
   - `TELEGRAM_MODE=polling` — для локальной разработки;
   - `TELEGRAM_MODE=webhook` и `WEBHOOK_URL` — для деплоя с публичным HTTPS;
   - `WEBHOOK_SECRET` — секрет webhook, если хочешь проверку заголовка
     `X-Telegram-Bot-Api-Secret-Token`;
   - `GEMINI_API_KEY` — ключ Gemini, если нужен AI fallback.
4. Запусти backend и проверь `/health`.
5. Напиши в группе `/start` — бот должен ответить `Бот запущен.`.
6. Напиши вопрос с FAQ-триггером, например `Какой сейчас курс usdt?` —
   бот должен ответить reply-сообщением на основе `app/knowledge/faq`.
7. Отправь сообщение со спам-сигналом, например `free usdt airdrop` —
   бот должен удалить сообщение и заблокировать автора, если у него есть права.
8. Отправь адресное оскорбление, например `Ты дурак`, — бот должен сначала дать
   2 предупреждения, а на 3-м нарушении временно запретить пользователю писать
   в группу на 24 часа, если у него есть `can_restrict_members`.

## Основные переменные окружения

- `BOT_TOKEN` — токен Telegram-бота.
- `BOT_USERNAME` — username бота без `@`, нужен для распознавания упоминаний/reply.
- `TELEGRAM_MODE` — режим Telegram runtime: `polling` для разработки,
  `webhook` для деплоя.
- `WEBHOOK_URL` — публичный HTTPS URL сервиса.
- `WEBHOOK_PATH` — путь webhook endpoint, по умолчанию `/telegram/webhook`.
- `WEBHOOK_SECRET` — секрет для проверки `X-Telegram-Bot-Api-Secret-Token`.
- `GEMINI_API_KEY` — ключ Google Gemini API.
- `PROXY_HTTP` — HTTP proxy в формате `host:port:username:password`, например
  `135.106.25.252:63488:jhtD1E2e:jUWKgx2U`.
- `PROXY_URL` — готовый HTTP/SOCKS proxy URL, если удобнее передать сразу
  `http://user:pass@host:port` или `socks5://127.0.0.1:1080`.
- `DATABASE_PATH` — путь к SQLite базе, по умолчанию `./data/knowledge.db`.
- `KNOWLEDGE_BASE_DIR` — путь к каталогу Markdown базы знаний,
  по умолчанию `./app/knowledge`.

Не-секретные параметры антиспама, задержек и имена Gemini-моделей лежат не в
`.env`, а в коде:

- `app/core/abuse_config.py`
- `app/core/abuse_stop_words.txt`
- `app/core/spam_config.py`
- `app/core/spam_stop_words.txt`
- `app/core/telegram_config.py`
- `app/core/ai_config.py`

## Поведение бота

- Удаляет спам по правилам из `app/services/spam.py` и блокирует автора.
- Предупреждает за адресные оскорбления по правилам из `app/services/abuse.py`.
- После 2 предупреждений временно ограничивает отправку сообщений на 24 часа
  через Telegram `restrict_chat_member`.
- Если pre-filter не нашёл явный спам, `TriageAgent` решает `spam/reply/ignore`.
- Если нужен ответ, `AnswerAgent` сначала использует `app/knowledge/*.md`, а при
  отсутствии локального FAQ включает Google Search grounding.
- Перед ответом ждёт 5-15 секунд.
- Отвечает reply на конкретное сообщение.

## Как это работает в файлах

1. FastAPI стартует в `app/main.py`, при наличии `BOT_TOKEN` инициализирует
   aiogram и запускает `polling` или `webhook` по `TELEGRAM_MODE`.
2. В `polling`-режиме `app/telegram/bot.py` сам читает updates из Telegram.
   В `webhook`-режиме Telegram присылает updates в `app/api/routers/telegram.py`.
3. `app/telegram/handlers/group.py` принимает сообщения группы, нормализует их
   в `IncomingMessage` и вызывает `GroupService`.
4. `app/services/spam.py` выполняет быстрый deterministic pre-filter и при
   явном спаме пишет причину в `spam_log`.
5. `app/services/abuse.py` детектит адресные оскорбления по словарю и контексту,
   выдаёт предупреждения и после повторных нарушений формирует mute-решение.
6. `app/ai/orchestration/group_message_orchestrator.py` вызывает `TriageAgent`
   и решает, игнорировать сообщение или готовить ответ.
7. `app/ai/agents/answer.py` берёт локальный FAQ/partners из Markdown, добавляет
   историю `chat_log`, а при отсутствии локального FAQ использует Google Search.
8. `app/telegram/services/group_service.py` сохраняет Q/A пару в `chat_log`,
   обновляет `chat_members` и отдаёт handler-слою `GroupMessageResult` с action
   `ignore/reply/delete_spam/warn_user/mute_user`.

## Где лежит промпт

- Системные промпты лежат в `app/ai/prompts/answer.md` и
  `app/ai/prompts/triage.md`.
- Имена Gemini-моделей лежат в `app/core/ai_config.py`.
- FAQ/partner данные хранятся в `app/knowledge/faq/*.md` и
  `app/knowledge/partners/*.md`.
- Stop-words антиспама лежат в `app/core/spam_stop_words.txt`.
- Stop-words для abuse moderation лежат в `app/core/abuse_stop_words.txt`.

## Документация

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/STRUCTURE.md](docs/STRUCTURE.md)
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- [admin_bot_rules.md](admin_bot_rules.md)
