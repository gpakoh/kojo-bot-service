# Kojo Bot Service — Releases

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
