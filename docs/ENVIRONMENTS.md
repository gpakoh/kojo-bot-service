# Kojo — Environment Matrix

## 1. Назначение

Документ формализует окружения Kojo-сервиса:

- какие переменные окружения используются;
- как различаются local, staging, production;
- какие значения обязательны;
- какие секреты нельзя коммитить.

Окружения различаются тремя вещами: токены Telegram-бота, БД, Redis. Каждое окружение должно использовать свои экземпляры. Использование production-токена на staging недопустимо.

## 2. Поддерживаемые окружения

- **local** — разработка на машине разработчика
- **staging** — тестовый сервер для проверки миграций и smoke-тестов
- **production** — рабочий сервер с реальными данными

## 3. Общие правила

- реальные `.env` файлы не коммитятся — они в `.gitignore`
- секреты хранятся вне репозитория: в Gitea Secrets, на сервере, в secret storage
- `.env.example` содержит только placeholders, никогда — реальные значения
- production и staging должны использовать разные БД, Redis и BOT_TOKEN
- backup БД обязателен перед любым upgrade production
- переменные с паролями и токенами не выводятся в логи

## 4. Local

- используется для разработки и отладки
- допустимы тестовые или отладочные токены Telegram
- БД — локальный PostgreSQL (через docker compose или system PostgreSQL)
- Redis — локальный (через docker compose.local.yml)
- LOG_LEVEL рекомендуется DEBUG или INFO
- допускается прямое подключение к БД без docker compose
- backup не требуется

## 5. Staging

- отдельный staging-бот (создаётся через BotFather с тестовым токеном)
- отдельная staging БД (не должна содержать реальных данных)
- отдельный Redis
- тестовые ключи для карт, доставки, платежей
- LOG_LEVEL — INFO или DEBUG
- используется для проверки миграций, smoke-тестов и pre-production деплоя
- рекомендуется настроить backup с retention 7 дней

## 6. Production

- production BOT_TOKEN (основной бот)
- production БД с реальными данными
- production Redis
- боевые ключи для карт, доставки, платежей
- LOG_LEVEL — INFO или WARNING (не DEBUG)
- backup БД обязателен (ежедневно, retention 14 дней)
- мониторинг и alerting включены
- доступ к серверу ограничен
- используется docker-compose.yml (production compose)

## 7. Обязательные переменные

Эти переменные должны быть заданы в любом окружении. Без них сервис не стартует.

- `BOT_TOKEN` — токен Telegram-бота от BotFather
- `DATABASE_URL` — строка подключения к PostgreSQL
- `QUART_SERVER_URL` — URL Quart API-сервера
- `INTEGRATION_SERVER_URL` — URL сервера интеграций
- `BOT_ID_FOR_QUART` — идентификатор бота для Quart
- `ADMIN_CHAT_ID` — Telegram ID администратора для алертов

## 8. Опциональные переменные

Переменные с значениями по умолчанию. Могут быть не заданы.

**Подключения:**

- `REDIS_URL` — Redis (по умолчанию `redis://localhost:6379/0`)
- `KOJO_DATABASE_URL` — альтернативный URL БД для backup-скрипта (приоритет выше DATABASE_URL)
- `KOJO_REDIS_URL` — зарезервировано для явного указания Redis URL

**Telegram и proxy:**

- `WEBHOOK_PUBLIC_URL` — публичный URL для вебхука (пусто — polling mode)
- `WEBHOOK_SECRET_TOKEN` — секрет вебхука (пусто)
- `TG_PROXY_URL` — URL прокси для Telegram API (пусто)
- `USE_PROXY` — использовать прокси (false)
- `HTTPS_PROXY` / `https_proxy` — устанавливается динамически из TG_PROXY_URL

**Бот:**

- `BOT_INTERNAL_PORT` — порт HTTP health-сервера (8080)
- `WELCOME_MESSAGE` — приветственное сообщение
- `ADMIN_IDS` — список ID администраторов через запятую (пусто)
- `RESET_PERSISTENCE` — сбросить persistence при старте (false)

**Логирование и observability:**

- `LOG_LEVEL` — уровень логирования (INFO)
- `ENABLE_METRICS` — включить Prometheus-метрики (true)
- `ENABLE_TRACING` — включить Jaeger-трассировку (true)
- `APP_VERSION` — версия приложения для метрик ('unknown')
- `TENANT_BOT_ID` — tenant ID для мультитенантности ('default')
- `JAEGER_ENDPOINT` — endpoint Jaeger-агента (пусто — трассировка отключена)

**Пул подключений к БД:**

- `DB_POOL_MIN_SIZE` — минимальный размер пула (5)
- `DB_POOL_MAX_SIZE` — максимальный размер пула (20)
- `DB_COMMAND_TIMEOUT` — таймаут команды в секундах (10)
- `DB_POOL_MAX_INACTIVE_TIME` — максимальное время неактивности в секундах (300)
- `DB_CONNECTION_TIMEOUT` — таймаут подключения в секундах (30)
- `DB_MAX_RETRY_ATTEMPTS` — количество попыток переподключения (3)
- `DB_RETRY_BASE_DELAY` — задержка между попытками в секундах (1.0)

**Кеш:**

- `CACHE_DEFAULT_TTL` — TTL кеша по умолчанию в секундах (3600)
- `CIRCUIT_FAILURE_THRESHOLD` — порог срабатывания circuit breaker (5)
- `CIRCUIT_RECOVERY_TIMEOUT` — таймаут восстановления circuit breaker (30)

**Мониторинг БД:**

- `SLOW_QUERY_THRESHOLD_MS` — порог медленного запроса в миллисекундах (100)
- `QUERY_MONITORING` — включить мониторинг запросов (true)
- `LOG_ALL_QUERIES` — логировать все запросы (false)

**Доставка:**

- `WEBAPP_MAP_URL` — URL карты для отслеживания доставки
- `YANDEX_MAPS_API_KEY` — API-ключ Яндекс.Карт
- `DEFAULT_WEIGHT_GRAMS` — вес заказа по умолчанию в граммах (500)
- `ORDER_ASSEMBLY_DAYS` — дней на сборку заказа (2)

**Пул прокси:**

- `PROXY_POOL` — список прокси через запятую
- `PROXY_POOL_2` — запасной список прокси
- `PROXY_POOL_3` — ещё один запасной список
- `PROXY_COOLDOWN_SECONDS` — время остывания прокси (300)
- `PROXY_HEALTH_CHECK_INTERVAL` — интервал проверки здоровья прокси (60)

**Backup:**

- `BACKUP_DIR` — директория для backup (./backups)
- `RETENTION_DAYS` — срок хранения backup в днях (14)

**Tenant:**

- `{BOT_ID}_DATABASE_URL` — URL БД для конкретного tenant
- `{BOT_ID}_ADMIN_IDS` — ID администраторов для tenant
- `TENANT_TO_MIGRATE` — tenant для миграции (опционально)

## 9. Секреты

Следующие переменные содержат конфиденциальные данные. Они никогда не должны попадать в репозиторий, выводиться в логи или логи CI.

- `BOT_TOKEN` — токен доступа к Telegram API
- `DATABASE_URL` — содержит пароль БД
- `REDIS_URL` — содержит пароль Redis (если используется)
- `WEBHOOK_SECRET_TOKEN` — секрет вебхука
- `TG_PROXY_URL` — может содержать логин/пароль прокси
- `PROXY_POOL*` — IP-адреса внутренних прокси
- `YANDEX_MAPS_API_KEY` — API-ключ Яндекс
- `WEBAPP_MAP_URL` — может содержать внутренние URL
- `{BOT_ID}_DATABASE_URL` — пароль tenant-БД

## 10. Environment promotion checklist

**Local → Staging:**

- тесты проходят: `pytest -q`
- миграции применяются локально: `alembic upgrade head`
- docker compose config проходит проверку
- env-файл staging заполнен корректными значениями

**Staging → Production:**

- CI на merge commit зелёный
- release tag создан: `git tag -a v0.X.Y`
- backup БД сделан перед деплоем
- staging smoke-test пройден
- rollback tag известен (предыдущий v0.X.Y)
- production deploy утверждён

## 11. Примеры placeholders

```
BOT_TOKEN=<telegram-bot-token>
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>:5432/<db>
QUART_SERVER_URL=http://<quart-host>:5000
INTEGRATION_SERVER_URL=http://<integration-host>:5000
BOT_ID_FOR_QUART=kojo
ADMIN_CHAT_ID=<telegram-id>
ADMIN_IDS=<telegram-id>,<telegram-id>

REDIS_URL=redis://<host>:6379/0
BOT_INTERNAL_PORT=8080
LOG_LEVEL=INFO
WEBHOOK_PUBLIC_URL=
WEBHOOK_SECRET_TOKEN=
TG_PROXY_URL=
USE_PROXY=false
WELCOME_MESSAGE=Добро пожаловать!
ENVIRONMENT=staging

# Backup
BACKUP_DIR=/var/backups/kojo
RETENTION_DAYS=14
```

## Ссылки

- `.env.example` — пример для локальной разработки
- `docker/.env.example` — пример для Docker-деплоя
- `docs/DEPLOYMENT_RUNBOOK.md` — процедура деплоя
- `docs/DB_BACKUP_RESTORE.md` — backup/restore
