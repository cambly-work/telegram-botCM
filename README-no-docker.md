# Запуск без Docker с Cloudflare Tunnel

Этот гайд описывает развертывание бота **без Docker** напрямую на хостовой системе
с использованием [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/) для публикации публичного HTTPS-адреса.
Инструкция подходит для VPS или bare-metal сервера, где нет возможности использовать
Docker или платный аккаунт ngrok.

## Предварительные требования

- Linux-сервер c Python 3.10+
- Доступ к PostgreSQL 13+ (локально или управляемый сервис)
- Аккаунт Cloudflare и установленный `cloudflared` (можно через `apt`, `brew`, `curl`)
- Опционально: установленный `ngrok` для локальной отладки

## 1. Подготовка приложения

1. **Клонируйте репозиторий и установите зависимости**:

   ```bash
   git clone https://github.com/<your-org>/telegram-botCM.git
   cd telegram-botCM

   python -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. **Создайте и заполните `.env`** на основе примера:

   ```bash
   cp .env.example .env
   ```

   Обязательно укажите значения:

   - `BOT_TOKEN` — токен вашего бота
   - `WEBHOOK_SECRET` — секрет для управления вебхуками
   - `ADMIN_IDS` — список Telegram ID администраторов
   - `PUBLIC_BASE_URL=cloudflared` — используем cloudflared как источник публичного URL
   - `CLOUDFLARED_AUTOFETCH=1`
   - `CLOUDFLARED_METRICS_URL=http://127.0.0.1:49999/metrics`

   Настройте `DB_DSN` на подключение к вашей PostgreSQL, например:

   ```dotenv
   DB_DSN=postgresql+asyncpg://user:password@localhost:5432/telegram_bot
   ```

3. **Подготовьте базу данных**: выполните `schema.sql` или миграции в соответствии
   с вашей стратегией деплоя. Минимально достаточно применить `schema.sql`:

   ```bash
   psql "${DB_DSN//+asyncpg/}" -f schema.sql
   ```

4. **Запустите приложение** (после активации виртуального окружения):

   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000
   ```

   Убедитесь, что эндпоинт здоровья отвечает:

   ```bash
   curl http://127.0.0.1:8000/health
   ```

## 2. Настройка Cloudflare Tunnel

1. **Аутентифицируйтесь в Cloudflare** (при первом запуске):

   ```bash
   cloudflared tunnel login
   ```

2. **Запустите туннель** в режиме быстрого старта, пробрасывая локальный `uvicorn`:

   ```bash
   cloudflared tunnel --url http://127.0.0.1:8000 --metrics 127.0.0.1:49999
   ```

   Cloudflare выдаст публичный URL вида `https://<hash>.trycloudflare.com`. Приложение автоматически
   подтянет адрес из метрик `cloudflared` (по URL из `CLOUDFLARED_METRICS_URL`) и обновит вебхук Telegram.

3. **Оставьте туннель работающим**: можно запустить в `tmux`, `screen` или настроить systemd-сервис.
   Пример unit-файла (`/etc/systemd/system/cloudflared-bot.service`):

   ```ini
   [Unit]
   Description=Cloudflare Tunnel for telegram-botCM
   After=network.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/path/to/telegram-botCM
   ExecStart=/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:8000 --metrics 127.0.0.1:49999
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

   После создания unit-файла выполните:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now cloudflared-bot
   ```

4. **Проверьте вебхук Telegram**: убедитесь, что в логах `uvicorn` появился запрос `setWebhook`, либо выполните:

   ```bash
   curl -H "X-Telegram-Bot-Api-Secret-Token: $WEBHOOK_SECRET" \
        "https://api.telegram.org/bot$BOT_TOKEN/getWebhookInfo"
   ```

   В ответе поле `url` должно совпадать с доменом Cloudflare.

## 3. Переключение на ngrok (опционально)

Если требуется временно использовать ngrok (например, для локальной отладки на ноутбуке):

1. Установите и запустите `ngrok`:

   ```bash
   ngrok http 8000
   ```

2. Обновите `.env`:

   ```dotenv
   PUBLIC_BASE_URL=ngrok
   NGROK_AUTOFETCH=1
   NGROK_API_URL=http://127.0.0.1:4040/api/tunnels
   ```

3. Перезапустите приложение, чтобы оно заново подтянуло URL из ngrok API.

## 4. Частые проблемы

| Симптом | Решение |
| ------- | ------- |
| Cloudflare не выдаёт URL | Проверьте авторизацию `cloudflared tunnel login` и наличие активной зоны в аккаунте Cloudflare |
| Бот не получает апдейты | Убедитесь, что `PUBLIC_BASE_URL` в `.env` установлен на `cloudflared`, запущен туннель и в логах нет ошибок HTTPS |
| Автообновление URL не работает | Проверьте корректность `CLOUDFLARED_METRICS_URL` и доступность `http://127.0.0.1:49999/metrics` |
| Ошибки подключения к БД | Убедитесь, что `DB_DSN` указывает на существующую базу и пользователь имеет нужные права |

После настройки система готова к эксплуатации без Docker: бот запускается как сервис Python,
а Cloudflare Tunnel обеспечивает внешний доступ без дополнительных расходов.
