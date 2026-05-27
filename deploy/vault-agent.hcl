# Vault Agent configuration for Kojo Bot
# Runs as sidecar: fetches secrets and writes to sink file.

vault {
  address = "http://127.0.0.1:8200"  # local Vault server or cluster
  retry {
    num_retries = 5
  }
}

auto_auth {
  method {
    type = "approle"
    config = {
      role_id_file_path   = "/etc/vault/role-id"
      secret_id_file_path = "/etc/vault/secret-id"
      remove_secret_id_file_after_reading = false
    }
  }
  sink {
    type = "file"
    config = {
      path = "/etc/vault/token"
    }
  }
}

template {
  destination = "/etc/kojo/vault-secrets.json"
  command     = "/bin/kill -HUP $(systemctl show --property=MainPID --value kojo-bot)"  
  
  contents = <<EOT
{
  "BOT_TOKEN": "{{ with secret "secret/data/kojo/bot" }}{{ .Data.data.token }}{{ end }}",
  "DATABASE_URL": "{{ with secret "secret/data/kojo/db" }}{{ .Data.data.url }}{{ end }}",
  "ADMIN_CHAT_ID": "{{ with secret "secret/data/kojo/bot" }}{{ .Data.data.admin_chat_id }}{{ end }}",
  "INTERNAL_SHARED_SECRET": "{{ with secret "secret/data/kojo/internal" }}{{ .Data.data.secret }}{{ end }}"
}
EOT
}

# Renew token automatically
cache {
  use_auto_auth_token = true
}
