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

## Run with docker compose

```bash
cd docker
cp .env.example ../.env     # создать .env из примера
# отредактировать ../.env с реальными токенами
docker compose up -d
```

## Required env files

- `.env` — основной файл (в корне проекта)
- `docker/.env.example` — пример для Docker-деплоя

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
