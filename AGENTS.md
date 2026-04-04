# AGENTS.md

## Единый источник правил

- Главный регламент проекта: `./admin_bot_rules.md`.
- Все правила по структуре, стеку, архитектуре, тестированию, Telegram-логике и
  документации брать из `admin_bot_rules.md`.
- При конфликте `admin_bot_rules.md` имеет приоритет над этим файлом.

## Agent-Specific Instructions

- Язык общения, комментариев и сообщений: русский.
- Перед началом задачи проверять доступные skills и выбирать минимальный
  достаточный набор.
- Для FastAPI/backend задач использовать `fastapi-development`.
- Это отдельный backend для Telegram-бота без `miniapp` и `admin`.
- Структура должна быть FastAPI backend layout: `app/core`, `app/api/routers`,
  `app/models`, `app/repositories`, `app/schemas`, `app/services`,
  `app/telegram`.
- Не возвращаться к `src/admin_bot` layout.
