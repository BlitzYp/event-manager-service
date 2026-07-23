"""Add event email templates, assets, deliveries, and email actions.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy.types import TypeEngine

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def medium_text() -> TypeEngine:
    return sa.Text().with_variant(mysql.MEDIUMTEXT(), "mysql")


def medium_blob() -> TypeEngine:
    return sa.LargeBinary().with_variant(mysql.MEDIUMBLOB(), "mysql")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    vendor_columns = {column["name"] for column in inspector.get_columns("vendors")}
    if "contract_number" not in vendor_columns:
        with op.batch_alter_table("vendors") as batch:
            batch.add_column(sa.Column("contract_number", sa.String(255), nullable=True))

    if "email_templates" not in tables:
        op.create_table(
            "email_templates",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("event_id", sa.BigInteger(), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("subject", sa.String(255), nullable=False),
            sa.Column("document_json", medium_text(), nullable=False),
            sa.Column("rendered_html", medium_text(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("archived_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.String(255), nullable=False),
            sa.Column("updated_by", sa.String(255), nullable=False),
            sa.Column("archived_by", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "event_id", "name", "archived_at", name="uq_email_template_name"
            ),
        )
        op.create_index("ix_email_templates_event_id", "email_templates", ["event_id"])
        op.create_index("ix_email_templates_archived_at", "email_templates", ["archived_at"])

    if "email_assets" not in tables:
        op.create_table(
            "email_assets",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("event_id", sa.BigInteger(), nullable=False),
            sa.Column("public_token", sa.String(64), nullable=False),
            sa.Column("original_name", sa.String(255), nullable=False),
            sa.Column("mime_type", sa.String(50), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("width", sa.Integer(), nullable=False),
            sa.Column("height", sa.Integer(), nullable=False),
            sa.Column("content", medium_blob(), nullable=False),
            sa.Column("uploaded_by", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("public_token"),
        )
        op.create_index("ix_email_assets_event_id", "email_assets", ["event_id"])
        op.create_index("ix_email_assets_created_at", "email_assets", ["created_at"])

    if "email_deliveries" not in tables:
        op.create_table(
            "email_deliveries",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("event_id", sa.BigInteger(), nullable=False),
            sa.Column("template_id", sa.BigInteger(), nullable=True),
            sa.Column("participant_id", sa.BigInteger(), nullable=True),
            sa.Column("recipient_email", sa.String(320), nullable=False),
            sa.Column("recipient_name", sa.String(255), nullable=True),
            sa.Column("subject", sa.String(255), nullable=False),
            sa.Column(
                "status",
                sa.Enum("sent", "failed", "simulated", native_enum=False),
                nullable=False,
            ),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(
                ["participant_id"], ["participants.id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["template_id"], ["email_templates.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        for name, columns in [
            ("ix_email_deliveries_event_id", ["event_id"]),
            ("ix_email_deliveries_template_id", ["template_id"]),
            ("ix_email_deliveries_participant_id", ["participant_id"]),
            ("ix_email_deliveries_status", ["status"]),
            ("ix_email_deliveries_created_at", ["created_at"]),
            ("ix_email_delivery_event_created", ["event_id", "created_at"]),
        ]:
            op.create_index(name, "email_deliveries", columns)

    inspector = sa.inspect(bind)
    action_columns = {
        column["name"] for column in inspector.get_columns("scheduled_actions")
    }
    for name, column_type in [
        ("email_template_id", sa.BigInteger()),
        ("email_subject", sa.String(255)),
        ("email_html", medium_text()),
    ]:
        if name not in action_columns:
            with op.batch_alter_table("scheduled_actions") as batch:
                batch.add_column(sa.Column(name, column_type, nullable=True))

    inspector = sa.inspect(bind)
    action_indexes = {
        index["name"] for index in inspector.get_indexes("scheduled_actions")
    }
    action_fks = inspector.get_foreign_keys("scheduled_actions")
    with op.batch_alter_table("scheduled_actions") as batch:
        if "ix_scheduled_actions_email_template_id" not in action_indexes:
            batch.create_index(
                "ix_scheduled_actions_email_template_id", ["email_template_id"]
            )
        if not any(
            fk.get("constrained_columns") == ["email_template_id"] for fk in action_fks
        ):
            batch.create_foreign_key(
                "fk_scheduled_actions_email_template",
                "email_templates",
                ["email_template_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    action_columns = {
        column["name"] for column in inspector.get_columns("scheduled_actions")
    }
    if "email_template_id" in action_columns:
        with op.batch_alter_table("scheduled_actions") as batch:
            batch.drop_constraint(
                "fk_scheduled_actions_email_template", type_="foreignkey"
            )
            batch.drop_index("ix_scheduled_actions_email_template_id")
            batch.drop_column("email_html")
            batch.drop_column("email_subject")
            batch.drop_column("email_template_id")
    for table in ["email_deliveries", "email_assets", "email_templates"]:
        if table in inspector.get_table_names():
            op.drop_table(table)
    vendor_columns = {column["name"] for column in inspector.get_columns("vendors")}
    if "contract_number" in vendor_columns:
        with op.batch_alter_table("vendors") as batch:
            batch.drop_column("contract_number")
