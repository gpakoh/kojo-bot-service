#!/bin/bash
set -euo pipefail

USER="kojo"
APP_DIR="/opt/kojo"
SECRETS_DIR="/etc/kojo"

echo "Creating user and directories..."
sudo useradd -r -s /bin/false "$USER" 2>/dev/null || true
sudo mkdir -p "$APP_DIR" "$SECRETS_DIR"
sudo chown "$USER:$USER" "$APP_DIR"
sudo chmod 700 "$SECRETS_DIR"

# Create empty secrets file with secure permissions
if [ ! -f "$SECRETS_DIR/secrets.env" ]; then
    sudo touch "$SECRETS_DIR/secrets.env"
    sudo chmod 600 "$SECRETS_DIR/secrets.env"
    echo "Created $SECRETS_DIR/secrets.env with permissions 600"
fi

echo "Installing systemd unit..."
sudo cp deploy/kojo-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kojo-bot

echo "Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if pg_isready -U "${DB_USER:-kojo_user}" -d "${DB_NAME:-kojo_db}" >/dev/null 2>&1; then
        echo "✅ PostgreSQL is ready"
        break
    fi
    echo "⏳ PostgreSQL not ready yet, retrying in 2s... ($i/30)"
    sleep 2
done

echo "Done. Next steps:"
echo "1. Place secrets in $SECRETS_DIR/kojo.env (chmod 600)"
echo "2. Run: sudo systemctl start kojo-bot"
echo "3. Check: sudo journalctl -u kojo-bot -f"
