# Typing Debt

Задокументированные mypy-ошибки, не исправленные в рамках соответствующих этапов.

## Pre-existing after Stage 1 (Docker and Dependencies Bootstrap)

Source: `mypy tg_bot services` — 5 errors in 3 files.

| # | File | Line | Error code | Description |
|---|------|------|------------|-------------|
| 1 | `tg_bot/infrastructure/cache.py` | 137 | attr-defined | `Redis.aclose()` не существует в type stub (есть в runtime). Нужен `type: ignore[attr-defined]`. |
| 2 | `tg_bot/infrastructure/cache.py` | 155 | union-attr | То же, третий экземпляр. |
| 3 | `tg_bot/infrastructure/cache.py` | 202 | attr-defined | То же, третий экземпляр. |
| 4 | `tg_bot/core/state_manager.py` | 114 | arg-type | `hdel` typed expects `list[Any]`, передаётся `str`. Текущий `# type: ignore[misc]` не ловит arg-type. Нужен `# type: ignore[arg-type]`. |
| 5 | `tg_bot/bot_services/product_sync_service.py` | 239 | redundant-cast | `cast(str, val)` избыточен, т.к. `val` уже `str`. |

**Not in scope for Docker/Dependencies bootstrap.**  
Fix target: **Static Typing Debt Cleanup** (next phase).

### Resolution plan

- `cache.py` — 3× `# type: ignore[attr-defined]` на `aclose()`
- `state_manager.py` — заменить `# type: ignore[misc]` → `# type: ignore[arg-type]`
- `product_sync_service.py` — убрать `cast(str, ...)` (redundant)
