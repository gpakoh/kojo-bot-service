# Gitea Actions Runner Operations

## Host

- **VM:** Wordpress (192.168.1.100, Debian Trixie)
- **Runner binary:** `/usr/local/bin/act_runner` (v0.6.1)
- **Gitea instance:** http://192.168.1.103:3005 (access via git.xloud.ru externally)

## Runners

### 1. `lxc100-runner` (shared, legacy)

- **Service:** `gitea-actions-runner` (systemd)
- **Config:** `/etc/act_runner/config.yaml`
- **Registration:** `/root/.runner`
- **Labels:** `ubuntu-latest`, `lxc100-runner`
- **Capacity:** 1
- **Base image:** `node:20-bookworm`
- **Назначение:** Quart-core CI и любые другие jobs без явного `runs-on`

### 2. `kojo-runner` (dedicated)

- **Service:** `gitea-actions-runner-kojo` (systemd)
- **Config:** `/etc/act_runner/config-kojo.yaml`
- **Registration:** `/etc/act_runner/.runner-kojo`
- **Labels:** `kojo` (только этот лейбл)
- **Capacity:** 1
- **Base image:** `nikolaik/python-nodejs:python3.12-nodejs24`
- **Назначение:** Только Kojo CI (`runs-on: kojo`)
- **Изоляция:** Не конкурирует с Quart-core — собственный polling loop

## Service management

```bash
# Status — both runners
systemctl status gitea-actions-runner       # lxc100-runner
systemctl status gitea-actions-runner-kojo  # kojo-runner

# Restart
systemctl restart gitea-actions-runner       # lxc100-runner
systemctl restart gitea-actions-runner-kojo  # kojo-runner

# Logs
journalctl -u gitea-actions-runner -n 100 --no-pager
journalctl -u gitea-actions-runner --since '5 min ago' --no-pager
journalctl -u gitea-actions-runner-kojo -n 100 --no-pager
```

## Symptom: jobs stuck in `queued` indefinitely

The runner process stays alive (systemd shows `active (running)`, PID responds to signals) but stops fetching new tasks from Gitea. Journal shows no new log entries since the last processed task.

**Root cause:** HTTP client in act_runner v0.6.1 stalls silently — likely a hung connection pool or blocked polling loop. Process remains alive, uses minimal CPU/memory, but never fetches new tasks.

**Fix:** Restart the service:

```bash
systemctl restart gitea-actions-runner
```

After restart, the runner re-declares itself and picks up queued jobs within seconds.

## Prevention

A daily cron job restarts both runners at 04:00 MSK (low-traffic window):

```
0 4 * * * /usr/bin/systemctl restart gitea-actions-runner; /usr/bin/systemctl restart gitea-actions-runner-kojo
```

## Re-registration (if `.runner` file is lost or token expires)

### lxc100-runner

```bash
act_runner register \
  --instance http://192.168.1.103:3005 \
  --token <registration-token> \
  --name lxc100-runner \
  --labels ubuntu-latest:docker://node:20-bookworm,lxc100-runner:docker://node:20-bookworm
```

### kojo-runner

```bash
act_runner register \
  --instance http://192.168.1.103:3005 \
  --token <registration-token> \
  --name kojo-runner \
  --labels kojo:docker://nikolaik/python-nodejs:python3.12-nodejs24
# После регистрации переместить .runner в /etc/act_runner/.runner-kojo
```

### Получение токена

```bash
curl -X POST -s --noproxy '*' -u "gpakoh:password" \
  "http://192.168.1.103:3005/api/v1/admin/actions/runners/registration-token" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])"
```

Или через UI: Admin → Actions → Runners → Create New Runner.

## Verification

### Services

```bash
# Check both services
systemctl status gitea-actions-runner --no-pager
systemctl status gitea-actions-runner-kojo --no-pager

# Confirm daemon declares successfully (look for "declare successfully")
journalctl -u gitea-actions-runner --since '1 min ago' --no-pager
journalctl -u gitea-actions-runner-kojo --since '1 min ago' --no-pager

# Both PIDs
ps aux | grep act_runner | grep -v grep
```

### API — список runners

```bash
curl -s --noproxy '*' -u "gpakoh:password" \
  "http://192.168.1.103:3005/api/v1/admin/actions/runners" \
  | python3 -c "import json,sys; [print(f'{r[\"name\"]}: {r[\"status\"]} — labels={[l[\"name\"] for l in r[\"labels\"]]}') for r in json.load(sys.stdin)['runners']]"
```

### API — очередь CI

```bash
curl -s --noproxy '*' -u "gpakoh:password" \
  "http://192.168.1.103:3005/api/v1/repos/gpakoh/kojo-bot-service/actions/runs?page=1&limit=5" \
  | python3 -c "import json,sys; [print(f'#{r[\"id\"]}: {r[\"status\"]} {r.get(\"conclusion\",\"?\")} — {r[\"event\"]} — {r.get(\"head_branch\",\"?\")}') for r in json.load(sys.stdin).get('workflow_runs',[])]"
```

## Resources

- Container host: Debian Trixie, 4 vCPU, 8 GB RAM
- Docker storage: `/var/lib/docker` (overlay2)
- Runner logs: systemd journal (not file-based)
