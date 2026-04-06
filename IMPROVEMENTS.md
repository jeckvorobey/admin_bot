# Улучшения и план доработки admin_bot

Документ составлен по результатам тестирования 04–06.04.2026.

---

## Реализовано (06.04.2026)

### Блок 1 — Исправлен triage: бот перестал вмешиваться в чужие разговоры

**Проблема**: бот отвечал на вопросы между людьми, реплики вида "Наконец-то обратная связь",
вопросы адресованные другим пользователям (`@username что думаешь?`).

**Что изменено**:
- `app/models/incoming_message.py` — добавлены поля `mention_targets` и `user_language`
- `app/telegram/handlers/group.py` — извлечение упомянутых пользователей из entities
- `app/ai/agents/triage.py` — исправлен `_fallback_decision`: вопрос без FAQ и без обращения к боту → IGNORE
- `app/ai/agents/triage.py` — в промпт добавлен `mention_targets` и `user_language`

### Блок 2 — Правильный механизм 5 минут

**Проблема**: бот отвечал мгновенно (5–15 сек), не ждал ответа от живых участников.
`_check_unanswered_question` искал в `chat_log` (отвеченные вопросы), а не pending.

**Что изменено**:
- `app/databases/sqlite.py` — новая таблица `pending_questions`
- `app/repositories/pending_question.py` — новый репозиторий (add/find_ready/mark_answered/mark_bot_answered)
- `app/models/group_action.py` — новый action `PENDING_REPLY`
- `app/telegram/services/group_service.py` — при triage=REPLY сохраняет в pending, возвращает PENDING_REPLY
- `app/telegram/services/group_service.py` — любое сообщение → `mark_answered()` (кто-то активен)
- `app/telegram/handlers/group.py` — при PENDING_REPLY запускает `asyncio.create_task(_delayed_answer_check)`
- `app/core/telegram_config.py` — константа `PENDING_REPLY_DELAY_SECONDS = 300`

### Блок 3 — Промпты переведены на английский

**Проблема**: промпты на русском снижали качество LLM-классификации (Gemini лучше работает с English).

**Что изменено**:
- `app/ai/prompts/triage.md` — полностью на English, добавлены few-shot примеры (7 кейсов)
- `app/ai/prompts/answer.md` — полностью на English, правила форматирования и языка
- `app/core/words/bot_behavior.md` — полностью на English

### Блок 4 — Определение языка пользователя

**Проблема**: бот всегда отвечал только на русском.

**Что изменено**:
- `app/models/incoming_message.py` — поле `user_language`
- `app/telegram/handlers/group.py` — берётся из `message.from_user.language_code`
- `app/ai/agents/answer.py` — передаётся в промпт exchange и web-search
- `app/ai/orchestration/group_message_orchestrator.py` — передаётся в `build_answer()`

### Блок 5 — Исправлен обрыв сообщений

**Проблема**: бот обрывал ответы на середине.

**Что изменено**:
- `app/ai/agents/answer.py` — `max_output_tokens`: 500 → 1024, `temperature`: 0.7 → 1.0

### Блок 6 — Форматирование ответов

Включено в обновлённый `app/ai/prompts/answer.md`:
- Короткие абзацы вместо списков с `*`
- Не более 3–4 пунктов если список нужен
- Без markdown-таблиц
- Умеренное использование emoji

---

## Следующая итерация (Блок 7 — Самообучение и RAG)

### Фаза 1: Поиск похожих вопросов в истории

- [ ] `app/repositories/chat_log.py` — метод `find_similar(question, chat_id)` по ключевым словам
- [ ] Использовать похожие Q&A в контексте answer агента
- [ ] Это снизит нагрузку на web-search и улучшит консистентность ответов

### Фаза 2: Feedback loop

- [ ] Таблица `answer_feedback (message_id, rating, created_at)`
- [ ] Обработчик реакций 👍/👎 на сообщения бота
- [ ] Использовать для фильтрации повторяющихся плохих ответов

### Фаза 3: Автоматическое обновление FAQ

- [ ] Анализ `chat_log` — популярные вопросы без FAQ-карточки
- [ ] Создание черновиков новых карточек (cron или /admin команда)
- [ ] Добавить английские trigger-слова в FAQ/partner карточки

---

## Тестирование

```bash
# Запустить бота
uv run python run.py

# Тестовые сценарии:
# 1. "Привет, как дела?" → бот НЕ должен отвечать
# 2. "@username что думаешь?" → бот НЕ должен отвечать
# 3. "Наконец-то обратная связь" → бот НЕ должен отвечать
# 4. "@admin_bot где поменять деньги?" → бот ДОЛЖЕН ответить (сразу, т.к. прямое обращение)
# 5. "где поменять деньги?" → бот должен ПОДОЖДАТЬ 5 мин, если никто не ответил — ответить
# 6. Задать вопрос, через 2 мин кто-то ответил → бот НЕ должен отвечать
# 7. "where to exchange money?" → бот должен ответить по-английски

# Прогон тестов
uv run pytest tests/ -v
uv run ruff check app tests
```
