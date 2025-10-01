# CODE: Magnetism Telegram Bot

Этот репозиторий содержит Telegram-бота и вспомогательный REST API, написанный на FastAPI и aiogram. Проект готов к деплою «из коробки» в Docker вместе с PostgreSQL.

## Структура

- `app.py` — основной FastAPI/aiogram-приложение.
- `db.py`, `schema.sql` — инициализация и утилиты работы с PostgreSQL.
- `handlers.py`, `keyboards.py`, `scheduler.py` — логика бота, клавиатуры и планировщик.
- `docker-compose.yml` — оркестрация Docker-сервисов (бот + PostgreSQL).
- `Dockerfile` — образ приложения.
- `.env.example` — пример файла окружения.
- `.dockerignore` — исключения из контекста сборки.

## Быстрый старт в Docker

1. **Склонируйте репозиторий на сервер:**

   ```bash
   git clone https://github.com/<your-org>/telegram-botCM.git
   cd telegram-botCM
   ```

2. **Создайте файл окружения:**

   ```bash
   cp .env.example .env
   ```

   Обязательно укажите боевой `BOT_TOKEN`, `PUBLIC_BASE_URL`, `WEBHOOK_SECRET`, идентификаторы администраторов и другие значения.

3. **Запустите сервисы:**

   ```bash
   docker compose up -d --build
   ```

   По умолчанию FastAPI доступен на `http://localhost:8000`, Postgres — во внутренней сети Compose.

4. **Проверьте работоспособность:**

   ```bash
   curl http://localhost:8000/health
   ```

   Ожидаемый ответ — JSON со статусом `ok`.

## Переменные окружения

| Переменная | Назначение |
| ---------- | ---------- |
| `BOT_TOKEN` | Токен Telegram-бота |
| `ADMIN_IDS` | CSV-список Telegram ID администраторов |
| `PUBLIC_BASE_URL` | Публичный URL, по которому Telegram обращается к вебхуку |
| `WEBHOOK_SECRET` | Секрет для ручного управления вебхуком и админ-эндпоинтов |
| `NGROK_AUTOFETCH` | Если `1/true` — автоматически подтянуть `PUBLIC_BASE_URL` из ngrok |
| `NGROK_API_URL` | Endpoint ngrok, возвращающий список туннелей (например, `http://ngrok:4040/api/tunnels`) |
| `NGROK_API_TOKEN` | Токен API ngrok (нужен для облачного API `https://api.ngrok.com`) |
| `NGROK_TUNNEL_NAME` | Фильтр по имени/URL туннеля ngrok, если их несколько |
| `DB_DSN` | Строка подключения к PostgreSQL (для Docker — `postgres`) |
| `BOT_TIMEZONE` | Таймзона планировщика уроков |
| `TIME_SEND_LESSONS` | Локальное время запуска рассылки уроков |
| `WELCOME_POST_URL` | Ссылка на приветственный пост клуба |
| `TEST_FORM_URL` | Ссылка на тест для определения уровня |
| `SUPPORT_CONTACT` | Контакт службы поддержки |
| `CLUB_CHAT_ID` | Числовой chat_id клубного чата (бот должен быть админом) |
| `AT_WEBHOOK_SHARED_SECRET` | Секрет для вебхуков Anti-training (опционально) |
| `YOOMONEY_CHECKOUT_URL` | Ссылка на страницу оплаты YooMoney |
| `YOOMONEY_WEBHOOK_SECRET` | Секрет для подписи вебхука YooMoney |

## Разработка без Docker

1. Установите зависимости:

   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Поднимите PostgreSQL локально или используйте Docker-контейнер.
3. Настройте `.env` (см. пример).
4. Запустите приложение:

   ```bash
   uvicorn app:app --reload
   ```

## Тестирование

Для запуска юнит-тестов установите `PYTHONPATH` и выполните:

```bash
PYTHONPATH=. pytest
```

## Ручное применение миграции напоминаний

Для продакшн-базы важно убедиться, что у таблицы `form_sessions` есть поля
`last_reminder_at` и `reminder_count`. Их добавляет скрипт
`migrations/20240703_form_sessions_form_slug.sql`. Минимальный набор команд для
ручного прогона:

```sql
ALTER TABLE form_sessions
    ADD COLUMN IF NOT EXISTS last_reminder_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reminder_count INT DEFAULT 0;

UPDATE form_sessions
SET reminder_count = COALESCE(reminder_count, 0);
```

Проверить наличие колонок можно запросом:

```sql
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'form_sessions';
```

## Прогресс уроков и ручная корректировка

Статусы обучения сохраняются в двух таблицах:

- `funnel_progress` — фиксирует выдачу уроков, статус домашнего задания (`submitted`, `pending`, `skipped`) и текст ответа.
- `lesson_feedback` — хранит обратную связь по урокам и используется как признак завершения, если статуса в `funnel_progress` нет (например, после импорта).

Бот комбинирует обе таблицы, чтобы построить блок «Мой прогресс»: статус урока определяется по `hw_status`, но при наличии отзывов урок также помечается завершённым. В профиле и в разделе обучения дополнительно отображается статус доступа (`Funnel`, `Member Active`, `Member Expired`) и дата окончания в формате `ДД.ММ.ГГГГ`.

### Админ-панель

- В карточке пользователя появилась кнопка «📈 Обновить прогресс». Формат строк для ручной правки: `lesson=1 status=submitted feedback=excellent,good delivered=2024-08-01 reset=0`. Поддерживаются поля `lesson`, `status`, `feedback`, `delivered`, `opened`, `answer`, `reset`.

### Админский API

- `GET /admin/progress?secret=...&user_id=123` — возвращает текущий прогресс (уроки, статусы, отзывы).
- `POST /admin/progress/sync?secret=...` — принимает JSON с массивом `lessons` и синхронизирует статусы. Пустой `feedback` очищает отзывы, `reset=true` удаляет урок из истории. Поле `actor_id` логирует действие в `admin_log`.

Подробнее структура описана в [`docs/progress_data.md`](docs/progress_data.md).

## Обновление и деплой

```bash
git pull
docker compose pull
docker compose up -d --build
```

Docker перезапустит сервисы с обновлённым кодом. Логи приложения доступны через `docker compose logs -f bot`.

## Настройка YooMoney

- Укажите `YOOMONEY_CHECKOUT_URL` в `.env`, чтобы раздел оплаты в боте показывал актуальную ссылку на форму YooMoney.
- Секрет `YOOMONEY_WEBHOOK_SECRET` (если задан) используется для проверки подписи вебхука. YooMoney должна отправлять заголовок `X-YooMoney-Signature` с HMAC-SHA256 тела запроса.
- Адрес обработчика: `POST <PUBLIC_BASE_URL>/webhooks/yoomoney`. Убедитесь, что в личном кабинете YooMoney настроен этот URL.
- После успешной оплаты бот активирует доступ пользователю, отправляет подтверждение и уведомляет администраторов. При отказе платежа доступ блокируется и админы получают предупреждение.

## Управление окном оплаты и текстами раздела «Пройти тест»

- Статус «Окно оплаты открыто/закрыто» хранится в записи `settings.payments_open` таблицы `content`. Бот сначала читает это значение из базы, а при отсутствии — использует дефолт из `content.yaml` (`true`). Если в БД лежит `false`, бот показывает кнопку «🔒 Оплата» и текст о закрытом окне.【F:handlers.py†L646-L690】【F:handlers.py†L1875-L1894】
- Переключить статус можно в админке: `⚙️ Админка → 💳 Оплаты → 🔓 Открыть окно оплат/🔒 Закрыть окно оплат`. Кнопка вызывает `set_bool_setting("payments_open", ...)`, которое обновляет запись в таблице `content` и сразу сбрасывает кеш — перезапуск бота не требуется.【F:handlers.py†L5620-L5628】【F:handlers.py†L688-L715】
- Тексты цепочки «Пройти тест» читаются через ключи `menu.test`, `menu.test_intro`, `menu.test_birthdate_prompt`, `menu.test_birthdate_invalid`, `menu.test_name_prompt`, `menu.test_name_invalid`, `menu.test_thanks`. Для каждого ключа бот сначала пытается найти значение в таблице `content`, и только если его нет — берёт fallback из `content.yaml`. Поэтому, чтобы отображался текст, сохранённый через админку, убедитесь, что запись с нужным `key` есть в таблице `content` (её можно добавить/отредактировать через раздел «Контент» админки).【F:handlers.py†L646-L689】【F:handlers.py†L2110-L2144】【F:handlers.py†L3783-L3894】

## Резервное копирование данных

- Данные PostgreSQL хранятся в volume `postgres_data`.
- Для бэкапа используйте `docker run --rm --volumes-from code-magnetism-db postgres:15-alpine pg_dump -U magnet magnetism > backup.sql`.

