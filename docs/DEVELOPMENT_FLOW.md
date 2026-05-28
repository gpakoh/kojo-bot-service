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

- **push** to any branch matching `main`, `feature/**`, `fix/**`, `chore/**`, `docs/**`, `ci/**`
- **pull_request** targeting `main`

This means CI runs automatically on feature branches before a PR is created, and again when a PR is opened or updated.

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

| Tag | Date | Commit |
|-----|------|--------|
| v0.1.0 | 2026-05-28 | 3c1c9677 |
