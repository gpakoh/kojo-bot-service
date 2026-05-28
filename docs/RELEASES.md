# Kojo Bot Service — Releases

## Post-v0.1.1 Operational Fixes (2026-05-29)

Базовый тег: `v0.1.1` (новый release tag не создавался).

### Расширение CI-триггеров

- В `.gitea/workflows/ci.yml` добавлены operational branch prefixes в push-триггеры:
  - `revert/**`, `hotfix/**`, `release/**`, `test/**`, `refactor/**`
- Ранее были только: `main`, `feature/**`, `fix/**`, `chore/**`, `docs/**`, `ci/**`
- `DEVELOPMENT_FLOW.md` обновлён: таблица branch prefixes расширена до 10 префиксов, добавлена заметка для агентов о падении при неизвестном префиксе

### Верификация через PR #13 (`revert/test-ci-trigger`)

- push trigger (`revert/`) — ✅ green
- pull_request trigger (`revert/` → `main`) — ✅ green
- main trigger — ✅ green
- PR merge с обеими CI-проверками — ✅ без снятия branch protection

CI теперь работает для `revert/` веток без необходимости временно отключать branch protection.

### GitHub Mirror Sync Runbook

- `git push github main` иногда ошибочно пишет `Everything up-to-date` при новых коммитах
- Задокументирован explicit SHA push как надёжный метод: `git push github $(git rev-parse HEAD):main`
- Force push запрещён без отдельного подтверждения

### Cleanup

- Удалены 7 stale remote-веток от merged PR #7–#13
- Ветки `ci/branch-triggers-and-docs` (PR #12) и `revert/test-ci-trigger` (PR #13) удалены после merge

### Production-код не менялся

- Только `.gitea/workflows/ci.yml` (триггеры) и `docs/` — production-код не затронут

## v0.1.1 (2026-05-28) — Hardening Release

**Commit:** `340f7c5`
**Tag hash:** `68b36d3832ab4a524ca3352a18f9f75f6f9dea81`

### Что включено

- **CI на feature branches + pull_request** — триггеры исправлены:
  - push → `feature/**`, `fix/**`, `chore/**`, `docs/**`, `ci/**`
  - pull_request → `main`
- **Branch protection contexts** — исправлены имена проверок:
  - `Kojo CI / test (push)`
  - `Kojo CI / test (pull_request)`
- **Ruff debt reduction** — 97 → 15 errors (78 auto-fixed, 4 manual)
- **Docker Compose smoke validation**:
  - `.env.example`, `docker/.env.example`, `docker/docker-compose.local.yml` добавлены
  - `Dockerfile` / `Dockerfile.multistage`: COPY `alembic/` вместо `migrations/`
  - `alembic/env.py`: async engine + `DATABASE_URL` override
  - Fix миграций: sequence creation, `postgresql.JSONB`, `DROP CONSTRAINT IF EXISTS`
  - Docker build, compose config, alembic upgrade — проходят
- **DB backup/restore runbook** — `docs/DB_BACKUP_RESTORE.md`
- **CI fix: container image вместо `setup-python`** — `actions/setup-python@v5` не работает в Gitea Actions (act_runner), перешли на `nikolaik/python-nodejs:python3.12-nodejs24`
- **pytest**: 1471 passed, 0 failed
- **mypy**: 0 issues
- **compileall**: clean

### Known remaining debt

- 15 ruff errors (зафиксированы, не блокируют CI):
  - 9× E402 — intentional late imports в тестах
  - 6× E501 — длинные строки в миграциях и тестовых сигнатурах

## v0.1.0 (2026-05-28)

**Commit:** `3c1c9677efbe20a7c2292cc209c5e0f518133ce7`
**Tag hash:** `1fffdb9e4a2c3de21c8f78ceef853ccf8b288f20`

### Что включено

- Extraction complete — код вынесен из monorepo `databases/kojo` в отдельный репозиторий
- CI green — все gates проходят:
  - compileall
  - pytest (1471 passed, 0 failed, 0 errors)
  - mypy (0 issues)
  - ruff (0 errors)
- Все quality gates blocking — `continue-on-error` удалён
- Gitea и GitHub mirror синхронизированы
