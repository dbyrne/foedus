"""user_github_id_nullable

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-13 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("github_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("github_id", existing_type=sa.Integer(), nullable=False)
