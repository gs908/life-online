"""initial_schema

Revision ID: 4bb73fc2e250
Revises:
Create Date: 2026-07-06 04:36:31.778948

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from app.common.db.base import Base
import app.models  # noqa: F401 - register all model tables in Base.metadata


# revision identifiers, used by Alembic.
revision: str = "4bb73fc2e250"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the current sys_* / scn_* initial schema."""
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=False)


def downgrade() -> None:
    """Drop the current sys_* / scn_* initial schema."""
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=False)
