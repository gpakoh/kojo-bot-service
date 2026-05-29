# Kojo — Deployment Runbook

## 1. Назначение документа

Документ описывает эксплуатационные процедуры для Kojo-сервиса:

- как развернуть Kojo с нуля;
- как обновить работающую инсталляцию;
- как выполнить откат при проблемах;
- что проверить после деплоя.

Документ рассчитан на администратора с доступом к серверу, Docker и репозиторию.

## 2. Предварительные требования

- доступ к Gitea-репозиторию (`git.xloud.ru/gpakoh/kojo-bot-service`);
- Docker и docker-compose-plugin установлены на целевой машине;
- PostgreSQL 15 — контейнер или внешний инстанс;
- Redis 7 — контейнер или внешний инстанс;
- доступ к файлу `.env` с реальными токенами и паролями;
- backup storage доступен для pre-deploy дампа;
- актуальный release tag известен (см. `git tag -l`).

## 3. Основные репозитории

- Gitea (`git.xloud.ru/gpakoh/kojo-bot-service`) — primary репозиторий, CI через Gitea Actions, все изменения через PR
- GitHub (`github.com/gpakoh/kojo-bot-service`) — mirror/backup, синхронизируется после каждого merge
- Ветка `main` защищена: прямой push запрещён, force push запрещён, обязателен проход CI
- Рабочий процесс: feature-ветка → PR → merge в main → mirror sync

## 4. Обязательные переменные окружения

Все переменные задаются в файле `.env` в корне проекта. Полный перечень с описанием окружений (local/staging/production) — в [docs/ENVIRONMENTS.md](ENVIRONMENTS.md). Пример — `.env.example`.

Обязательные:

- `BOT_TOKEN` — токен Telegram-бота от BotFather
- `DATABASE_URL` — строка подключения к PostgreSQL (`postgresql://user:password@host:port/dbname`)
- `QUART_SERVER_URL` — URL Quart API-сервера
- `INTEGRATION_SERVER_URL` — URL сервера интеграций
- `BOT_ID_FOR_QUART` — идентификатор бота для Quart
- `ADMIN_CHAT_ID` — Telegram ID администратора
- `ADMIN_IDS` — список ID администраторов через запятую

Опциональные (с значениями по умолчанию):

- `REDIS_URL` — строка подключения к Redis (`redis://127.0.0.1:6379/0`)
- `BOT_INTERNAL_PORT` — порт HTTP health-сервера (8080)
- `LOG_LEVEL` — уровень логирования (INFO)
- `WEBHOOK_PUBLIC_URL` — публичный URL вебхука (пусто — polling mode)
- `WEBHOOK_SECRET_TOKEN` — секрет вебхука (пусто)
- `TG_PROXY_URL` — URL прокси для Telegram API (пусто)
- `USE_PROXY` — использовать прокси (false)
- `WELCOME_MESSAGE` — приветственное сообщение

Все значения указываются только placeholder. Реальные токены и пароли хранятся вне репозитория.

## 5. Первый деплой

Шаги для развёртывания Kojo с нуля:

- клонировать репозиторий: `git clone https://git.xloud.ru/gpakoh/kojo-bot-service && cd kojo-bot-service`
- переключиться на актуальный release tag: `git checkout v0.1.1`
- скопировать файл `.env.example` в `.env`: `cp .env.example .env`
- заполнить `.env` реальными значениями (токен, пароли БД, URL)
- проверить конфигурацию compose: `docker compose -f docker/docker-compose.yml config`
- запустить PostgreSQL: `docker compose -f docker/docker-compose.yml up -d RAG_kojo-db`
- дождаться готовности БД: `docker compose exec RAG_kojo-db pg_isready -U kojo_user -d kojo_db`
- применить миграции: `docker compose run --rm RAG_kojo_bot alembic upgrade head`
- собрать образ: `docker compose build RAG_kojo_bot`
- запустить Kojo: `docker compose -f docker/docker-compose.yml up -d RAG_kojo_bot`
- проверить логи: `docker compose logs -f RAG_kojo_bot`

Если используется Redis (опционально), запустить до старта бота: `docker compose -f docker/docker-compose.local.yml up -d RAG_kojo-redis`.

## 6. Обновление версии

Штатное обновление между release tag-ами:

- убедиться, что CI на целевом PR/коммите зелёный
- сделать backup БД (см. docs/DB_BACKUP_RESTORE.md)
- скачать новые теги: `git fetch --tags`
- переключиться на новый тег: `git checkout v0.X.Y`
- пересобрать образ: `docker compose build RAG_kojo_bot`
- применить новые миграции: `docker compose run --rm RAG_kojo_bot alembic upgrade head`
- перезапустить сервис: `docker compose up -d RAG_kojo_bot`
- проверить логи: `docker compose logs -f RAG_kojo_bot`
- проверить health endpoint: `curl http://localhost:${BOT_INTERNAL_PORT:-8080}/health`

Если образ собирается заранее (CI-пайплайн), можно пропустить локальную сборку и использовать `compose build --pull`.

## 7. Rollback

Когда требуется откат: новая версия не стартует, health check не проходит, миграция сломала данные, обнаружена критическая ошибка.

Процедура:

- переключиться на предыдущий tag: `git checkout v0.X.Y`
- пересобрать образ: `docker compose build RAG_kojo_bot`
- перезапустить: `docker compose up -d RAG_kojo_bot`
- проверить health check: `curl http://localhost:${BOT_INTERNAL_PORT:-8080}/health`

Если откат включает даунгрейд миграций — восстановить БД из backup (см. docs/DB_BACKUP_RESTORE.md).

Alembic умеет откатывать одну миграцию: `docker compose run --rm RAG_kojo_bot alembic downgrade -1`. Но если данных много — надёжнее полный restore из backup.

## 8. Health checks после деплоя

После любого деплоя проверить:

- контейнеры запущены: `docker compose ps` — все сервисы в статусе `Up`
- БД доступна: `docker compose exec RAG_kojo-db pg_isready -U kojo_user`
- Redis доступен (если используется): `docker compose exec RAG_kojo-redis redis-cli ping` — должен ответить `PONG`
- health endpoint отвечает: `curl -f http://localhost:${BOT_INTERNAL_PORT:-8080}/health` — статус 200
- readiness endpoint отвечает: `curl -f http://localhost:${BOT_INTERNAL_PORT:-8080}/ready` — статус 200
- метрики отдаются: `curl http://localhost:${BOT_INTERNAL_PORT:-8080}/metrics` — Prometheus-формат
- логи без ошибок: `docker compose logs RAG_kojo_bot --tail 50` — нет `ERROR`, `CRITICAL`, `Traceback`
- миграции применены: `docker compose exec RAG_kojo-db psql -U kojo_user kojo_db -c "SELECT version_num FROM alembic_version"` — последняя версия
- Telegram polling работает: в логах видно `update_id`, сообщения от бота приходят

## 9. Логи

Основные команды для просмотра логов:

- `docker compose logs -f RAG_kojo_bot` — потоковые логи бота
- `docker compose logs -f RAG_kojo-db` — потоковые логи PostgreSQL
- `docker compose logs --tail 100 RAG_kojo_bot` — последние 100 строк
- `docker compose ps` — статус всех контейнеров
- `docker compose logs --no-color RAG_kojo_bot 2>&1 | grep -i error` — только ошибки

Если сервис запущен не через compose, а через systemd: `journalctl -u kojo-bot -f`.

Не выводить логи с токенами, паролями и другими секретами. Health-сервер не логирует секреты.

## 10. Backup перед деплоем

Перед каждым деплоем выполнить backup PostgreSQL.

Процедура описана в отдельном документе: [docs/DB_BACKUP_RESTORE.md](DB_BACKUP_RESTORE.md).

**Рекомендованный способ — скрипт `scripts/backup_db.sh`:**

```bash
KOJO_DATABASE_URL="postgresql://user:pass@host:5432/db" BACKUP_DIR=/var/backups/kojo \
  ./scripts/backup_db.sh
```

**Через docker compose (альтернатива):**

```bash
cd docker
docker compose exec RAG_kojo-db pg_dump -U kojo_user -Fc kojo_db > /var/backups/kojo/kojo_db_$(date +%Y%m%d_%H%M%S).dump
```

Redis-backup не требуется — данные Redis восстанавливаются автоматически.

## 11. Частые проблемы

- **Отсутствует `.env`** — бот не стартует с ошибкой `KeyError: 'BOT_TOKEN'`. Решение: скопировать `.env.example` и заполнить.
- **Неверный BOT_TOKEN** — Telegram API отвечает `401 Unauthorized`. Решение: проверить токен в BotFather, обновить `.env`.
- **DATABASE_URL недоступен** — бот падает при старте с `connection refused`. Решение: проверить, что PostgreSQL запущен и доступен по указанному адресу/порту.
- **Redis недоступен** — бот стартует, но с warning `Redis unavailable, using in-memory fallback`. Решение: проверить `redis-cli ping`, запустить контейнер Redis.
- **alembic migration failed** — ошибка применения миграций. Решение: проверить последовательность версий, выполнить `alembic downgrade -1`, исправить, повторить.
- **docker network conflict** — `network already exists` или `overlay network not found`. Решение: `docker network prune` или `docker compose down && docker compose up`.
- **GitHub mirror не синхронизирован** — зеркало отстаёт от Gitea. Решение: выполнить explicit SHA push: `git push github $(git rev-parse HEAD):main`.
- **CI не прошёл** — мерж заблокирован branch protection. Решение: исправить ошибки в новой ветке, дождаться зелёного CI, обновить PR.

## 12. Release checklist

Перед выпуском каждого релиза:

- PR замёрджен в main
- CI на merge commit зелёный
- release tag создан: `git tag -a v0.X.Y -m "v0.X.Y"` и запушен в Gitea и GitHub
- GitHub mirror синхронизирован: `git push github v0.X.Y`
- backup БД сделан перед деплоем
- миграции проверены на staging (alembic upgrade head)
- rollback tag известен (предыдущий v0.X.Y)
- deploy выполнен по процедуре раздела 6
- health check пройден (раздел 8)
- ошибок в логах нет
- Telegram-бот отвечает на сообщения

## Ссылки

- [docs/ENVIRONMENTS.md](ENVIRONMENTS.md) — матрица окружений local/staging/production
- [docs/DB_BACKUP_RESTORE.md](DB_BACKUP_RESTORE.md) — backup/restore БД
- [docs/DEVELOPMENT_FLOW.md](DEVELOPMENT_FLOW.md) — процесс разработки и CI
- [docs/DOCKER_BOOTSTRAP.md](DOCKER_BOOTSTRAP.md) — сборка Docker-образа
- [docs/RELEASES.md](RELEASES.md) — история релизов
- [deploy/CHECKLIST.md](../deploy/CHECKLIST.md) — pre/post-deploy проверки
- [deploy/RUNBOOKS.md](../deploy/RUNBOOKS.md) — операционные runbook'и
