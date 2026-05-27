"""
Multi-source secret loader: Vault Sink > Docker Secrets > Bare-metal File > Environment.
Never reads from .env or committed files.
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


# Priority 0: Vault Agent Sink (rendered Template)
VAULT_SINK = Path("/etc/kojo/vault-secrets.json")
_vault_cache: dict[str, str] | None = None
_vault_cache_mtime: float = 0.0

# Priority 1: Docker Secrets
DOCKER_SECRETS_DIR = Path("/run/secrets")

# Priority 2: Bare-metal Runtime File
BARE_METAL_SECRETS = Path("/etc/kojo/secrets.env")


def _load_vault_sink() -> dict[str, str]:
    """Load secrets from Vault Agent rendered template."""
    global _vault_cache, _vault_cache_mtime

    if not VAULT_SINK.exists():
        _vault_cache = {}
        return {}

    mtime = VAULT_SINK.stat().st_mtime
    if _vault_cache is not None and mtime == _vault_cache_mtime:
        return _vault_cache

    try:
        with open(VAULT_SINK, "r") as f:
            data = json.load(f)
        _vault_cache = {k: str(v) for k, v in data.items() if v is not None}
        _vault_cache_mtime = mtime
        logger.info("Loaded %d secrets from Vault sink", len(_vault_cache))
        return _vault_cache
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load Vault sink: %s", e)
        _vault_cache = {}
        return {}


def get_secret(key: str, default: str = "") -> str:
    """
    Get secret from multi-source: Vault Sink > Docker Secrets > Env > Default.

    Args:
        key: Secret key name
        default: Default value if not found

    Returns:
        Secret value as string
    """
    # Priority 0: Vault Sink
    vault_secrets = _load_vault_sink()
    if key in vault_secrets:
        return vault_secrets[key]

    # Priority 2: Bare-metal Runtime File (/etc/kojo/secrets.env)
    if BARE_METAL_SECRETS.exists():
        try:
            content = BARE_METAL_SECRETS.read_text()
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    if k.strip() == key:
                        return v.strip()
        except OSError as e:
            logger.warning("Failed to load bare-metal secrets: %s", e)

    # Priority 3: Docker Secrets
    docker_secret_path = DOCKER_SECRETS_DIR / key
    if docker_secret_path.exists():
        try:
            return docker_secret_path.read_text().strip()
        except OSError as e:
            logger.warning(f"[databases/kojo/tg_bot/infrastructure/secrets_loader.py] OSError: {e}")

    # Priority 4: Environment Variable
    value = os.environ.get(key)
    if value is not None:
        return value

    # Priority 5: Default
    return default


class SecretsLoader:
    @staticmethod
    def get(key: str, default: str = "") -> str:
        return get_secret(key, default)

    @staticmethod
    def get_required(key: str) -> str:
        return get_required(key)

    @staticmethod
    def get_int(key: str, default: int = 0) -> int:
        value = get_secret(key, str(default))
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def get_bool(key: str, default: bool = False) -> bool:
        value = get_secret(key, default="").lower()
        if value in ("true", "1", "yes", "on"):
            return True
        if value in ("false", "0", "no", "off"):
            return False
        return default


def get_required(key: str) -> str:
    """Get secret, raise RuntimeError if not found."""
    value = get_secret(key, default="")
    if not value:
        raise RuntimeError(f"Required secret '{key}' not found in any source")
    return value



