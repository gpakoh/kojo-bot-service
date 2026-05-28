# Gitea Actions Runner Operations

## Host

- **VM:** Wordpress (192.168.1.100, Debian Trixie)
- **Runner binary:** `/usr/local/bin/act_runner` (v0.6.1)
- **Config:** `/etc/act_runner/config.yaml`
- **Registration:** `/root/.runner`
- **Service:** `gitea-actions-runner` (systemd)
- **Gitea instance:** http://192.168.1.103:3005 (access via git.xloud.ru externally)

## Service management

```bash
# Status
systemctl status gitea-actions-runner

# Restart
systemctl restart gitea-actions-runner

# Logs
journalctl -u gitea-actions-runner -n 100 --no-pager
journalctl -u gitea-actions-runner --since '5 min ago' --no-pager
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

A daily cron job restarts the runner at 04:00 MSK (low-traffic window):

```
0 4 * * * /usr/bin/systemctl restart gitea-actions-runner
```

## Re-registration (if `.runner` is lost or token expires)

```bash
act_runner register \
  --instance http://192.168.1.103:3005 \
  --token <registration-token> \
  --name lxc100-runner \
  --labels ubuntu-latest:docker://node:20-bookworm,lxc100-runner:docker://node:20-bookworm
```

Get a registration token from Gitea: Admin → Actions → Runners → Create New Runner.

## Verification

After restart:

```bash
# Check service
systemctl status gitea-actions-runner --no-pager

# Confirm daemon declares successfully (look for "declare successfully")
journalctl -u gitea-actions-runner --since '1 min ago' --no-pager

# Check queued jobs pick up via Gitea API
# Replace credentials with your Gitea username and password/token
curl -u "username:password_or_token" \
  "https://git.xloud.ru/api/v1/repos/gpakoh/kojo-bot-service/actions/runs?page=1&limit=5"
```

## Resources

- Container host: Debian Trixie, 4 vCPU, 8 GB RAM
- Docker storage: `/var/lib/docker` (overlay2)
- Runner logs: systemd journal (not file-based)
