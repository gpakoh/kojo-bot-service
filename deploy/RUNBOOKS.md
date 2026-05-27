# Operations Runbooks

## Alert: Circuit Breaker OPEN
1. Check `/metrics` — `kojo_proxy_failover_count` spikes
2. Check logs: `grep "Circuit.*OPEN" logs/`
3. Verify upstream: `curl http://quart-server:5000/health`
4. If upstream down — restart Quart container
5. If upstream OK but CB stuck — `clear_circuit_breakers()` via admin command

## Alert: DB Connection Pool Exhausted
1. Check `/ready` — PostgreSQL status
2. Check `pg_stat_activity` for idle connections
3. Restart bot container (graceful shutdown closes pool)
4. If persistent — increase `max_size` in `DatabaseManager`

## Alert: High Latency (>5s)
1. Check `kojo_llm_latency_seconds` histogram
2. If LLM slow — check GPU utilization (`nvidia-smi`)
3. If DB slow — check `kojo_db_query_duration_seconds`
4. If proxy slow — check `kojo_proxy_failover_count`

## Rollback Procedure
1. `docker compose down`
2. `docker compose up -d --build` with previous image tag
3. Verify `/health` and `/ready`
4. Run smoke test: create order — AI query
