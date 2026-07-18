"""Add expiry support for short-lived wallet preview tokens.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("wallet_access_tokens")}
    if "expires_at" not in columns:
        op.add_column(
            "wallet_access_tokens",
            sa.Column("expires_at", sa.DateTime(), nullable=True),
        )

    indexes = {index["name"] for index in inspector.get_indexes("wallet_access_tokens")}
    if "ix_wallet_access_tokens_expires_at" not in indexes:
        op.create_index(
            "ix_wallet_access_tokens_expires_at",
            "wallet_access_tokens",
            ["expires_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("wallet_access_tokens")}
    if "ix_wallet_access_tokens_expires_at" in indexes:
        op.drop_index("ix_wallet_access_tokens_expires_at", table_name="wallet_access_tokens")

    columns = {column["name"] for column in inspector.get_columns("wallet_access_tokens")}
    if "expires_at" in columns:
        op.drop_column("wallet_access_tokens", "expires_at")
