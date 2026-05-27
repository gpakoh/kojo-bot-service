import hashlib
import hmac
import secrets
import time
from typing import ClassVar


class HMACNonceManager:
    """Manages nonce generation and replay-attack prevention."""

    _used_nonces: ClassVar[set[str]] = set()

    @classmethod
    def generate_nonce(cls) -> str:
        """Generate a cryptographically random nonce (32 hex chars = 16 bytes)."""
        return secrets.token_hex(16)

    @classmethod
    def generate_timestamp(cls) -> int:
        """Return current Unix timestamp."""
        return int(time.time())

    @classmethod
    def validate_nonce(cls, nonce: str, timestamp: int) -> bool:
        """Validate nonce: check expiry (5 min) and replay protection."""
        now = int(time.time())
        if abs(now - timestamp) > 300:
            return False
        if nonce in cls._used_nonces:
            return False
        cls._used_nonces.add(nonce)
        return True


def sign_payload(secret: str, payload: bytes) -> str:
    """Sign payload with HMAC-SHA256, return hex digest."""
    if not secret:
        raise ValueError("HMAC secret must not be empty")
    return hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()


def verify_signature(secret: str, payload: bytes, signature: str) -> bool:
    """Verify HMAC-SHA256 signature against payload."""
    if not secret or not signature:
        return False
    expected = sign_payload(secret, payload)
    return hmac.compare_digest(expected, signature)
