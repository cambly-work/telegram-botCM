# Развёртывание бота без Docker с PostgreSQL и ngrok

Данное руководство описывает развёртывание Telegram-бота на Linux-сервере без использования Docker. В сценарии предполагается, что база данных хранится в PostgreSQL на том же сервере, а публичный адрес для вебхуков Telegram проксируется через `ngrok`. Также приведены шаги по загрузке дампа базы с локального компьютера на сервер и его восстановлению.

## 1. Предварительные требования

- Сервер под управлением Ubuntu 22.04 LTS (или совместимого дистрибутива Debian).
- Права sudo на сервере.
- Установленный `ngrok`-аккаунт (для получения токена) и локальный файл дампа PostgreSQL (`.sql` или `.dump`).
- Токен Telegram-бота и остальные значения из `.env`.

## 2. Установка системных пакетов

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev \
    build-essential libpq-dev git postgresql postgresql-contrib
```

> При отсутствии Python 3.11 используйте доступную версию Python ≥ 3.10 и скорректируйте команды (`python3`/`pip3`).

## 3. Создание пользователя и подготовка окружения

```bash
sudo adduser --disabled-password --gecos "" botuser
sudo usermod -aG sudo botuser
sudo -iu botuser
```

С дальнейшими шагами работаем от имени `botuser`.

Создайте директорию для приложения и логов:

```bash
mkdir -p ~/apps/telegram-botCM
cd ~/apps
```

## 4. Клонирование репозитория и установка зависимостей

```bash
git clone https://github.com/<your-org>/telegram-botCM.git
cd telegram-botCM
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Скопируйте файл окружения и заполните обязательные параметры:

```bash
cp .env.example .env
nano .env
```

Минимальный набор переменных:

- `BOT_TOKEN`
- `WEBHOOK_SECRET`
- `PUBLIC_BASE_URL` (пока можно оставить пустым — значение добавим после запуска ngrok)
- `DB_DSN` вида `postgresql+asyncpg://bot_user:bot_password@127.0.0.1:5432/bot_db`
- `ADMIN_IDS`, `BOT_TIMEZONE` и другие параметры по необходимости.

## 5. Настройка PostgreSQL

Выполните следующие шаги под пользователем `postgres`:

```bash
sudo -iu postgres
createuser --interactive --pwprompt bot_user
createdb --owner=bot_user bot_db
exit
```

Проверьте подключение из-под `botuser`:

```bash
psql postgresql://bot_user@127.0.0.1:5432/bot_db
\q
```

## 6. Передача дампа с локальной машины

На локальном компьютере выполните команду для загрузки дампа на сервер (пример с `scp`):

```bash
scp /path/to/local/dump.dump botuser@your.server.ip:/home/botuser/backups/bot.dump
```

Альтернативно используйте `rsync` или SFTP-клиент. Убедитесь, что директория `~/backups` существует на сервере (`mkdir -p ~/backups`).

## 7. Восстановление дампа

Под пользователем `botuser` активируйте виртуальное окружение (если ещё не активировано) и выполните восстановление:

### 7.1. Дамп в формате `pg_dump` (custom/директория)

```bash
pg_restore --clean --no-owner \
    --dbname=postgresql://bot_user:bot_password@127.0.0.1:5432/bot_db \
    ~/backups/bot.dump
```

### 7.2. Плоский SQL-файл

```bash
psql postgresql://bot_user:bot_password@127.0.0.1:5432/bot_db \
    -f ~/backups/bot.sql
```

После восстановления при необходимости примените актуальные миграции из директории `migrations/` (например, если в дампе отсутствуют новые поля):

```bash
psql postgresql://bot_user:bot_password@127.0.0.1:5432/bot_db \
    -f migrations/20240703_form_sessions_form_slug.sql
```

## 8. Настройка ngrok

1. Скачайте и распакуйте ngrok:

   ```bash
   wget https://bin.equinox.io/c/4VmDzA7iaHb/ngrok-stable-linux-amd64.tgz
   tar -xzf ngrok-stable-linux-amd64.tgz
   sudo mv ngrok /usr/local/bin/
   ```

2. Авторизуйте клиент токеном из личного кабинета:

   ```bash
   ngrok config add-authtoken <NGROK_AUTHTOKEN>
   ```

3. Запустите туннель на нужный порт (FastAPI работает на `8000`):

   ```bash
   ngrok http 8000 --region=eu --log=stdout
   ```

   В выводе появится публичный HTTPS-URL вида `https://<random>.ngrok-free.app`. Скопируйте его и вставьте в `.env` в `PUBLIC_BASE_URL`.

4. Для автоматического запуска создайте systemd-юнит `~/services/ngrok.service` (см. пример ниже) или используйте `screen`/`tmux`.

## 9. Запуск приложения через uvicorn

Активируйте виртуальное окружение и запустите приложение вручную для проверки:

```bash
source ~/apps/telegram-botCM/.venv/bin/activate
cd ~/apps/telegram-botCM
uvicorn app:app --host 0.0.0.0 --port 8000
```

Проверьте здоровье приложения:

```bash
curl http://127.0.0.1:8000/health
```

В логах должен появиться запрос и статус `{"status": "ok"}`.

## 10. Настройка systemd (опционально)

Создайте файл `~/services/telegram-bot.service` со следующим содержимым:

```ini
[Unit]
Description=CODE:Magnetism Telegram Bot (uvicorn)
After=network.target postgresql.service
Requires=postgresql.service

[Service]
User=botuser
WorkingDirectory=/home/botuser/apps/telegram-botCM
Environment="PYTHONPATH=/home/botuser/apps/telegram-botCM"
EnvironmentFile=/home/botuser/apps/telegram-botCM/.env
ExecStart=/home/botuser/apps/telegram-botCM/.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Скопируйте файл в `/etc/systemd/system/` и активируйте сервис:

```bash
sudo cp ~/services/telegram-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-bot.service
```

Аналогично можно создать юнит `ngrok.service`:

```ini
[Unit]
Description=ngrok tunnel for Telegram webhook
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/local/bin/ngrok http 8000 --region=eu
Restart=on-failure
User=botuser
WorkingDirectory=/home/botuser

[Install]
WantedBy=multi-user.target
```

```bash
sudo cp ~/services/ngrok.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ngrok.service
```

После запуска сервисов проверьте статус:

```bash
sudo systemctl status telegram-bot.service
sudo systemctl status ngrok.service
```

## 11. Настройка вебхука Telegram

Как только `PUBLIC_BASE_URL` обновится на адрес из ngrok, перезапустите сервис бота. Приложение автоматически обновит вебхук (если включен автосброс). Также можно вызвать ручной endpoint:

```bash
curl -X POST "http://127.0.0.1:8000/api/admin/webhook/reset" \
    -H "X-Webhook-Secret: $WEBHOOK_SECRET"
```

Проверьте актуальный статус вебхука:

```bash
curl "http://127.0.0.1:8000/api/admin/webhook/info" \
    -H "X-Webhook-Secret: $WEBHOOK_SECRET"
```

## 12. Ротация логов и обновления

- Логи systemd доступны через `journalctl -u telegram-bot.service -f`.
- Для обновления приложения:
  ```bash
  cd ~/apps/telegram-botCM
  git pull
  source .venv/bin/activate
  pip install -r requirements.txt
  sudo systemctl restart telegram-bot.service
  ```
- Регулярно обновляйте дампы и храните их в безопасном месте.

Следуя этому руководству, вы сможете поднять бота на чистом сервере без Docker, обеспечить доступ Telegram через ngrok и восстановить состояние базы из локального дампа.
