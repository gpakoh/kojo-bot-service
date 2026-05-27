# Zero-downtime Deploy Checklist (Manifest §7.4)

## Pre-deploy
- [ ] `alembic upgrade head` — migrations applied on staging
- [ ] `pytest tests/` — all green
- [ ] `ruff check tg_bot/ tests/` — 0 errors
- [ ] Docker image built: `docker build -f docker/Dockerfile -t kojo-bot:${VERSION} .`
- [ ] Secrets updated in Docker / bare-metal

## Deploy (Rolling Update)
- [ ] New container starts → readiness probe `/ready` returns 200
- [ ] Old container receives SIGTERM → graceful shutdown (30s max)
- [ ] DB connection pool drained, Redis disconnected
- [ ] Health check confirms old container stopped

## Post-deploy
- [ ] `/health` returns 200
- [ ] `/metrics` returns Prometheus format
- [ ] Test order flow: create → pay → cancel
- [ ] Test AI query: RAG response < 5s
- [ ] Alerting: send test ERROR log, verify Telegram delivery

## Rollback
- [ ] `docker compose down` + `docker compose up` with previous image
- [ ] Or: `systemctl restart kojo-bot` with previous binary
- [ ] Verify rollback within 2 minutes
