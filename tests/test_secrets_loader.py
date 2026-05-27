import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tg_bot.infrastructure.secrets_loader import SecretsLoader


class TestSecretsLoader:
    def test_docker_secret_priority(self, tmp_path) -> None:
        with patch('tg_bot.infrastructure.secrets_loader.VAULT_SINK') as mock_vault:
            mock_vault.exists.return_value = False

            with patch('tg_bot.infrastructure.secrets_loader.DOCKER_SECRETS_DIR', tmp_path):
                secret_file = tmp_path / "TEST_KEY"
                secret_file.write_text("docker_val")

                with patch('tg_bot.infrastructure.secrets_loader.BARE_METAL_SECRETS') as mock_bare:
                    mock_bare.exists.return_value = False

                    with patch.dict(os.environ, {}, clear=True):
                        result = SecretsLoader.get("TEST_KEY")
                        assert result == "docker_val"

    def test_env_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("TEST_KEY", "env_val")
        with patch.object(Path, 'exists', return_value=False):
            result = SecretsLoader.get("TEST_KEY")
            assert result == "env_val"

    def test_default_fallback(self) -> None:
        with patch.object(Path, 'exists', return_value=False):
            result = SecretsLoader.get("MISSING", "default")
            assert result == "default"

    def test_required_raises(self) -> None:
        with patch.object(Path, 'exists', return_value=False):
            with pytest.raises(RuntimeError):
                SecretsLoader.get_required("MISSING")

    def test_get_int(self, monkeypatch) -> None:
        monkeypatch.setenv("PORT", "8080")
        with patch.object(Path, 'exists', return_value=False):
            assert SecretsLoader.get_int("PORT") == 8080

    def test_get_bool_true(self, monkeypatch) -> None:
        monkeypatch.setenv("FLAG", "true")
        with patch.object(Path, 'exists', return_value=False):
            assert SecretsLoader.get_bool("FLAG") is True

    def test_get_bool_false(self, monkeypatch) -> None:
        monkeypatch.setenv("FLAG", "false")
        with patch.object(Path, 'exists', return_value=False):
            assert SecretsLoader.get_bool("FLAG") is False
