# Technical Debt — Kojo Bot Service

## Ruff Baseline (2026-05-29)

- Активные правила: `E`, `F`, `W`, `I`
- Текущий результат: **0 errors** в CI
- Конфигурация: `pyproject.toml` → `[tool.ruff.lint]` → `select = ["E", "F", "W", "I"]`

### Accepted per-file-ignores

- **E501** (line too long) — хендлеры, сервисы, утилиты — 30+ файлов
- **E402** (import not at top) — main, config_pusher, registration, order_queries, db, redis — 7 файлов

### Решение

- E501/E402 — accepted technical debt на время service extraction
- Не чинить formatting-only изменения до стабилизации границ сервисов
- После выноса сервисов — отдельная ветка `chore/ruff-baseline-cleanup`

### Follow-up

- Убрать per-file-ignores после стабилизации границ сервисов
- Пересмотреть набор активных правил (возможно расширить)
