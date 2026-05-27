"""Integration tests for HMAC signing and nonce management."""
from typing import Any

from tg_bot.infrastructure.hmac_signing import (
    HMACNonceManager,
    sign_payload,
    verify_signature,
)


class TestSignPayload:
    def test_basic_signing(self) -> Any:
        secret = "my_secret"
        payload = b'{"test": 1}'
        sig = sign_payload(secret, payload)
        assert len(sig) == 64  # SHA-256 hex
        assert verify_signature(secret, payload, sig) is True

    def test_verify_wrong_secret_fails(self) -> Any:
        sig = sign_payload("secret", b"payload")
        assert verify_signature("wrong", b"payload", sig) is False

    def test_verify_wrong_payload_fails(self) -> Any:
        sig = sign_payload("secret", b"payload")
        assert verify_signature("secret", b"other", sig) is False

    def test_empty_payload(self) -> Any:
        sig = sign_payload("secret", b"")
        assert verify_signature("secret", b"", sig) is True

    def test_unicode_payload(self) -> Any:
        payload = '{"name": "Кофе Эфиопия"}'.encode("utf-8")
        sig = sign_payload("secret", payload)
        assert verify_signature("secret", payload, sig) is True


class TestHMACNonceManager:
    def test_generate_nonce_unique(self) -> Any:
        n1 = HMACNonceManager.generate_nonce()
        n2 = HMACNonceManager.generate_nonce()
        assert n1 != n2
        assert len(n1) == 32  # hex of 16 bytes

    def test_timestamp_recent(self) -> Any:
        ts = HMACNonceManager.generate_timestamp()
        import time
        assert abs(ts - int(time.time())) < 5

    def test_validate_nonce_success(self) -> Any:
        nonce = HMACNonceManager.generate_nonce()
        ts = HMACNonceManager.generate_timestamp()
        assert HMACNonceManager.validate_nonce(nonce, ts) is True

    def test_validate_nonce_replay_fails(self) -> Any:
        nonce = "reused_nonce"
        ts = HMACNonceManager.generate_timestamp()
        assert HMACNonceManager.validate_nonce(nonce, ts) is True
        # Second Use — Replay
        assert HMACNonceManager.validate_nonce(nonce, ts) is False

    def test_validate_nonce_expired(self) -> Any:
        nonce = HMACNonceManager.generate_nonce()
        old_ts = HMACNonceManager.generate_timestamp() - 400  # > 5 min
        assert HMACNonceManager.validate_nonce(nonce, old_ts) is False
