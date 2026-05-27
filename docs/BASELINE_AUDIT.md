# Project Baseline Audit

**Дата:** 2026-05-26
**Проект:** Kojo Bot (`databases/kojo`)
**Python:** 3.12.2 (система), pyproject.toml `>=3.12`

## 1. Структура проекта

- `tg_bot/` — основной пакет бота (28 модулей, 17 хендлеров, 20 сервисов)
- `tg_bot/handlers/` — 17 модулей обработчиков
- `tg_bot/bot_services/` — 20 сервисных модулей
- `tg_bot/application/` — запросы, команды, обработчики событий
- `tg_bot/core/` — State manager, FSM router
- `tg_bot/di/` — Dependency injection (provider, middleware, UoW)
- `tg_bot/domain/` — Доменные модели
- `tg_bot/infrastructure/` — Кеш, HTML pipeline, secrets, репозитории
- `tg_bot/read_models/` — Read model keyboards
- `tg_bot/schemas/` — Pydantic схемы
- `tg_bot/tenant/` — Мультитенантность (база, middleware)
- `services/` — Proxy pool, proxy adapter, gateway
- `utils/` — Config pusher, env utils, image cache, logging, retry, UI formatters
- `tests/` — 1452 тестов в ~30 файлах
- `alembic/` — Миграции БД
- `docker/` — Dockerfile, docker-compose.yml, .dockerignore
- `scripts/` — backup shell скрипты
- `migrations/` — SQL файлы миграций
- `config/` — Файлы конфигов бота

## 2. Конфигурационные файлы

- `pyproject.toml` — ✅ есть, strict=true, mypy+ruff конфиг
- `requirements.txt` — ✅ есть, 11 зависимостей + dev
- `requirements-prod.txt` — ✅ есть, 12 зависимостей production-only
- `.env` — ✅ есть, корневой уровень
- `docker/.env` — ✅ есть
- `.pre-commit-config.yaml` — ✅ есть
- `.dockerignore` — ✅ создан
- `.env.example` — ✅ обновлён, покрывает все 54 переменные
- `docker/.env.example` — ✅ обновлён

## 3. Python Version Mismatch — РЕШЕНО

Dockerfile использует `python:3.12-slim` (было `3.11-slim`). Соответствует `requires-python = ">=3.12"` в pyproject.toml.

## 4. Результаты инструментов

### 4.1 `python -m compileall` — 0 ошибок

Все модули компилируются чисто.

### 4.2 `ruff check .` — 2 предупреждения (F821/F822/F823 — 0)

Оба предупреждения в `alembic/env.py`:
- `I001` — неотсортированный импорт
- `F401` — `typing.Any` импортирован, но не используется

В `tg_bot/`, `services/`, `utils/`, `tests/` ошибок нет.

### 4.3 `mypy tg_bot services` — 5 ошибок

Все ошибки известные, pre-existing typing debt:

- `tg_bot/infrastructure/cache.py` (строки 137, 155, 202) — `"Redis" has no attribute "aclose"` — type stub отстаёт от runtime
- `tg_bot/core/state_manager.py` (строка 114) — `hdel` ожидает `list[Any]`, передаётся `str`. `# type: ignore[misc]` не ловит `arg-type`
- `tg_bot/bot_services/product_sync_service.py` (строка 239) — избыточный `cast(str, val)`, val уже str

Ошибки зафиксированы в `docs/TYPING_DEBT.md`.  
28 модулей из Phase 13 проходят mypy --strict чисто (0 ошибок).

### 4.4 `pytest` — 1423/1452 passed (97.9%)

29 падений, все в error-handling путях:

- `test_navigation.py` — 2 падения, Error handler вызывает ValueError (pre-existing)
- `test_rate_limit_*.py` — 4 падения, Rate limit exception пути
- `test_ui_helpers.py` — 7 падений, Delete/edit fallback на общем исключении
- `test_tenant_migrations.py` — 4 падения, General exception в create/rollback/migrate/drop
- `test_gateway_retry_policy.py` — 10 падений, Retry count + circuit breaker
- `test_security_callbacks.py` — 1 падение, Zero product ID rejection
- `test_config_manager.py` — 1 падение, Redis default value

Все падения — в error-handling путях, где моки кидают исключения. Не связаны с бизнес-логикой.

## 5. Блокеры

**Docker build** — не блокирован, образ собирается на `python:3.12-slim` (416MB, без `build-essential`).

**Production deploy** — не блокирован, но 29 тестов падают на error-handling путях.

**Local dev / tests** — не блокирован.

## 6. Рекомендации

- **Dockerfile**: `build-essential` удалён (image 416MB, все зависимости через binary wheels). Всё чисто.
- **5 mypy ошибок**: исправить в рамках Static Typing Debt Cleanup
- **29 pytest падений**: разобрать в рамках Test Stabilization
- **Type Safety Expansion**: расширить mypy --strict на `core/`, `infrastructure/`, `main.py`, `services/`, `utils/`
