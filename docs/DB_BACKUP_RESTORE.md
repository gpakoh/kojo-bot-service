# Kojo Database Backup & Restore Runbook

## Databases

| DB | Engine | Service | Persistence | Required |
|---|--------|---------|-------------|----------|
| PostgreSQL | Postgres 15 | `RAG_kojo-db` | Volume `kojo_kojo_postgres_data` | Да — основная БД |
| Redis 7 | Redis | `RAG_kojo-redis` | Только в памяти (non-persistent) | Нет — кеш/очереди |

Схема миграций управляется через Alembic (таблица `alembic_version`, 5 migrations).

## Backup

### Через docker compose (рекомендовано)

```bash
cd docker

# PostgreSQL — plain SQL (gzip)
docker compose exec RAG_kojo-db pg_dump -U kojo_user kojo_db | gzip > /var/backups/kojo/kojo_db_$(date +%Y%m%d_%H%M%S).sql.gz

# PostgreSQL — custom format (быстрее, можно pg_restore по частям)
docker compose exec RAG_kojo-db pg_dump -U kojo_user -Fc kojo_db > /var/backups/kojo/kojo_db_$(date +%Y%m%d_%H%M%S).dump

# PostgreSQL — только данные (без схемы)
docker compose exec RAG_kojo-db pg_dump -U kojo_user -a kojo_db | gzip > /var/backups/kojo/kojo_db_data_$(date +%Y%m%d_%H%M%S).sql.gz
```

Аргументы:
- `-Fc` — custom format (сжатый, поддерживает pg_restore `-j` параллельно, `-t` по таблицам)
- `-a` — только данные, без схемы (data-only)
- `-s` — только схема, без данных (schema-only)
- `--no-owner`, `--no-acl` — если восстанавливаете на другом инстансе с другим пользователем

### Через скрипт

```bash
# Установить переменные окружения или положить DATABASE_URL в .env
export PGHOST=127.0.0.1 PGPORT=5435 PGUSER=kojo_user PGPASSWORD=kojo_password PGDATABASE=kojo_db
./scripts/backup_postgres.sh /var/backups/kojo
```

Скрипт делает:
- custom-format dump (`pg_dump -Fc`)
- retention 7 дней (старые удаляются)
- lock-файл `/tmp/kojo_backup.lock` — защита от параллельных запусков

### Через cron

```bash
# ежедневно в 03:00
0 3 * * * /opt/kojo/scripts/backup_postgres.sh /var/backups/kojo >> /var/log/kojo_backup.log 2>&1
```

### Redis

Redis в Kojo используется как in-memory кеш (сессии, очереди сообщений). Персистентность не настроена. При `docker compose down` данные Redis теряются без последствий — кеш перестроится автоматически.

Если требуется сохранить состояние Redis перед остановкой:

```bash
docker compose exec RAG_kojo-redis redis-cli SAVE
```

Файл дампа будет внутри контейнера в `/data/dump.rdb`. Для резервного копирования:

```bash
docker compose cp RAG_kojo-redis:/data/dump.rdb /var/backups/kojo/redis_dump.rdb
```

## Restore

### Plain SQL (pg_dump без -Fc)

```bash
cd docker
gunzip -c /var/backups/kojo/kojo_db_20260528_030000.sql.gz | docker compose exec -T RAG_kojo-db psql -U kojo_user kojo_db
```

### Custom format (pg_dump -Fc)

```bash
cd docker
docker compose exec -T RAG_kojo-db pg_restore -U kojo_user -d kojo_db --clean /dev/stdin < /var/backups/kojo/kojo_db_20260528_030000.dump
```

`--clean` удаляет существующие объекты перед созданием.

### Частичное восстановление (одна таблица)

```bash
docker compose exec -T RAG_kojo-db pg_restore -U kojo_user -d kojo_db -t public.orders /dev/stdin < /path/to/dump.dump
```

### Полная пересборка

Если нужно пересоздать БД с нуля:

```bash
cd docker
docker compose down -v           # удалить volume (ОСТОРОЖНО)
docker compose up -d             # Postgres создаст fresh БД
docker compose exec RAG_kojo-db pg_restore -U kojo_user -d kojo_db < /path/to/dump.dump
```

## Проверка после restore

### 1. Alembic version

Убедиться, что версия миграции соответствует ожидаемой:

```bash
docker compose exec RAG_kojo-db psql -U kojo_user kojo_db -c "SELECT version_num FROM alembic_version"
```

Ожидаемый вывод: `version_num` из `alembic/versions/` (последняя миграция).

Если таблица пуста или отличается — прогонить миграции:

```bash
docker compose exec RAG_kojo_bot alembic upgrade head
```

### 2. Row counts (основные таблицы)

```bash
docker compose exec RAG_kojo-db psql -U kojo_user kojo_db -c "
SELECT schemaname, tablename, n_live_tup
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;
"
```

### 3. Целостность

```bash
docker compose exec RAG_kojo-db psql -U kojo_user kojo_db -c "
SELECT count(*) AS total_orphaned
FROM pg_constraint
WHERE contype = 'f'
  AND NOT EXISTS (
    SELECT 1 FROM pg_class
    WHERE oid = conrelid
  );
"

docker compose exec RAG_kojo-db psql -U kojo_user kojo_db -c "
SELECT schemaname, tablename, seq_scan, seq_tup_read, idx_scan, idx_tup_fetch
FROM pg_stat_user_tables;
"
```

### 4. Работоспособность приложения

```bash
# Health check
curl http://localhost:8080/ready

# Metrics (счётчики БД)
curl http://localhost:8080/metrics | grep kojo_db_

# Smoke: создать заказ
# ... через Telegram-команду
```

## Где хранить dumps

| Среда | Путь | Retention |
|-------|------|-----------|
| Production | `/var/backups/kojo/` | 7 дней (настраивается в `backup_postgres.sh`) |
| Stage | `/tmp/kojo_backups/` | По необходимости |
| Локально | `./backups/` (не трекать git) | По необходимости |

Для production настроить внешнее хранилище (S3/NFS) поверх локального каталога.

## Что нельзя коммитить

- Дампы БД (`.dump`, `.sql`, `.sql.gz`, `.rdb`)
- `.env` с реальными паролями
- Логи backup (`.log`)
- Любые файлы, содержащие production данные

`.gitignore` уже включает:
```
*.dump
*.sql.gz
/backups/
.env
```

Если нужно сохранить дамп в репозитории — положить в отдельный приватный S3/Git LFS и не включать в `.gitignore` под замком.

## Ссылки

- `scripts/backup_postgres.sh` — существующий скрипт backup (custom format, 7 дней retention)
- `docs/DEVELOPMENT_FLOW.md` — общий процесс разработки
- `deploy/CHECKLIST.md` — pre/post-deploy проверки
- `docker/docker-compose.yml` — production compose
- `docker/docker-compose.local.yml` — local override с Redis
