# Admin Bot Rules

Единый регламент разработки проекта **admin_bot**.

## Назначение проекта

Telegram-бот-администратор для групп:

- слушает сообщения в группе;
- удаляет спам;
- блокирует авторов спама;
- предупреждает за оскорбления между участниками;
- временно запрещает отправку сообщений после повторных оскорблений;
- отвечает на релевантные вопросы как живой участник;
- мягко направляет к обменнику и партнёрам;
- хранит историю Q/A, участников и логи спама в SQLite;
- хранит FAQ и партнёров в Markdown-файлах.

## Стек

- Python 3.13+
- FastAPI
- aiogram 3.x
- SQLite
- Google Gemini API
- uv

## Архитектурный паттерн

Использовать стандартный backend layout FastAPI с разделением слоёв:

`models -> repositories -> services -> API routers`

Telegram runtime и handlers держать в `app/telegram/`, HTTP webhook — в
`app/api/routers/telegram.py`.

## Базовая структура проекта

```text
app/
├── api/
│   └── routers/
├── ai/
│   ├── agents/
│   ├── clients/
│   ├── knowledge/
│   ├── orchestration/
│   ├── prompts/
│   └── schemas/
├── core/
├── databases/
├── knowledge/
├── models/
├── repositories/
├── schemas/
├── services/
├── telegram/
│   ├── handlers/
│   ├── middlewares/
│   └── services/
├── utils/
└── main.py
tests/
docs/
run.py
pyproject.toml
```

## Правила разработки

- Язык общения, комментариев, docstring и документации — русский.
- Всегда сверяться со skills перед изменениями.
- Для backend/FastAPI задач использовать `fastapi-development`.
- Соблюдать TDD: сначала тест, потом реализация.
- Не смешивать HTTP слой, Telegram handlers, бизнес-логику и доступ к данным.
- Публичные Python API типизировать.
- Новые настройки добавлять через `app/core/config.py` и `.env.example`.
- При изменении функционала обновлять README/docs.
- FAQ и партнёрские рекомендации хранить в `.md` файлах с frontmatter.
- AI-логику держать в `app/ai/`: отдельный triage agent, отдельный answer agent,
  orchestration, prompts, client wrappers и схемы контрактов.

## Поведение бота

- Бот не отвечает на каждое сообщение.
- Локальный pre-filter быстро отсекает явный спам.
- Triage agent решает `spam/reply/ignore` после pre-filter.
- Answer agent сначала ищет локальный FAQ/partners в Markdown, затем при
  необходимости использует Google Search grounding.
- Сообщения со спам-сигналами удаляются, автор блокируется в группе, причина
  пишется в `spam_log`.
- За адресные оскорбления бот сначала отправляет reply-предупреждение с просьбой
  общаться уважительно, а после 2 предупреждений временно ограничивает отправку
  сообщений на 24 часа через `restrict_chat_member`.
- Ответ отправляется reply на конкретное сообщение.
- Перед ответом нужна задержка 5–15 секунд.

## Таблицы SQLite

- `spam_log`
- `chat_log`
- `chat_members`

## Telegram ограничения
