# Post-Extraction Status — Kojo Bot Service

## Extraction Date
2026-05-27

## Source Path
`databases/kojo/` in `quart-ollama_bot` repo

## Repository URLs

| Remote | URL | Status |
|---------|-----|--------|
| Gitea (origin) | `https://git.xloud.ru/gpakoh/kojo-bot-service` | ✅ Sync OK |
| GitHub (mirror) | `git@github.com:gpakoh/kojo-bot-service` | ✅ Sync OK |

## Commit Hashes

| Repo | Branch | HEAD Hash |
|------|--------|-----------|
| Kojo (local) | `main` | `a97d462` |
| Gitea | `main` | `a97d462` (same) |
| GitHub | `main` | `a97d462` (same) |
| Quart (parent) | `master` | `ef973939dc87` |

### Post-Extraction commits applied

| # | PR | Purpose | Merge |
|---|-----|---------|-------|
| 1 | #7 | RELEASES.md + CI container fix (`setup-python` → `nikolaik/python-nodejs`) | `f88831f` |
| 2 | #8 | Tag hash + CI fix details in RELEASES.md | `54ec3de` |
| 3 | #9 | `runs-on: kojo` for dedicated runner | `d0fb768` |
| 4 | #10 | RUNNER_OPERATIONS.md with kojo-runner docs | `b91f308` |
| 5 | #11 | Revert to single `lxc100-runner`, `runs-on: ubuntu-latest` restored | `1d7676f` |
| 6 | #12 | CI trigger expansion + DEVELOPMENT_FLOW.md + mirror sync docs | `d92ec06` |
| 7 | #13 | `revert/test-ci-trigger` verification PR | `a97d462` |

## Repository Stats
- 472 files
- 51,036 lines of code
- Single extraction commit `5d6562a`
- Post-extraction: 7 merged PRs (no file count / LOC change — only docs + CI)

## Test Status

| Check | Result | Details |
|-------|--------|---------|
| `pytest` | ✅ 1471 passed, 28 warnings | Coverage 59% |
| `mypy tg_bot services` | ✅ Clean | 0 errors |
| `compileall` | ✅ Clean | All modules compile |
| `ruff check .` | ⚠️ 15 errors (0 fixable) | Reduced from 185 via v0.1.1 (8 PRs) |

### Ruff Debt Breakdown (v0.1.1+)
- `E402`: 9 — intentional late imports in tests
- `E501`: 6 — long lines in migrations and test signatures

**Policy:** Accepted as non-blocking debt. 15 errors remain, enshrined in .ruff_accepted.txt.

## Docker Status
| Check | Result |
|-------|--------|
| `docker build -f docker/Dockerfile` | ✅ Build OK (image `kojo-bot-service:local`) |
| `docker compose config` | ⚠️ Requires `.env` file (not committed) |

## CI Status
| Platform | Workflows | Status |
|----------|-----------|--------|
| Gitea Actions | `.gitea/workflows/ci.yml` | ✅ Running (compileall blocking, pytest/mypy/ruff informational, docker optional) |
| GitHub Actions | Not configured | 🔴 Not set up |

### Gitea CI Details
- **Pipeline:** `Kojo CI` — single job with 4 gates (compileall → pytest → mypy → ruff)
- **Gates:** all blocking — `continue-on-error` removed in v0.1.0
- **Runner:** single `lxc100-runner` (capacity=1, labels: `ubuntu-latest` + `lxc100-runner`)
- **CI triggers:**
  - **push:** `main`, `feature/**`, `fix/**`, `chore/**`, `docs/**`, `ci/**`, `revert/**`, `hotfix/**`, `release/**`, `test/**`, `refactor/**`
  - **pull_request:** `main`
- **Container:** `nikolaik/python-nodejs:python3.12-nodejs24` (replaced `actions/setup-python@v5` which was broken on Gitea act_runner)
- **Last run:** ✅ all 4 gates green (pytest 1471 passed, mypy 0, compileall clean, ruff 15 accepted)
- **Runner restarted daily at 04:00 via cron** — workaround for Gitea Actions runner stuck-in-progress issue

### CI Workflow
`.gitea/workflows/ci.yml` — 62 lines, standard Gitea Actions syntax.

## Quart Repo (Parent) Verification
| Check | Result |
|-------|--------|
| `databases/kojo/` files in working tree | ✅ Removed |
| `kojo-extract` branch | ⚠️ Still exists (8 commits, no submodule) |
| `.gitmodules` with kojo | ✅ None |
| `rg "databases/kojo"` in source files | ✅ Clean |
| `rg "kojo-bot-service"` in source files | ✅ Clean |

## Secrets Check
| Check | Result |
|-------|--------|
| `.env` files committed | ✅ None |
| Real secrets in tracked files | ✅ Clean |
| `secrets_loader.py` in repo | ✅ Legitimate code, not secrets |

## Key Findings
1. **Docker build passes** — image builds successfully
2. **docker-compose** needs `.env` (normal, not committed)
3. **CI configured** — Gitea Actions workflow running
4. **Runner limitation** — pytest/mypy/ruff fail on LXC runner (compileall passes). Needs runner log access to debug
5. **`kojo-extract` branch** still exists in Quart repo — consider cleanup
6. **No `README.md`** in kojo repo root — consider adding
7. **No `Makefile`** — consider if needed for deployment
8. **`.gitignore` updated** — added `.coverage`, `htmlcov/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`

## Known Follow-Ups
1. ✅ Gitea Actions CI for kojo — set up
2. Set up GitHub Actions CI for kojo
3. Clean up `kojo-extract` branch in Quart repo
4. Add `README.md` for kojo
5. Add `.env.example` to kojo repo
6. ✅ pytest/mypy/ruff теперь работают на LXC runner — дебаг runner окружения больше не нужен
7. Verify production deployment path after extraction
8. ✅ ruff debt reduced from 185→15 (accepted as non-blocking)
9. ⚠️ Gitea Actions runner stuck-in-progress issue — workaround via daily restart at 04:00
