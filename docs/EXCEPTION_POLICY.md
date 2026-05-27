# Exception Policy

## Layers and boundaries

| Layer | File(s) | Boundary type | Broad except allowed? |
|-------|---------|---------------|-----------------------|
| Maintenance wrappers | `tg_bot/tenant/migrations.py` | Migration/rollback — error must not crash the process | Yes (Category A) |
| UI fallback | `tg_bot/ui_helpers.py` | Message delete/edit/cleanup — user flow must not crash | Yes (Category A) |
| Callback parsing | `tg_bot/schemas/callbacks.py` | Malformed callback data from user — graceful degradation to None | Yes (Category A) |
| Middleware | `tg_bot/rate_limit_middleware.py` | Rate limiting — identity extraction / callback answer failure must not crash | Yes (Category A) |

## Where broad `except Exception` is allowed

Broad `except Exception` is permitted **only** in layers that are explicitly designated as error boundaries:

### A — Error boundary / fallback layer

Characteristics:
- The code is a safety net around an operation that must never crash the caller
- There is a specific `except` for known exceptions *before* the broad `Exception`
- On exception: log + return safe default (False, None, etc.)
- Tests explicitly verify graceful degradation

Examples from audited files:

```python
# migrations.py — maintenance wrapper: migration error must not crash the process
except Exception as e:
    logger.error(...)
    return False
```

```python
# ui_helpers.py — UI fallback: individual delete failure must not block the loop
except TelegramError as e:
    _handle_telegram_error(e, ...)
except Exception as e:
    logger.warning(...)
```

```python
# callbacks.py — callback parsing: malformed data → None
except Exception:
    return None
```

```python
# rate_limit_middleware.py — middleware boundary: failure degrades to safe default
except Exception as e:
    logger.warning(...)
    return None
```

### B — Infrastructure critical path

Broad `except Exception` is allowed **only** if:
- Error is logged via `logger.exception()` or `logger.warning(exc_info=True)`
- There is a safe fallback path
- No silent corruption or data loss
- No bare `except: pass`

The audited files do not contain any Category B blocks that would justify broad `except Exception`.

## Where broad `except Exception` is NOT allowed

### C — Programming error hiding

Broad `except Exception` must NOT be used in contexts where it would hide:
- `AttributeError` — calling method on wrong type
- `TypeError` — wrong argument types
- `ValueError` from broken contract
- `AssertionError` — debug assertions
- `KeyError` from corrupted data structure
- `ImportError` / `ModuleNotFoundError`
- Pydantic `ValidationError` from wrong callback schema (unless explicitly documented as expected malformed input)

The audited files do not contain any Category C blocks.

## Logging requirements

| Severity | Where | Method |
|----------|-------|--------|
| `logger.warning` | UI fallback, middleware boundary | `logger.warning(f"...: {e}")` |
| `logger.error` | Maintenance wrapper, critical path | `logger.error(f"...: {e}")` |
| Silent (no log) | Callback parsing (hot path, expected malformed data) | No log — `return None` |

**Never log:** secrets, tokens, passwords, API keys, database connection strings.

## Prohibited patterns

- `except:` (bare except) — always wrong
- `except Exception: pass` — always wrong
- `except Exception` without logging in a non-hot-path block — suspicious
- Catching `Exception` to work around a broken interface instead of fixing the interface

## Current justified broad `except Exception` blocks

### migrations.py (4 blocks)

| Line | Method | Comment |
|------|--------|---------|
| 95 | `migrate_tenant()` | After `TimeoutExpired`. Catch-all for subprocess/os errors. |
| 181 | `rollback_tenant()` | After `TimeoutExpired`. Same pattern. |
| 206 | `create_tenant()` | Schema creation via external db call. |
| 229 | `drop_tenant()` | Schema destruction via external db call. |

### ui_helpers.py (6 blocks)

| Line | Function | Comment |
|------|----------|---------|
| 57 | `cleanup_previous_menu()` | After `TelegramError`. Message loop must not crash on individual failure. |
| 76 | `safe_delete_message()` | After `TelegramError`. Returns False. |
| 153 | `safe_update_ui()` (delete message) | After `TelegramError`. Delete during UI update. |
| 161 | `safe_update_ui()` (delete query.message) | After `TelegramError`. Same pattern. |
| 199 | `safe_edit_ui()` | After `TelegramError`. Edit falls back to send_message. |

### callbacks.py (1 block)

| Line | Function | Comment |
|------|----------|---------|
| 169 | `parse_callback_data()` | Silent catch — expected on malformed callback data from user. No logging to avoid hot-path noise. |

### rate_limit_middleware.py (2 blocks)

| Line | Method | Comment |
|------|--------|---------|
| 63 | `__init__` / `_user_key()` | Identity extraction must not crash rate limiting. |
| 178 | `__call__()` | Callback answer must not crash rate limit enforcement. |

## Audit scope

- **Total `except Exception` across `tg_bot/`, `services/`, `utils/`:** 16
- **In audited files (4 files):** 12
- **Outside audit scope:** 4 (`navigation.py:239,265`, `ai_communication_service.py:390`, `retry_policy.py:123`)
- **Bare `except:` found:** 0
- **`except Exception: pass` found:** 0
