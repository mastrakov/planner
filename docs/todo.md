# TODO — mastroplan_bot

Список задач по итогам ревью функциональных требований.
Каждый пункт содержит принятое решение и что конкретно нужно сделать.

---

## Критичные (ломают логику)

### 1. Двойной показ просроченных задач в брифинге
**Решение:** Блок «Просрочено» имеет приоритет. Задача с `due_date < today_start` попадает только в ⚠️ и исключается из блока «Задачи на сегодня».

- [ ] `services/briefing.py`: в `build_morning` добавить exclusion-set из id просроченных задач перед формированием блока «на сегодня»

---

### 2. Повторяющиеся события + напоминания к ним
**Решение:** Напоминание к повторяющемуся событию создаётся один раз со своим `repeat` (совпадающим с `repeat` события). После срабатывания `mark_sent` продвигает `remind_at` на следующий интервал — по той же логике что standalone-напоминания. `event_id` остаётся для отображения, но не управляет циклом.

- [ ] `services/calendar.py` → `create_event`: при `intent.repeat != none` создавать `Reminder` с тем же `repeat`
- [ ] `db/repo/reminders.py` → `mark_sent`: убедиться что логика продвижения `remind_at` работает для event-привязанных напоминаний (сейчас может быть завязана только на standalone)
- [ ] Добавить в `requirements.md` раздел 3.2: описание поведения повторяющихся напоминаний к событиям

---

### 3. Нет `DeleteEventIntent` и `UpdateEventIntent`
**Решение:** Добавить оба intent'а. `delete_event` — деструктивный (подтверждение). `CalendarService.delete_event` уже реализован — нужно подключить к роутеру. `update_event` реализовать в `CalendarService`.

- [ ] `services/intent/models.py`: добавить `DeleteEventIntent`, `UpdateEventIntent`
- [ ] `services/intent/models.py`: добавить оба в `ParsedIntent` union и `DESTRUCTIVE_INTENT_TYPES`
- [ ] `services/intent/router.py`: добавить dispatch для `delete_event`, `update_event`
- [ ] `services/calendar.py`: реализовать `update_event` (title, starts_at, ends_at)
- [ ] `services/intent/prompts.py`: описать новые intent'ы в system prompt
- [ ] `requirements.md` раздел 5.2: добавить `delete_event` и `update_event` в таблицу намерений

---

## Важные (некорректное поведение)

### 4. Подтверждение мультиинтента
**Решение:** Если в `ParsedResponse.intents` есть хотя бы один деструктивный intent — весь пакет показывается пользователю списком и выполняется только после единого подтверждения.

- [ ] `services/intent/router.py`: проверять `any(i.type in DESTRUCTIVE_INTENT_TYPES for i in intents)` перед dispatch, а не только первый intent
- [ ] `handlers/confirm_intent.py`: при подтверждении выполнять все intent'ы пакета по порядку
- [ ] `requirements.md` раздел 5.2: зафиксировать правило

---

### 5. `due_date` без времени → 23:59
**Решение:** Если пользователь указал только дату без времени — AI устанавливает `due_date = 23:59:00` этого дня в TZ пользователя. Прописать в system prompt.

- [ ] `services/intent/prompts.py`: добавить правило «due_date без времени = 23:59:00 дня дедлайна в TZ пользователя»
- [ ] `requirements.md` раздел 2.2: добавить пояснение

---

### 6. `scheduled_at` / `due_date` в прошлом
**Решение:** Валидация в intent-роутере при создании задачи (`create_task`): если дата < `now - 1h` — ошибка с подсказкой. `update_task` — допускает прошедшие даты (ручная правка). Допуск 1 час защищает от ложных срабатываний.

- [ ] `services/intent/router.py`: в обработке `create_task` добавить проверку `scheduled_at` и `due_date` на прошлое
- [ ] Текст ошибки: «Дата "[дата]" уже прошла. Уточните — например, "сегодня в 18:00" или "завтра".»
- [ ] `requirements.md` раздел 2.2: зафиксировать правило

---

### 7. Нет обработки ошибок AI API
**Решение:** Один retry через 2 секунды. При повторной ошибке — fallback-сообщение: «AI-сервис временно недоступен. Используйте команды: /tasks, /calendar, /reminders.» Автоматического переключения провайдера нет.

- [ ] `services/intent/parser.py`: обернуть вызов AI в try/except, retry 1 раз с `asyncio.sleep(2)`
- [ ] Перехватывать: сетевые ошибки, 429 rate limit, любые API exceptions
- [ ] `requirements.md` раздел 5.2: добавить описание поведения при ошибке

---

### 8. Google токены — flow при ошибке
**Решение:** При устаревшем `access_token` — автообновление через `refresh_token` (один раз, без уведомления). Если `refresh_token` невалиден — деактивировать интеграцию (`is_active = False`) + уведомить пользователя: «Токен Google Calendar истёк. Переподключите: /connect_google».

- [ ] `services/integrations/google/calendar.py`: добавить try/except на `google.auth.exceptions.RefreshError`
- [ ] `db/repo/integrations.py`: метод `deactivate(user_id, integration_type)`
- [ ] При RefreshError: deactivate + `bot.send_message(user_id, "...")`
- [ ] `requirements.md` раздел 3.3: заменить «токены автоматически обновляются» на детальное описание

---

## Средние (UX и корректность)

### 9. Алгоритм поиска задачи по названию
**Решение:** Case-insensitive substring-match. 2–5 совпадений → список с выбором. >5 совпадений → только счётчик, просьба уточнить.

- [ ] `db/repo/tasks.py` или `services/tasks.py`: унифицировать поиск — `ilike(f"%{query}%")`
- [ ] При >5 совпадениях возвращать счётчик без списка
- [ ] `requirements.md` раздел 2.2 и 9: зафиксировать алгоритм

---

### 10. Период для `/weekly` по запросу
**Решение:** Всегда rolling 7 дней от момента запроса — и для ручного `/weekly`, и для автоматического воскресного саммари. Текущая реализация `now - timedelta(days=7)` уже корректна, нужно зафиксировать в требованиях.

- [ ] Проверить что `analytics.py` / `briefing.py` используют одинаковый период для обоих случаев
- [ ] `requirements.md` раздел 6.3: уточнить «последние 7 дней от момента запроса»

---

### 11. Смена timezone — применяется со следующего дня
**Решение:** Новый timezone вступает в силу начиная со следующего дня. При смене — сообщить пользователю новое время брифинга.

- [ ] `handlers/settings.py`: при сохранении нового timezone отправить подтверждение: «Часовой пояс изменён. Брифинг будет приходить в 08:00 Europe/Berlin начиная с завтрашнего дня»
- [ ] `services/scheduler.py`: `send_morning_briefings` — проверять timezone из БД, изменения подхватываются автоматически при следующем часовом тике
- [ ] `requirements.md` раздел 8: добавить пояснение

---

### 12. OAuth callback в локальной разработке
**Решение:** При `settings.is_local` команда `/connect_google` возвращает явное сообщение вместо broken ссылки.

- [ ] `handlers/google_auth.py` → `cmd_connect_google`: добавить `if settings.is_local: return await message.answer("Google OAuth недоступен в локальной разработке. Используйте ngrok или разверните на сервере.")`
- [ ] `requirements.md` раздел 3.3: задокументировать

---

## Инфраструктурные

### 13. Брифинг — защита от пропуска при даунтайме
**Решение:** Таблица `sent_briefings (user_id, date DATE, briefing_type TEXT, sent_at TIMESTAMPTZ)`. Перед отправкой — проверка записи. При старте — catch-up если `now < briefing_time + 3h`.

- [ ] Alembic миграция: таблица `sent_briefings`
- [ ] `db/repo/`: добавить `SentBriefingsRepo` с методами `was_sent(user_id, date, type)` и `mark_sent(...)`
- [ ] `services/scheduler.py` → `send_morning_briefings`: проверять `sent_briefings` перед отправкой и писать запись после
- [ ] Catch-up логика при старте: если запись отсутствует и `now < briefing_time + 3h` — отправить немедленно
- [ ] `requirements.md` раздел 6.1: добавить описание механизма

---

### 14. `chat_history` — лимит и TTL
**Решение:** Max 10 записей per user (удалять старые при вставке). APScheduler job раз в сутки удаляет записи старше 7 дней.

- [ ] `db/repo/chat_history.py` → `add`: после вставки удалять записи пользователя сверх 10 последних
- [ ] `services/scheduler.py`: добавить daily job `cleanup_chat_history` — `DELETE WHERE created_at < now - 7 days`
- [ ] `requirements.md` раздел 5.3: уточнить

---

## Не делаем (зафиксированные решения)

- **Intent'ы для управления списками** — FSM через `/lists` достаточен. Списки — редкая структурная операция.
- **`confidence` per intent** — оставить на уровне `ParsedResponse`. Проблема мультиинтента решена через правило в п.4.
- **Автоматический failover AI провайдера** — только ручное переключение через `/settings`.
