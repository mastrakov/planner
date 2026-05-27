# Архитектура — mastroplan_bot

## Обзор системы

```
Telegram ──HTTPS──► nginx ──► aiogram 3 (webhook)
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              Intent Parser    Scheduler        Handlers
                    │          (APScheduler)        │
                    ▼               │               ▼
              AI Router        Briefing/        Services
           ┌──────┴──────┐     Analytics    ┌────┴────┐
           ▼             ▼                  ▼         ▼
      Claude API     OpenAI API         TaskSvc  CalendarSvc
                         │                         │
                     Whisper API            ReminderSvc
                                                   │
                                          IntegrationRegistry
                                                   │
                                          GoogleCalendarProvider
                                          (+ другие в будущем)
                                                   │
                                          PostgreSQL (asyncpg)
```

---

## Стек технологий

| Слой | Технология |
|---|---|
| Язык | Python 3.12 |
| Telegram | aiogram 3 (async) |
| Пакетный менеджер | uv |
| Type checking | pyright |
| Linter | ruff |
| Валидация данных | pydantic v2 |
| ORM | SQLAlchemy 2.0 async |
| БД драйвер | asyncpg |
| База данных | PostgreSQL 16 |
| Миграции | Alembic |
| Планировщик | APScheduler |
| AI | Anthropic API (Claude), OpenAI API (GPT-4o, Whisper) |
| Шифрование | cryptography (Fernet) |
| Контейнеризация | Docker + Docker Compose |
| Reverse proxy | nginx |
| SSL | Let's Encrypt (certbot) |
| CI/CD | GitHub Actions |
| Container Registry | GitHub Container Registry (ghcr.io) |
| Хостинг | Hetzner VPS |

---

## Структура проекта

```
planner/
├── docs/
│   ├── requirements.md
│   └── architecture.md
├── bot/
│   ├── main.py                    # точка входа, запуск polling/webhook
│   ├── config.py                  # pydantic-settings, все env переменные
│   ├── db/
│   │   ├── base.py                # Base, engine, session factory
│   │   ├── models.py              # все SQLAlchemy модели
│   │   ├── migrations/            # Alembic
│   │   │   └── versions/
│   │   └── repo/
│   │       ├── users.py
│   │       ├── tasks.py
│   │       ├── reminders.py
│   │       ├── calendar.py
│   │       ├── chat_history.py
│   │       └── integrations.py
│   ├── handlers/
│   │   ├── __init__.py            # get_main_router(), порядок подключения
│   │   ├── start.py               # /start, /help
│   │   ├── tasks.py               # /tasks, /lists + inline callbacks
│   │   ├── lists_fsm.py           # FSM: создание/переименование списков
│   │   ├── calendar.py            # /calendar + inline callbacks
│   │   ├── reminders.py           # /reminders + inline callbacks
│   │   ├── analytics.py           # /analytics, /weekly, /morning
│   │   ├── settings.py            # /settings, /model + FSM настроек
│   │   ├── google_auth.py         # /connect_google, /disconnect_google, OAuth callback
│   │   ├── voice.py               # голосовые сообщения
│   │   ├── confirm_intent.py      # FSM: подтверждение низкоуверенных intent'ов
│   │   └── ai_chat.py             # catch-all: текст → intent парсинг
│   ├── services/
│   │   ├── tasks.py               # бизнес-логика задач
│   │   ├── calendar.py            # бизнес-логика событий + создание напоминаний
│   │   ├── reminders.py           # бизнес-логика напоминаний (CRUD + check_and_send)
│   │   ├── briefing.py            # сборка утреннего брифинга и недельного плана
│   │   ├── analytics.py           # недельная и месячная статистика
│   │   ├── scheduler.py           # APScheduler jobs
│   │   ├── voice.py               # ogg → mp3 → Whisper → текст
│   │   ├── intent/
│   │   │   ├── parser.py          # текст → AI → ParsedResponse (Pydantic)
│   │   │   ├── router.py          # ParsedIntent → нужный сервис
│   │   │   ├── models.py          # Pydantic-схемы всех намерений
│   │   │   └── prompts.py         # system prompt для intent-парсинга
│   │   └── integrations/
│   │       ├── base.py            # CalendarProvider (ABC), CalendarEventDTO
│   │       ├── registry.py        # IntegrationRegistry
│   │       └── google/
│   │           ├── calendar.py    # GoogleCalendarProvider
│   │           └── auth.py        # OAuth2 flow
│   ├── keyboards/
│   │   ├── tasks.py
│   │   ├── calendar.py
│   │   └── settings.py
│   ├── middlewares/
│   │   ├── auth.py                # проверка whitelist
│   │   └── user.py                # инжект user объекта в handler
│   └── utils/
│       └── dt.py                  # now_utc(), fmt_date(), fmt_time(), fmt_full()
├── tests/
│   ├── conftest.py
│   ├── test_intent_parser.py
│   ├── test_tasks.py
│   └── test_briefing.py
├── deploy/
│   ├── nginx.conf
│   └── certbot-init.sh
├── .github/workflows/ci.yml
├── docker-compose.yml
├── docker-compose.dev.yml
├── Dockerfile
├── pyproject.toml
├── alembic.ini
└── .env.example
```

---

## Слои архитектуры

### 1. Handlers (aiogram роутеры)
Принимают Telegram updates, валидируют входные данные, вызывают сервисы, формируют ответ.
Не содержат бизнес-логику — только оркестрацию.

**Порядок подключения роутеров важен** (более специфичные перед catch-all):
```
start → tasks → lists_fsm → confirm_intent → calendar → reminders
→ settings → analytics → google_auth → voice → ai_chat (catch-all)
```

### 2. Services (бизнес-логика)
Реализуют логику приложения. Не знают про Telegram — работают с доменными объектами.
Вызывают репозитории для работы с БД и провайдеры интеграций.

### 3. Repositories (data access)
Инкапсулируют все SQL-запросы. Сервисы не пишут SQL напрямую.
Один репозиторий на модель/агрегат.

### 4. Integrations (внешние сервисы)
Реализуют единый интерфейс (Provider pattern).
Новая интеграция = новый класс, реализующий абстрактный провайдер.

---

## База данных

### Модели

```
users
├── id (bigint, telegram user_id)
├── username
├── first_name
├── timezone (default: "Europe/Moscow")
├── ai_model (default: "claude")
├── briefing_time (default: "08:00")
├── is_active
└── created_at

task_lists
├── id
├── user_id → users.id
├── name
├── emoji
├── color
├── position
└── created_at

tasks
├── id
├── list_id → task_lists.id
├── user_id → users.id
├── title
├── priority (low/medium/high)
├── scheduled_at (nullable)  ← когда планируется приступить к задаче
├── due_date (nullable)      ← крайний срок выполнения
├── completed_at
└── created_at

task_events
├── id
├── task_id → tasks.id
├── user_id → users.id
├── event_type (created/completed/postponed/deleted/updated)
└── occurred_at

calendar_events
├── id
├── user_id → users.id
├── external_id (Google Calendar event id, nullable)
├── title
├── starts_at
├── ends_at (nullable)
├── repeat (none/daily/weekly/monthly)
└── created_at

reminders
├── id
├── user_id → users.id
├── event_id → calendar_events.id (nullable, CASCADE)  ← привязка к событию
├── task_id  → tasks.id (nullable, CASCADE)             ← привязка к задаче
├── title
├── remind_at
├── repeat (none/daily/weekly/monthly)
├── is_sent
└── created_at

  Три сценария использования:
  • event_id IS NULL, task_id IS NULL → standalone-напоминание («напомни через 10 минут»)
  • event_id IS NOT NULL → напоминание к событию, удаляется каскадно вместе с ним
  • task_id IS NOT NULL  → напоминание к задаче, удаляется каскадно вместе с ней
  Одно событие или задача могут иметь несколько напоминаний с разными remind_at.

user_integrations
├── id
├── user_id → users.id
├── integration_type (calendar/tasks/storage)
├── provider_name (google/notion/...)
├── is_active
├── credentials (зашифровано Fernet: access_token, refresh_token, expiry)
└── created_at

chat_history
├── id
├── user_id → users.id
├── role (user/assistant)
├── content
└── created_at
```

### Миграции

| Revision | Описание |
|---|---|
| `1a84aa9cb3d8` | Initial schema |
| `a3f2b1c4d5e6` | `reminders.event_id` FK → `calendar_events`, удалён `calendar_events.reminder_minutes` |
| `b1c2d3e4f5a6` | `tasks.scheduled_at` (nullable), `reminders.task_id` FK → `tasks` (nullable, CASCADE) |

---

## Intent-парсинг

### Flow
```
Текст/голос
    │
    ▼
IntentParser.parse(text, user, history)
    │
    ├── Формирует system prompt (дата, время, часовой пояс, списки задач пользователя)
    ├── Передаёт последние 10 сообщений из chat_history как контекст
    ├── Запрашивает AI → получает JSON
    └── Pydantic валидирует → ParsedResponse
           │
           ▼
    IntentRouter.route(parsed, user, message, state, history)
           │
           ├── clarification_needed → задать вопрос
           ├── confidence < 0.8 → FSM подтверждения
           ├── destructive action → FSM подтверждения
           └── иначе → _dispatch → нужный сервис
```

### Pydantic-схемы намерений

```python
ParsedIntent = Annotated[
    CreateTaskIntent        # create_task  (с классификацией списка, приоритетом, дедлайном)
    | CreateEventIntent     # create_event  (reminder_minutes: list[int])
    | CreateReminderIntent  # create_reminder
    | ListTasksIntent       # list_tasks
    | CompleteTaskIntent    # complete_task
    | DeleteTaskIntent      # delete_task        ← деструктивное
    | UpdateTaskIntent      # update_task
    | ListEventsIntent      # list_events
    | ListRemindersIntent   # list_reminders
    | DeleteReminderIntent  # delete_reminder    ← деструктивное
    | UpdateReminderIntent  # update_reminder
    | GetBriefingIntent     # get_briefing
    | GetAnalyticsIntent    # get_analytics  (period: "week"|"month")
    | AIChatIntent,         # ai_chat
    Field(discriminator="type"),
]

class ParsedResponse(BaseModel):
    intents: list[ParsedIntent]
    confidence: float           # 0.0 – 1.0
    clarification_needed: str | None

DESTRUCTIVE_INTENT_TYPES = {"delete_task", "delete_reminder"}
```

### CreateTaskIntent — автоклассификация, приоритет, scheduled_at / due_date

```python
class CreateTaskIntent(BaseModel):
    type: Literal["create_task"]
    title: str
    priority: Literal["low", "medium", "high"] = "medium"  # AI определяет из текста
    scheduled_at: datetime | None = None  # когда планируется приступить (с точностью до минуты)
    due_date: datetime | None = None      # крайний срок (может отличаться от scheduled_at)
    suggested_list_id: int | None = None     # ID списка, определённого AI
    suggested_list_name: str | None = None   # Название для отображения пользователю
    list_confidence: float = 0.0             # уверенность в классификации (0.0 – 1.0)
```

**Логика классификации списка:**
- System prompt включает все списки пользователя (id, name, emoji)
- AI анализирует текст задачи и возвращает `suggested_list_id` + `list_confidence`
- `list_confidence >= 0.8` → список подставляется автоматически, бот сообщает: «Добавил в 💼 Работа»
- `list_confidence < 0.8` → бот показывает inline-кнопки с топ-3 вариантами списков для выбора пользователем
- Если у пользователя только один список — всегда используется он без вопросов

**Логика дат:**
- `scheduled_at` — AI извлекает когда пользователь планирует приступить («в субботу в 15:00»)
- `due_date` — AI извлекает крайний срок («до конца воскресенья»); может совпадать с `scheduled_at` или быть позже
- Если оба `None` — бот добавляет inline-кнопку «📅 Добавить дедлайн»
- В брифинге и `/tasks` задача с `scheduled_at` отображается с временем (🕐), без `scheduled_at` но с `due_date` — с датой (📅)

### CreateEventIntent и напоминания

```python
class CreateEventIntent(BaseModel):
    type: Literal["create_event"]
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    reminder_minutes: list[int] = []  # например [60, 10] → за 1 час и за 10 минут
```

`CalendarService.create_event` создаёт по одной строке в `reminders` на каждый элемент списка:
```python
for minutes in intent.reminder_minutes:
    remind_at = event.starts_at - timedelta(minutes=minutes)
    await reminder_repo.create(user_id=..., event_id=event.id, remind_at=remind_at, ...)
```

---

## Напоминания: жизненный цикл

```
Создание события с reminder_minutes=[60, 10]
    │
    ├── CalendarEvent сохранён в calendar_events
    └── 2 строки в reminders (event_id=..., task_id=NULL, is_sent=False)

Создание напоминания к задаче
    │
    └── 1 строка в reminders (event_id=NULL, task_id=..., is_sent=False)

Удаление задачи
    └── reminders с task_id=task.id удаляются каскадно (ondelete=CASCADE)

APScheduler: check_reminders каждую минуту
    │
    └── ReminderRepo.get_pending() → remind_at <= now AND is_sent=False
              │
              ├── bot.send_message(user_id, "🔔 Напоминание: ...")
              └── ReminderRepo.mark_sent(reminder)
                        │
                        ├── repeat=none  → is_sent = True
                        └── repeat≠none  → remind_at += period (цикл до remind_at > now)

Удаление CalendarEvent
    └── reminders с event_id=event.id удаляются каскадно (ondelete=CASCADE)
```

---

## Интеграции (Provider pattern)

```python
# base.py
class CalendarProvider(ABC):
    async def create_event(self, user_id: int, event: CalendarEventDTO) -> str: ...
    async def list_events(self, user_id: int, date_from: date, date_to: date) -> list[CalendarEventDTO]: ...
    async def delete_event(self, user_id: int, event_id: str) -> None: ...
    async def update_event(self, user_id: int, event_id: str, event: CalendarEventDTO) -> None: ...

class CalendarEventDTO(BaseModel):
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    external_id: str | None = None
```

Добавление новой интеграции:
1. Создать `services/integrations/notion/calendar.py` → `NotionCalendarProvider(CalendarProvider)`
2. Зарегистрировать: `registry.register_calendar("notion", NotionCalendarProvider())`
3. Добавить OAuth flow если нужно

---

## Автоматические рассылки (APScheduler)

```python
# Все три джобы запускаются каждый час в :00
# Логика часового пояса — внутри каждой функции
scheduler.add_job(send_morning_briefings, "cron", minute=0)
scheduler.add_job(send_weekly_summary,    "cron", minute=0)
scheduler.add_job(check_reminders,        "interval", minutes=1)
```

**`send_morning_briefings`** — проходит по всем активным пользователям, у кого `briefing_time` совпадает с текущим часом в их часовом поясе (допуск: первые 5 минут часа). В понедельник дополнительно отправляет недельный план.

`BriefingService.build_morning(user)` собирает:
- просроченные задачи (due_date < today, completed_at IS NULL)
- задачи на сегодня (scheduled_at = today **OR** due_date = today без scheduled_at), отсортированные по priority DESC; задачи с scheduled_at отображаются с временем 🕐
- задачи с priority=high и due_date IS NULL и scheduled_at IS NULL (не более 5)
- события на сегодня из `calendar_events`
- напоминания на сегодня из `reminders`
- для каждого события/задачи с scheduled_at: проверяет наличие связанных записей в `reminders` — если нет, предлагает кнопку добавления напоминания

`BriefingService.build_weekly(user)` собирает:
- задачи с due_date в диапазоне [сегодня, +6 дней], сгруппированные по списку, отсортированные по due_date + priority
- задачи с priority=high и due_date IS NULL (не более 5)
- события на неделю из `calendar_events`, сгруппированные по дням
- для каждого события: флаг «без напоминания» для показа кнопок

**`send_weekly_summary`** — та же логика: воскресенье, 20:xx по часовому поясу пользователя.

**`check_reminders`** — выбирает записи из `reminders` где `remind_at <= now AND is_sent=False`, отправляет уведомление, обновляет запись.

---

## CI/CD

```
push/PR → GitHub Actions
    │
    ├── ruff check (lint)
    ├── pyright (type check)
    ├── pytest (unit tests)
    │
    └── (только master) docker build
                │
                ├── push → ghcr.io/mastrakov/planner:latest
                └── ssh deploy@vps
                        └── docker compose pull && docker compose up -d
```

---

## Безопасность

| Механизм | Реализация |
|---|---|
| Whitelist | `AuthMiddleware` проверяет каждый update, неизвестные `user_id` получают отказ |
| Webhook secret | Telegram подписывает запросы, aiogram проверяет подпись |
| Секреты | Только в `.env` на VPS и GitHub Secrets, в репозиторий не попадают |
| Google токены | Шифруются Fernet (`ENCRYPTION_KEY`) перед записью в БД |
| Сеть | PostgreSQL и бот не доступны снаружи Docker-сети, только nginx на 80/443 |
| Фаервол | UFW: открыты только порты 22, 80, 443 |
| Утечки секретов | gitleaks сканирует коммиты в CI |

---

## Локальная разработка

```bash
# 1. Поднять только БД
docker compose -f docker-compose.dev.yml up -d

# 2. Установить зависимости
uv sync

# 3. Скопировать и заполнить .env
cp .env.example .env

# 4. Применить миграции
uv run alembic upgrade head

# 5. Запустить бота (polling режим)
uv run python -m bot.main
```

`ENVIRONMENT=local` в `.env` переключает бота в polling-режим.
Google Calendar OAuth не работает локально (нет домена для callback) — эту интеграцию тестировать на стейдже.
