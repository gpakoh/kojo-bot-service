# Kojo Bot Service — Development Flow

## Repository model

- **Gitea** (`git.xloud.ru/gpakoh/kojo-bot-service`) — primary, CI via Gitea Actions
- **GitHub** (`github.com/gpakoh/kojo-bot-service`) — mirror / backup, pushed after every commit to main
- Both remotes are pushed simultaneously from local

## Branch protection

`main` is **protected**:

- Direct push — **disabled** for all users
- Force push — **disabled**
- Branch deletion — **disabled**
- Required CI status check — **enabled**: the `test` job (compileall → pytest → mypy → ruff) must pass
- Admin override — **disabled** (`block_admin_merge_override: false`)

All changes must go through a feature branch and pull request.

## CI triggers

Gitea Actions runs the `test` job on:

- **push** to any branch matching `main`, `feature/**`, `fix/**`, `chore/**`, `docs/**`, `ci/**`, `revert/**`, `hotfix/**`, `release/**`, `test/**`, `refactor/**`
- **pull_request** targeting `main`

This means CI runs automatically on feature branches before a PR is created, and again when a PR is opened or updated.

Если агент создаёт ветку с другим префиксом (не из списка выше), push-CI не запустится, а branch protection заблокирует merge из-за отсутствующего required context `Kojo CI / test (push)`. В таком случае нужно либо добавить префикс в триггеры, либо временно убрать push-check из branch protection (через Gitea API PATCH `/branch_protections/main`).

## Branch model: trunk-based

```
feature/<short-name>  →  PR  →  main
```

No `develop` branch. Reason: single-developer team, CI is fast, trunk-based keeps history linear and simple.

Branch naming:

- `feature/<short-name>` — new functionality
- `fix/<short-name>` — bugfixes
- `chore/<short-name>` — maintenance, refactoring
- `ci/<short-name>` — CI / workflow changes
- `docs/<short-name>` — documentation-only changes
- `revert/<short-name>` — revert commits
- `hotfix/<short-name>` — urgent fixes to main
- `release/<short-name>` — release preparation
- `test/<short-name>` — CI / trigger testing
- `refactor/<short-name>` — refactoring

## PR checklist

Before merging into `main`:

- [ ] `pytest` — all tests pass
- [ ] `mypy tg_bot services` — no issues
- [ ] `ruff check tg_bot/ services/ utils/` — all checks pass
- [ ] `python -m compileall . -q` — no compilation errors
- [ ] Docker build — if Dockerfile or dependencies changed

## Releases

Tags follow [SemVer](https://semver.org/):

```
vMAJOR.MINOR.PATCH
```

- Annotated tags (`git tag -a`)
- Pushed to both remotes

### Published

- **v0.1.0** (2026-05-28) — `3c1c9677`
- **v0.1.1** (2026-05-28) — `340f7c5`

## GitHub mirror sync

GitHub (`github.com/gpakoh/kojo-bot-service`) — mirror/backup, обновляется после каждого merge в main.

`git push github main` иногда ошибочно говорит `Everything up-to-date` даже при новых коммитах.
Надёжный способ — явный пуш по SHA:

```bash
HEAD_SHA="$(git rev-parse HEAD)"
git push github "${HEAD_SHA}:main"
```

Для тегов:

```bash
git push github v0.1.1
```

Не использовать force push без отдельного подтверждения.
