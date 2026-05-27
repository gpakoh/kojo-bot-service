# Tests For Gitignore And Config Safety
from pathlib import Path
from typing import Any

import pytest


class TestGitignore:
    @pytest.fixture
    def repo_root(self, tmp_path) -> Any:
        project_root = Path(__file__).resolve().parents[2]
        return project_root

    def test_bak_files_excluded(self, repo_root) -> Any:
        gitignore = repo_root / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            assert "*.bak" in content
            assert ".env" in content

    def test_no_secrets_in_config(self, repo_root) -> Any:
        config = repo_root / "config" / "config.json"
        if config.exists():
            import json
            data = json.loads(config.read_text())
            sensitive_keys = ['password', 'token', 'secret', 'key']
            for key in data.keys():
                if any(s in key.lower() for s in sensitive_keys):
                    assert data[key] == "" or data[key] is False, f"Found sensitive key: {key}"

    def test_env_file_exists(self, repo_root) -> Any:
        env = repo_root / ".env"
        assert not env.exists() or env.is_file()

    def test_gitignore_includes_pycache(self, repo_root) -> Any:
        gitignore = repo_root / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            assert "__pycache__/" in content
