"""add order rating fields

Revision ID: bccff3b5b9ff
Revises: 005_tenant_rls
Create Date: 2026-05-30 21:25:54.934496

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bccff3b5b9ff'
down_revision: Union[str, Sequence[str], None] = '005_tenant_rls'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS rating INTEGER")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS rating_comment TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS rating_comment")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS rating")
