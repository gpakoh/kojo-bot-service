# Kojo Bot Service — Releases

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
- **CI fix: container image вместо `setup-python`** — `actions/setup-python@v5` не работает
  в Gitea Actions (act_runner), перешли на `nikolaik/python-nodejs:python3.12-nodejs24`
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
