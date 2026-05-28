# Docker Bootstrap

## Python version

`python:3.12-slim` (соответствует `requires-python = ">=3.12"` в pyproject.toml).

## Dependencies source of truth

`requirements-prod.txt` — production-зависимости.
Dockerfile копирует его как `requirements.txt` и ставит через `pip install -r requirements.txt`.

- `pyproject.toml` НЕ содержит секции `[project.dependencies]` — только tool-конфиги.
- `requirements.txt` (корневой) — для локальной разработки, может содержать dev-зависимости (pytest, mypy).

## Build image

```bash
docker build -f docker/Dockerfile -t kojo-bot .
```

## Run with docker compose (production)

```bash
cd docker
cp .env.example ../.env     # создать .env из примера
# отредактировать ../.env с реальными токенами
docker compose up -d
```

## Local smoke test (development)

```bash
docker build -f docker/Dockerfile -t kojo-bot:smoke .
cp .env.example .env
docker compose -f docker/docker-compose.yml -f docker/docker-compose.local.yml --env-file .env up -d
docker exec RAG_kojo-db pg_isready -U kojo_user -d kojo_db  # ждать готовности
docker run --rm --network docker_kojo_local \
  -e DATABASE_URL=postgresql+asyncpg://kojo_user:kojo_password@RAG_kojo-db:5432/kojo_db \
  kojo-bot:smoke alembic upgrade head
docker compose -f docker/docker-compose.yml -f docker/docker-compose.local.yml down
```

## Required env files

- `.env` — основной файл (в корне проекта)
- `docker/.env.example` — пример для Docker-деплоя
- `.env.example` — пример для локальной разработки

## Verification

```bash
# compile
python -m compileall tg_bot services utils alembic tests

# ruff (только критические)
ruff check tg_bot services utils alembic tests --select F821,F822,F823,E999

# mypy (основные модули)
mypy tg_bot services

# pytest (не должен регрессировать)
pytest

# docker build
docker build -f docker/Dockerfile .
```
