import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from utils.env_utils import update_env_variable


class TestUpdateEnvVariable:
    def test_normal_update_key_exists_replace(self) -> Any:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".env", delete=False) as f:
            f.write("EXISTING_KEY=old_value\nOTHER_KEY=keep_me\n")
            env_path = f.name

        try:
            result = update_env_variable("EXISTING_KEY", "new_value", env_path=env_path)
            assert result is None

            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()

            assert "EXISTING_KEY=new_value" in content
            assert "OTHER_KEY=keep_me" in content
            assert os.environ.get("EXISTING_KEY") == "new_value"
        finally:
            Path(env_path).unlink(missing_ok=True)
            os.environ.pop("EXISTING_KEY", None)

    def test_new_key_added(self) -> Any:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".env", delete=False) as f:
            f.write("OTHER_KEY=keep_me\n")
            env_path = f.name

        try:
            update_env_variable("NEW_KEY", "new_value", env_path=env_path)

            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()

            assert "NEW_KEY=new_value" in content
            assert "OTHER_KEY=keep_me" in content
        finally:
            Path(env_path).unlink(missing_ok=True)
            os.environ.pop("NEW_KEY", None)
            os.environ.pop("OTHER_KEY", None)

    def test_file_does_not_exist_creates_new(self) -> Any:
        env_path = "/tmp/__test_non_existent_env_file__.env"
        Path(env_path).unlink(missing_ok=True)

        try:
            update_env_variable("BRAND_NEW", "hello", env_path=env_path)

            assert Path(env_path).exists()
            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()

            assert "BRAND_NEW=hello" in content
            assert os.environ.get("BRAND_NEW") == "hello"
        finally:
            Path(env_path).unlink(missing_ok=True)
            os.environ.pop("BRAND_NEW", None)

    def test_exception_on_file_read_creates_new(self, fs) -> Any:
        fs.create_file("/tmp/test_read_fail.env", contents="OLD=val\n")
        update_env_variable("AFTER_ERROR", "works", env_path="/tmp/test_read_fail.env")
        with open("/tmp/test_read_fail.env", "r") as f:
            content = f.read()
        assert "AFTER_ERROR=works" in content
        assert "OLD=val" in content
        os.environ.pop("AFTER_ERROR", None)

    def test_exception_on_file_write_logged(self) -> Any:
        with tempfile.NamedTemporaryFile(suffix=".env", delete=False) as f:
            env_path = f.name

        try:
            with patch("builtins.open", side_effect=PermissionError("write denied")):
                update_env_variable("WRITE_FAIL", "val", env_path=env_path)

            assert os.environ.get("WRITE_FAIL") == "val"
        finally:
            Path(env_path).unlink(missing_ok=True)
            os.environ.pop("WRITE_FAIL", None)

    def test_updates_os_environ_immediately(self) -> Any:
        with tempfile.NamedTemporaryFile(suffix=".env", delete=False) as f:
            env_path = f.name

        try:
            update_env_variable("IMMEDIATE_CHECK", "instant", env_path=env_path)
            assert os.environ.get("IMMEDIATE_CHECK") == "instant"
        finally:
            Path(env_path).unlink(missing_ok=True)
            os.environ.pop("IMMEDIATE_CHECK", None)

    def test_preserves_other_lines_when_replacing(self) -> Any:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".env", delete=False) as f:
            f.write("A=1\nB=2\nC=3\n")
            env_path = f.name

        try:
            update_env_variable("B", "22", env_path=env_path)

            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            assert len(lines) == 3
            assert lines[0].strip() == "A=1"
            assert lines[1].strip() == "B=22"
            assert lines[2].strip() == "C=3"
        finally:
            Path(env_path).unlink(missing_ok=True)
            os.environ.pop("A", None)
            os.environ.pop("B", None)
            os.environ.pop("C", None)

    def test_adds_newline_to_last_line_when_missing(self) -> Any:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".env", delete=False) as f:
            f.write("EXISTING=val")
            env_path = f.name

        try:
            update_env_variable("NEW_KEY", "new_val", env_path=env_path)

            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()

            assert "EXISTING=val\nNEW_KEY=new_val\n" in content
        finally:
            Path(env_path).unlink(missing_ok=True)
            os.environ.pop("EXISTING", None)
            os.environ.pop("NEW_KEY", None)
