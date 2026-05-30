"""Tests for the order rating fields Alembic migration."""
from pathlib import Path


def test_order_rating_migration_is_idempotent() -> None:
    migration_files = sorted(Path("alembic/versions").glob("*rating*.py"))
    assert migration_files, "No rating migration file found in alembic/versions/"

    source = "\n".join(path.read_text(encoding="utf-8") for path in migration_files)

    assert "ADD COLUMN IF NOT EXISTS rating" in source
    assert "ADD COLUMN IF NOT EXISTS rating_comment" in source
    assert "DROP COLUMN IF EXISTS rating_comment" in source
    assert "DROP COLUMN IF EXISTS rating" in source
