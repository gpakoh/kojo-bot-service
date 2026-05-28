# Post-Extraction Status — Kojo Bot Service

## Extraction Date
2026-05-27

## Source Path
`databases/kojo/` in `quart-ollama_bot` repo

## Repository URLs

- Gitea (origin): `https://git.xloud.ru/gpakoh/kojo-bot-service` — ✅ Sync OK
- GitHub (mirror): `git@github.com:gpakoh/kojo-bot-service` — ✅ Sync OK

## Commit Hashes

- Kojo (local) `main` — `613e000`
- Gitea `main` — `613e000` (same)
- GitHub `main` — `613e000` (same)
- Quart (parent) `master` — `ef973939dc87`

### Post-Extraction commits applied

1. PR #7 — RELEASES.md + CI container fix (`setup-python` → `nikolaik/python-nodejs`) — merge `f88831f`
2. PR #8 — Tag hash + CI fix details in RELEASES.md — merge `54ec3de`
3. PR #9 — `runs-on: kojo` for dedicated runner — merge `d0fb768`
4. PR #10 — RUNNER_OPERATIONS.md with kojo-runner docs — merge `b91f308`
5. PR #11 — Revert to single `lxc100-runner`, `runs-on: ubuntu-latest` restored — merge `1d7676f`
6. PR #12 — CI trigger expansion + DEVELOPMENT_FLOW.md + mirror sync docs — merge `d92ec06`
7. PR #13 — `revert/test-ci-trigger` verification PR — merge `a97d462`
8. PR #14 — Post-v0.1.1 operational status docs — merge `613e000`

## Repository Stats

- 472 files
- 51,036 lines of code
- Single extraction commit `5d6562a`
- Post-extraction: 8 merged PRs (только docs + CI, файлы/LOC не менялись)

## Test Status

- `pytest` — ✅ 1471 passed, 28 warnings, coverage 59%
- `mypy tg_bot services` — ✅ Clean, 0 errors
- `compileall` — ✅ Clean, все модули компилируются
- `ruff check .` — ⚠️ 15 errors (0 fixable), снижено с 185 через v0.1.1

### Ruff Debt (v0.1.1+)

- `E402`: 9 — intentional late imports в тестах
- `E501`: 6 — длинные строки в миграциях и тестовых сигнатурах

Политика: принято как non-blocking debt, 15 errors зафиксированы в `.ruff_accepted.txt`.

## Docker Status

- `docker build -f docker/Dockerfile` — ✅ Build OK (image `kojo-bot-service:local`)
- `docker compose config` — ⚠️ Requires `.env` file (не закоммичен)

## CI Status

- Gitea Actions `.gitea/workflows/ci.yml` — ✅ Running
- GitHub Actions — 🔴 Not configured

### Gitea CI Details

- **Pipeline:** `Kojo CI` — один job с 4 gates (compileall → pytest → mypy → ruff)
- **Gates:** все blocking — `continue-on-error` удалён в v0.1.0
- **Runner:** один `lxc100-runner` (capacity=1, labels: `ubuntu-latest` + `lxc100-runner`)
- **CI triggers:**
  - push: `main`, `feature/**`, `fix/**`, `chore/**`, `docs/**`, `ci/**`, `revert/**`, `hotfix/**`, `release/**`, `test/**`, `refactor/**`
  - pull_request: `main`
- **Container:** `nikolaik/python-nodejs:python3.12-nodejs24` (заменил `actions/setup-python@v5`, который не работал на Gitea act_runner)
- **Last run:** ✅ все 4 gates green (pytest 1471 passed, mypy 0, compileall clean, ruff 15 accepted)
- **Runner restart:** ежедневно в 04:00 через cron — workaround для Gitea Actions stuck-in-progress

### CI Workflow
`.gitea/workflows/ci.yml` — 62 строк, стандартный Gitea Actions синтаксис.

## Quart Repo (Parent) Verification

- `databases/kojo/` files in working tree — ✅ Removed
- `kojo-extract` branch — ⚠️ Still exists (8 commits, no submodule)
- `.gitmodules` with kojo — ✅ None
- `rg "databases/kojo"` in source files — ✅ Clean
- `rg "kojo-bot-service"` in source files — ✅ Clean

## Secrets Check

- `.env` files committed — ✅ None
- Real secrets in tracked files — ✅ Clean
- `secrets_loader.py` in repo — ✅ Legitimate code, not secrets

## Key Findings

1. **Docker build passes** — image собирается успешно
2. **docker-compose** требует `.env` (нормально, не закоммичен)
3. **CI настроен** — Gitea Actions workflow работает
4. **pytest/mypy/ruff** теперь работают на LXC runner — дебаг больше не нужен
5. **`kojo-extract` branch** всё ещё существует в Quart repo — нужно почистить
6. **Нет `README.md`** в корне kojo репозитория
7. **Нет `Makefile`**
8. **`.gitignore`** обновлён: добавлены `.coverage`, `htmlcov/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`

## Known Follow-Ups

1. ✅ Gitea Actions CI для kojo — настроен
2. Настроить GitHub Actions CI для kojo
3. Почистить `kojo-extract` branch в Quart repo
4. Добавить `README.md` для kojo
5. Добавить `.env.example` в kojo repo
6. ✅ pytest/mypy/ruff работают на LXC runner — дебаг не нужен
7. Verify production deployment path после extraction
8. ✅ ruff debt снижен с 185 до 15 (принято как non-blocking)
9. ⚠️ Gitea Actions runner stuck-in-progress — workaround: ежедневный restart в 04:00
