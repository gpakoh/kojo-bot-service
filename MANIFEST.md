🏗 MANIFEST — Kojo Bot SaaS Production Standard

**Версия:** 1.0.0  
**Цель:** Кодовая база Kojo соответствует уровню production-grade SaaS для малого бизнеса (кофейни/чайные). Подходит как для bare-metal (CPU-only), так и для Docker-оркестрации.  
**Scope:** Telegram-бот (python-telegram-bot), Quart-интеграция, LLM/RAG-сервис, PostgreSQL, Redis, Proxy Pool.


## §1. Архитектура и чистота кода

### §1.1. Структура слоёв (Clean Architecture)
```
┌─────────────────────────────────────┐
│  Handlers / UI (tg_bot/handlers)    │  ← Зависят только от Application
├─────────────────────────────────────┤
│  Application (tg_bot/application)   │  ← CQRS: Commands + Queries
├─────────────────────────────────────┤
│  Domain (tg_bot/domain)             │  ← Aggregates, Value Objects, Events
├─────────────────────────────────────┤
│Infrastructure(tg_bot/infrastructure)│ ← DB, Cache, Event Store, Metrics
├─────────────────────────────────────┤
│  Services / Adapters (services/)    │  ← Gateway, Proxy Pool, Retry
└─────────────────────────────────────┘
```
**Правило:** Зависимости направлены строго внутрь. Domain не знает про Telegram, HTTP, PostgreSQL.

### §1.2. Dependency Injection (DI)
- Все сервисы получают зависимости через `__init__`. Запрещён импорт и вызов глобальных синглтонов внутри бизнес-логики.
- Глобальные регистры (`_clients`, `_proxy_pools`, `_circuit_breakers`) обязаны иметь:
  - TTL-очистку (минимум 1 час);
  - thread-safe / asyncio-safe доступ;
  - функцию `clear_*()` для тестовой изоляции.
- **Acceptance:** `mypy --strict` проходит без `type: ignore` в слоях Domain и Application.

### §1.3. DDD (Domain-Driven Design)
- **Aggregate Root:** `Order` (и будущие `User`, `Product`). Защита инвариантов внутри агрегата.
- **Value Objects:** `Money`, `Address` — immutable, валидация в `__init__`.
- **Domain Events:** `OrderCreated`, `OrderStatusChanged` и т.д. События — dataclasses, immutable. Публикация через шину (не прямой вызов хендлеров).
- **State Machine:** Все статусы `OrderStatus` имеют явный граф переходов. Недопустимый переход → `InvalidStateTransition`.

### §1.4. CQRS
- **Commands:** пишут в БД, эмитят Domain Events, возвращают `Result[Ok, Error]` (не бросают Exception в хендлеры).
- **Queries:** read-only, используют `ReadRepository`, возвращают `PaginatedResult[T]`.
- **Read Models:** `tg_bot/read_models/` — flat dataclasses только для отображения. Нет бизнес-логики.

### §1.5. Критерии качества кода
- **DRY:** Любая логика дублируется максимум 1 раз (utility). Дублирующиеся методы → рефакторинг.
- **Dead code:** Все `print()`, закомментированные блоки, неиспользуемые импорты — удалены перед коммитом.
- **Функции:** Длина ≤60 строк. Если больше — разбиение на приватные методы.
- **Классы:** Количество публичных методов ≤10. Иначе — выделение миксинов или сервисов.


## §2. Безопасность (Security)

### §2.1. Управление секретами (Secrets Management)
- **Запрещено:** хранить plaintext-токены, пароли БД, API-ключи в `.env` файлах, которые попадают в Git.
- **Bare-metal:** используется механизм runtime-переменных (например, `source /etc/kojo/secrets.env` перед стартом) или systemd `EnvironmentFile` с правами `600`.
- **Docker:** используются Docker Secrets (или mount файла с секретами в `/run/secrets/`).
- **Логи:** Все логи проходят через `RedactingFormatter`. Regex-замена токенов, паролей, URL с credentials на `[REDACTED]`.
- **Acceptance:** `grep -r "BOT_TOKEN\|password\|secret" logs/` возвращает 0 совпадений с реальными значениями.

### §2.2. Валидация входных данных
- **LLM Prompt:** Весь пользовательский текст перед вставкой в prompt проходит `sanitize_for_llm_prompt()`. Блокируются `<script`, `on*=` события, ограничение длины (max 2000 символов).
- **HTML для Telegram:** Единый pipeline `_prepare_html()` (whitelist-подход). Разрешены только: `<b>`, `<i>`, `<u>`, `<code>`, `<a href="...">`. Всё остальное — strip.
- **Callback data:** Валидатор длины (≤64 байт для Telegram), проверка префиксов, отсутствие инъекций.
- **SQL:** Только parameterized queries (`$1`, `$2`). Запрещён f-string или конкатенация в SQL.

### §2.3. Rate Limiting & Abuse Protection
- **Per-user:** callback throttle (1 сек), AI throttle (5 сек), search throttle (3 сек).
- **Per-bucket:** `BucketConfig` с `ttl`, `max_calls`, `message`. Навигация — 3 вызова, оплата — 2 вызова.
- **Gateway:** Circuit Breaker на внешние API (Quart, LLM). Порог: 5 ошибок → OPEN, timeout 30 сек, HALF_OPEN после восстановления.
- **Proxy Pool:** Автоматический failover при HTTP 5xx / timeout. Max retries = 3, cooldown = 300 сек.


## §3. Надёжность и отказоустойчивость (Reliability)

### §3.1. Graceful Shutdown
- При получении `SIGTERM` / `SIGINT`:
  1. Бот перестаёт принимать новые update'ы (stop webhook polling).
  2. Завершаются активные задачи с таймаутом 30 сек.
  3. Закрываются пулы: PostgreSQL (`pool.close()`), Redis, GatewayClient (`aclose()`), ProxyPool.
  4. Процесс завершается с кодом 0.
- **Acceptance:** `kill -15 <pid>` не приводит к потере данных в корзине/заказе.

### §3.2. Health Checks
- **Liveness:** `GET /health` — процесс жив, Python не завис.
- **Readiness:** `GET /ready` — PostgreSQL доступна, Redis доступен, Quart (если нужен) отвечает.
- **Docker:** `HEALTHCHECK` использует readiness endpoint, интервал 30 сек, timeout 10 сек, 3 retries.
- **Bare-metal:** systemd `ExecStartPost` или отдельный скрипт ждёт `pg_isready` и `/ready`.

### §3.3. Retry & Idempotency
- **Retry Policy:** Exponential backoff (base=2, jitter 50-150%), max delay 30 сек.
- **Idempotency:** Все платёжные и заказные операции используют `idempotency_key` (UUID), хранятся в Redis/DB 24 часа. Повторный запрос с тем же ключом возвращает кешированный результат, не создаёт дубль.

### §3.4. База данных
- **Connection Pool:** `asyncpg.Pool` с `min_size=5`, `max_size=20`, `timeout=10`.
- **Migrations:** Только Alembic. Запрещён `init_db()` с `CREATE TABLE IF NOT EXISTS` в коде бота.
- **Transactions:** Все операции «заказ + items» — в одной транзакции. `BEGIN ... COMMIT`.


## §4. Инфраструктура и деплой

### §4.1. Docker (для GPU-нод и RAG)
- **Multi-stage build:** `builder` (compile deps) → `runtime` (slim image).
- **Non-root user:** `USER appuser` (UID 1000), права только на `/app`.
- **Read-only root fs:** `read_only: true` где возможно, tmpfs для `/tmp`.
- **Resource limits:** `mem_limit`, `cpus` указаны для каждого сервиса.

### §4.2. Bare-metal (для CPU-only slave-нод)
- **Unit-файл:** `kojo-bot.service` (systemd) или `service kojo-bot start` (SysVinit).
- **Auto-restart:** `Restart=always`, `RestartSec=5`.
- **Logging:** stdout/stderr → journald или rsyslog с ротацией (`logrotate`).
- **Monitoring:** `monit` или `systemd` watchguard для перезапуска при memory leak.

### §4.3. Конфигурация
- **Hierarchical Config:** Env → DB (settings) → File (config.json). Приоритет: DB > Env > File.
- **Hot reload:** Изменение `config.json` или DB-настройки подхватывается без перезапуска (TTL кэша 60 сек).
- **Feature Flags:** Все экспериментальные фичи (`use_lightrag`, `enable_web_search`) — через `config.json` с возможностью отключения в runtime.


## §5. Тестирование (Testing)

### §5.1. Пирамида тестов
```
        /\\
       /  \\   E2E (1%) — Telegram API mock
      /----\\
     /      \\  Integration (20%) — DB + Gateway + Proxy
    /--------\\
   /          \\ Unit (79%) — Domain, Services, Utils
  /--------------\\
```

### §5.2. Unit-тесты
- **Coverage:** Core (domain, services, gateway) ≥ 80%. Handlers ≥ 60%.
- **Mocking:** Внешние HTTP-вызовы (`httpx.AsyncClient`) мокаются через `respx` или `unittest.mock`.
- **Изоляция:** Каждый тест очищает глобальные регистры (`clear_gateway_clients()`, `clear_all_pools()`).

### §5.3. Интеграционные тесты
- **DB:** Используется отдельная `test_kojo_db`, создаётся `asyncpg.Pool` на каждый test session, откатывается транзакция после теста.
- **Gateway:** Поднимается `pytest-httpx` или `respx` для проверки retry + circuit breaker.
- **Proxy:** TCP-mock сервер на `localhost:0` для проверки failover.

### §5.4. Property-based тесты
- **Hypothesis:** Парсеры цен (`parse_product_file`), поисковые запросы (`search_products`), нормализация текста.
- **Цель:** Ловить edge-case без ручного перебора.

### §5.5. CI / Pre-commit
- **Git hook:** `pre-commit.sh` запускает:
  1. `ruff check tg_bot/ tests/`
  2. `mypy --strict tg_bot/domain/ tg_bot/application/ services/`
  3. `pytest tests/ -q --tb=short`
- **Блокировка:** Если любой шаг падает — `exit 1`, коммит отменяется.


## §6. Наблюдаемость (Observability)

### §6.1. Логирование (Logging)
- **Формат:** Structured JSON. Обязательные поля: `timestamp`, `level`, `logger`, `message`, `correlation_id`, `user_id` (если есть).
- **Уровни:**
  - `DEBUG` — SQL-запросы (если включено флагом), FSM-переходы.
  - `INFO` — бизнес-события (заказ создан, оплата прошла).
  - `WARNING` — retry, circuit breaker OPEN, proxy failover.
  - `ERROR` — исключения, недоступность БД, LLM timeout.
- **Redaction:** Секреты маскируются до записи в файл/stdout.

### §6.2. Метрики (Metrics)
- **Endpoint:** `GET /metrics` (Prometheus-формат).
- **Обязательные метрики:**
  - `kojo_orders_total` (counter по статусам)
  - `kojo_order_value_sum` (histogram)
  - `kojo_llm_latency_seconds` (histogram)
  - `kojo_proxy_failover_count` (counter)
  - `kojo_db_query_duration_seconds` (summary)
  - `kojo_active_users` (gauge)
- **Business метрики:** Заказы/час, средний чек, конверсия корзины → checkout.

### §6.3. Трейсинг (Tracing)
- **Correlation ID:** `X-Request-ID` (UUID4) генерируется на входе в бота и пробрасывается во все HTTP-запросы (Quart, LLM, Integration Service).
- **Логи:** Все записи в рамках одного запроса содержат один `correlation_id`.

### §6.4. Алертинг
- **ERROR-логи:** При `ERROR` или `CRITICAL` отправляется сообщение в `ADMIN_CHAT_ID` (Telegram) или webhook в Slack/PagerDuty.
- **Circuit Breaker OPEN:** Мгновенное уведомление админу.
- **DB disconnect:** Если readiness падает — алерт каждые 5 минут до восстановления.


## §7. SaaS и масштабирование

### §7.1. Multi-tenancy (Мультитенантность)
- **Tenant ID:** Каждый бот-экземпляр имеет `bot_id` (например, `kojo`, `lebo_coffee`).
- **Изоляция данных:** Row-level security (RLS) в PostgreSQL или префикс таблиц (`kojo_orders` vs `lebo_orders`).
- **Config:** Каждый тенант имеет свой `config.json` и `.env`, загружается в `HierarchicalConfig`.

### §7.2. API и интеграции
- **OpenAPI:** Спецификация `services/gateway/openapi_spec.yaml` — источник правды.
- **Версионирование:** Публичные endpoint'ы: `/v1/api/...`. Internal: `/internal/...`.
- **Gateway Client:** Сгенерированный (или typed-ручной) клиент с retry + circuit breaker. Нет raw `httpx.get()` в хендлерах.

### §7.3. Federation (Master / Slave)
- **Master:** Принимает задачи от пользователей, маршрутизирует на Slave.
- **Slave:** Только вычисления (CPU-only). Нет прямого доступа пользователей.
- **Secret:** `FEDERATION_SECRET` для HMAC-подписи запросов между нодами.

### §7.4. Zero-downtime deploy
- **Rolling update:** Новый контейнер поднимается → readiness OK → старый получает SIGTERM.
- **Bare-metal:** `service kojo-bot restart` с `graceful shutdown` (см. §3.1).


## §8. Процесс разработки (Process)

### §8.1. Git-стратегия
- **Main branch:** Защищена. Только через PR/MR.
- **Conventional Commits:** `feat:`, `fix:`, `refactor:`, `test:`, `docs:`.
- **Tagging:** `v1.2.3` — semver.

### §8.2. Definition of Done (DoD)
Перед тем как задача считается выполненной, проверяется чек-лист:
- [ ] Код проходит `ruff` без ошибок.
- [ ] Код проходит `mypy --strict` в затронутых слоях.
- [ ] Написаны unit-тесты (coverage не ниже текущего).
- [ ] Интеграционные тесты проходят (если затронут Gateway/DB).
- [ ] Нет `print()`, закомментированного кода, дублирующейся логики.
- [ ] Логи не содержат секретов (проверка grep).
- [ ] Graceful shutdown не сломан (проверяется через `kill -15`).
- [ ] Документация (docstring / README) обновлена при изменении контрактов.

### §8.3. Code Review Checklist
Ревьюер обязан проверить:
1. **Архитектура:** Нет ли нарушения направления зависимостей (Domain → Infrastructure)?
2. **Безопасность:** Все ли входные данные валидируются/sanitize?
3. **Надёжность:** Есть ли обработка `None`, `TimeoutError`, `ConnectionError`?
4. **Тесты:** Покрыты ли граничные случаи?
5. **Observability:** Добавлены ли `logger.info/warning/error` в ключевые пути?


## §9. Gap Analysis — текущее состояние vs Манифест

| Пункт манифеста | Текущий статус | Действие |
| §1.2 DI без глобального state | ❌ `_clients`, `_proxy_pools` без TTL | Добавить TTL + cleanup |
| §1.5 Dead code / DRY | ❌ 4x `return text.strip()` в `_prepare_html` | Рефакторинг в pipeline |
| §2.1 Secrets management | ❌ `.env` в Git, plaintext токены | Внедрить Docker Secrets / runtime env |
| §2.2 HTML sanitize pipeline | ⚠️ Есть, но дублируется и разрознен | Единый `_prepare_html` |
| §3.1 Graceful shutdown | ❌ Не видно в дампе | Добавить обработку SIGTERM в `main.py` |
| §3.2 Readiness endpoint | ❌ Нет `/ready` | Добавить в TG-bot webhook server |
| §5.5 Pre-commit блокирует | ⚠️ Есть скрипт, но не настроен как git hook | `git config core.hooksPath` или `pre-commit` framework |
| §6.1 JSON structured logs | ❌ Plain text | Внедрить `python-json-logger` |
| §6.2 Prometheus metrics | ❌ Нет `/metrics` | Добавить `prometheus-client` |
| §7.3 Federation HMAC | ⚠️ Есть `FEDERATION_SECRET`, но не видно подписи | Добавить HMAC к inter-node requests |


## §10. Приоритет фаз приведения к манифесту

1. **Phase 1 — Critical Fixes:** SyntaxError, dead code, requirements sync, healthcheck.
2. **Phase 2 — Type Safety:** `mypy --strict` на Domain + Application + Services.
3. **Phase 3 — Reliability:** Graceful shutdown, idempotency, readiness endpoint.
4. **Phase 4 — Testing:** Интеграционные тесты Gateway/Proxy, coverage ≥80% core.
5. **Phase 5 — Security:** Secrets management, redaction, input validation hardening.
6. **Phase 6 — Observability:** JSON-логи, Prometheus, correlation ID.
7. **Phase 7 — SaaS:** Multi-tenancy hardening, feature flags, zero-downtime.
8. **Phase 8 — Docs:** OpenAPI client generation, runbooks, deployment guide.


*Манифест является обязательным к исполнению. Любое отклонение требует documented exception с рисками и mitigation.*

