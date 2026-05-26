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
                     Whisper API            IntegrationRegistry
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
├── docs/                          # документация
│   ├── requirements.md
│   └── architecture.md
├── bot/
│   ├── __init__.py
│   ├── main.py                    # точка входа, запуск polling/webhook
│   ├── config.py                  # pydantic-settings, все env переменные
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py                # Base, engine, session factory
│   │   ├── models.py              # все SQLAlchemy модели
│   │   └── repo/                  # репозитории (data access layer)
│   │       ├── __init__.py
│   │       ├── users.py
│   │       ├── tasks.py
│   │       ├── reminders.py
│   │       ├── calendar.py
│   │       └── integrations.py
│   ├── handlers/                  # aiogram роутеры
│   │   ├── __init__.py
│   │   ├── start.py               # /start, /help
│   │   ├── tasks.py               # /tasks, /lists
│   │   ├── calendar.py            # /calendar
│   │   ├── settings.py            # /settings, /model
│   │   ├── analytics.py           # /analytics, /weekly
│   │   ├── voice.py               # голосовые сообщения
│   │   ├── google_auth.py         # /connect_google, OAuth callback
│   │   └── ai_chat.py             # свободный диалог, intent роутинг
│   ├── services/
│   │   ├── __init__.py
│   │   ├── voice.py               # ogg → mp3 → Whisper → текст
│   │   ├── briefing.py            # сборка утреннего брифинга
│   │   ├── analytics.py           # недельная аналитика
│   │   ├── scheduler.py           # APScheduler jobs
│   │   ├── tasks.py               # бизнес-логика задач
│   │   ├── calendar.py            # бизнес-логика событий
│   │   ├── reminders.py           # бизнес-логика напоминаний
│   │   ├── intent/
│   │   │   ├── __init__.py
│   │   │   ├── parser.py          # текст → AI → ParsedResponse (Pydantic)
│   │   │   ├── router.py          # ParsedIntent → нужный сервис
│   │   │   ├── models.py          # Pydantic схемы для всех намерений
│   │   │   └── prompts.py         # system prompts
│   │   └── integrations/
│   │       ├── __init__.py
│   │       ├── base.py            # абстрактные классы провайдеров
│   │       ├── registry.py        # IntegrationRegistry
│   │       └── google/
│   │           ├── __init__.py
│   │           ├── calendar.py    # GoogleCalendarProvider
│   │           └── auth.py        # OAuth2 flow
│   ├── keyboards/
│   │   ├── __init__.py
│   │   ├── tasks.py               # inline клавиатуры для задач
│   │   ├── calendar.py
│   │   └── settings.py
│   └── middlewares/
│       ├── __init__.py
│       ├── auth.py                # проверка whitelist
│       └── user.py                # инжект user объекта в handler
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_intent_parser.py
│   ├── test_tasks.py
│   └── test_briefing.py
├── deploy/
│   ├── nginx.conf
│   └── certbot-init.sh
├── .github/
│   └── workflows/
│       └── ci.yml
├── docker-compose.yml             # продакшен
├── docker-compose.dev.yml         # локальная разработка (только БД)
├── Dockerfile
├── pyproject.toml
├── uv.lock
├── .python-version
├── .env.example
└── .gitignore
```

---

## Слои архитектуры

### 1. Handlers (aiogram роутеры)
Принимают Telegram updates, валидируют входные данные, вызывают сервисы, формируют ответ.
Не содержат бизнес-логику — только оркестрацию.

### 2. Services (бизнес-логика)
Реализуют логику приложения. Не знают про Telegram — работают с доменными объектами.
Вызывают репозитории для работы с БД и провайдеры интеграций.

### 3. Repositories (data access)
Инкапсулируют все SQL запросы. Сервисы не пишут SQL напрямую.
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
├── position (порядок отображения)
└── created_at

tasks
├── id
├── list_id → task_lists.id
├── user_id → users.id
├── title
├── priority (low/medium/high)
├── due_date
├── completed_at
└── created_at

task_events
├── id
├── task_id → tasks.id
├── user_id → users.id
├── event_type (created/completed/postponed/deleted/updated)
└── occurred_at

reminders
├── id
├── user_id → users.id
├── title
├── remind_at
├── repeat (none/daily/weekly/monthly)
├── is_sent
└── created_at

calendar_events
├── id
├── user_id → users.id
├── external_id (Google Calendar event id)
├── title
├── starts_at
├── ends_at
├── reminder_minutes
└── created_at

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

---

## Intent парсинг

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
    IntentRouter.route(parsed_response, user)
           │
           ├── confidence < 0.8 → показать подтверждение
           ├── clarification_needed → задать вопрос
           ├── destructive action → показать подтверждение
           └── иначе → выполнить, показать результат
```

### Pydantic схемы намерений

```python
# Дискриминированный union по полю type
ParsedIntent = Annotated[
    CreateTaskIntent
    | CreateEventIntent
    | CreateReminderIntent
    | ListTasksIntent
    | CompleteTaskIntent
    | DeleteTaskIntent
    | UpdateTaskIntent
    | GetBriefingIntent
    | GetAnalyticsIntent
    | AIChatIntent,
    Field(discriminator="type")
]

class ParsedResponse(BaseModel):
    intents: list[ParsedIntent]
    confidence: float           # 0.0 - 1.0
    clarification_needed: str | None
```

---

## Интеграции (Provider pattern)

```python
# base.py
class CalendarProvider(ABC):
    @abstractmethod
    async def create_event(self, user_id: int, event: CalendarEventDTO) -> str: ...

    @abstractmethod
    async def list_events(self, user_id: int, date_from: date, date_to: date) -> list[CalendarEventDTO]: ...

    @abstractmethod
    async def delete_event(self, user_id: int, event_id: str) -> None: ...

    @abstractmethod
    async def update_event(self, user_id: int, event_id: str, event: CalendarEventDTO) -> None: ...

# registry.py
class IntegrationRegistry:
    def get_calendar(self, provider_name: str) -> CalendarProvider: ...
    def register_calendar(self, name: str, provider: CalendarProvider) -> None: ...
```

Добавление новой интеграции:
1. Создать `services/integrations/notion/calendar.py` с классом `NotionCalendarProvider(CalendarProvider)`
2. Зарегистрировать в `registry.register_calendar("notion", NotionCalendarProvider())`
3. Добавить OAuth flow если нужно

---

## Автоматические рассылки (APScheduler)

```python
# scheduler.py — jobs при старте бота
scheduler.add_job(send_morning_briefings, "cron", hour=0, minute=0)  # каждый час проверяем у кого сейчас время брифинга
scheduler.add_job(send_weekly_summary, "cron", day_of_week="sun", hour=20, minute=0)
scheduler.add_job(check_reminders, "interval", minutes=1)
```

`send_morning_briefings` — проходит по всем активным пользователям, у кого `briefing_time` совпадает с текущим временем в их часовом поясе → отправляет брифинг.

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

## Локальная разработка

```bash
# 1. Поднять только БД
docker compose -f docker-compose.dev.yml up -d

# 2. Установить зависимости
uv sync

# 3. Скопировать и заполнить .env
cp .env.example .env

# 4. Запустить бота (polling режим)
uv run python -m bot.main
```

В `.env` переменная `ENVIRONMENT=local` переключает бота в polling режим.
Google Calendar не работает локально (нет домена для OAuth callback).

---

## Безопасность

- **Whitelist:** middleware проверяет каждый update, неизвестные user_id получают отказ
- **Webhook secret:** Telegram подписывает запросы, aiogram проверяет подпись
- **Секреты:** только в `.env` на VPS и GitHub Secrets, в репозиторий не попадают
- **Google токены:** шифруются Fernet (`ENCRYPTION_KEY` в `.env`) перед записью в БД
- **Сеть:** PostgreSQL и бот не доступны снаружи Docker сети, только nginx торчит на 80/443
- **UFW:** открыты порты 22, 80, 443
- **gitleaks:** сканирует коммиты на случайно закоммиченные секреты
