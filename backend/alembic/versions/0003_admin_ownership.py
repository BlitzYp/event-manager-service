"""Add account roles, event ownership, and impersonation metadata.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    admin_columns = {column["name"] for column in inspector.get_columns("admin_users")}
    admin_indexes = {index["name"] for index in inspector.get_indexes("admin_users")}
    if "is_super_admin" not in admin_columns:
        with op.batch_alter_table("admin_users") as batch:
            batch.add_column(
                sa.Column("is_super_admin", sa.Boolean(), nullable=False, server_default=sa.false())
            )
    if "ix_admin_users_is_super_admin" not in admin_indexes:
        op.create_index("ix_admin_users_is_super_admin", "admin_users", ["is_super_admin"])

    # Existing CLI-created administrators already had global access; preserve it.
    op.execute(sa.text("UPDATE admin_users SET is_super_admin = true"))

    inspector = sa.inspect(bind)
    event_columns = {column["name"] for column in inspector.get_columns("events")}
    event_indexes = {index["name"] for index in inspector.get_indexes("events")}
    event_fks = inspector.get_foreign_keys("events")
    if "admin_id" not in event_columns:
        with op.batch_alter_table("events") as batch:
            batch.add_column(sa.Column("admin_id", sa.BigInteger(), nullable=True))
    if "ix_events_admin_id" not in event_indexes:
        op.create_index("ix_events_admin_id", "events", ["admin_id"])
    if not any(fk.get("constrained_columns") == ["admin_id"] for fk in event_fks):
        with op.batch_alter_table("events") as batch:
            batch.create_foreign_key(
                "fk_events_admin_id_admin_users", "admin_users", ["admin_id"], ["id"],
                ondelete="RESTRICT",
            )
    op.execute(
        sa.text(
            "UPDATE events SET admin_id = (SELECT MIN(id) FROM admin_users) "
            "WHERE admin_id IS NULL"
        )
    )

    inspector = sa.inspect(bind)
    session_columns = {column["name"] for column in inspector.get_columns("admin_sessions")}
    session_indexes = {index["name"] for index in inspector.get_indexes("admin_sessions")}
    session_fks = inspector.get_foreign_keys("admin_sessions")
    if "impersonator_admin_id" not in session_columns:
        with op.batch_alter_table("admin_sessions") as batch:
            batch.add_column(sa.Column("impersonator_admin_id", sa.BigInteger(), nullable=True))
    if "ix_admin_sessions_impersonator_admin_id" not in session_indexes:
        op.create_index(
            "ix_admin_sessions_impersonator_admin_id", "admin_sessions", ["impersonator_admin_id"]
        )
    if not any(
        fk.get("constrained_columns") == ["impersonator_admin_id"] for fk in session_fks
    ):
        with op.batch_alter_table("admin_sessions") as batch:
            batch.create_foreign_key(
                "fk_admin_sessions_impersonator_admin_id_admin_users",
                "admin_users",
                ["impersonator_admin_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    with op.batch_alter_table("admin_sessions") as batch:
        batch.drop_constraint(
            "fk_admin_sessions_impersonator_admin_id_admin_users", type_="foreignkey"
        )
        batch.drop_index("ix_admin_sessions_impersonator_admin_id")
        batch.drop_column("impersonator_admin_id")
    with op.batch_alter_table("events") as batch:
        batch.drop_constraint("fk_events_admin_id_admin_users", type_="foreignkey")
        batch.drop_index("ix_events_admin_id")
        batch.drop_column("admin_id")
    with op.batch_alter_table("admin_users") as batch:
        batch.drop_index("ix_admin_users_is_super_admin")
        batch.drop_column("is_super_admin")
