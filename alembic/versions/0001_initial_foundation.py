"""Initial foundation: tenancy tables and catalogs.

Revision ID: 0001
Revises:
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # organizations
    op.create_table(
        "organizations",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("state IN ('active', 'inactive')", name="chk_org_state"),
    )

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="reader"),
        sa.Column("state", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('reader', 'reviewer', 'approver', 'admin')", name="chk_user_role"),
        sa.CheckConstraint("state IN ('active', 'inactive')", name="chk_user_state"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_users_org", "users", ["organization_id"])

    # sessions (ADR-0009)
    op.create_table(
        "sessions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_sessions_user", "sessions", ["user_id"])
    op.create_index("idx_sessions_org", "sessions", ["organization_id"])
    op.create_index("idx_sessions_expires", "sessions", ["expires_at"])

    # currencies (global catalog)
    op.create_table(
        "currencies",
        sa.Column("code", sa.Char(length=3), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("decimals", sa.Integer(), nullable=False, server_default="2"),
        sa.CheckConstraint("decimals >= 0 AND decimals <= 4", name="chk_currency_decimals"),
    )

    # Seed currencies
    op.bulk_insert(
        sa.table("currencies", sa.column("code", sa.Char), sa.column("name", sa.Text), sa.column("decimals", sa.Integer)),
        [
            {"code": "EUR", "name": "Euro", "decimals": 2},
            {"code": "USD", "name": "US Dollar", "decimals": 2},
            {"code": "GBP", "name": "British Pound", "decimals": 2},
        ],
    )

    # tax_rates
    op.create_table(
        "tax_rates",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tax_type", sa.Text(), nullable=False),
        sa.Column("percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("jurisdiction", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("tax_type IN ('vat', 'withholding')", name="chk_tax_rate_type"),
        sa.CheckConstraint("percentage >= 0 AND percentage <= 100", name="chk_tax_rate_pct"),
        sa.CheckConstraint("valid_until IS NULL OR valid_until >= valid_from", name="chk_tax_rate_validity"),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
    )

    # categories
    op.create_table(
        "categories",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("state", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("state IN ('active', 'inactive')", name="chk_cat_state"),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"], ondelete="SET NULL"),
    )

    # payment_methods
    op.create_table(
        "payment_methods",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("state IN ('active', 'inactive')", name="chk_pm_state"),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
    )

    # suppliers
    op.create_table(
        "suppliers",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legal_name", sa.Text(), nullable=False),
        sa.Column("nif_cif", sa.Text(), nullable=False),
        sa.Column("tax_address", sa.Text(), nullable=True),
        sa.Column("contact_data", postgresql.JSONB, nullable=True),
        sa.Column("state", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("state IN ('active', 'inactive')", name="chk_sup_state"),
        sa.ForeignKeyConstraint(["owner_id"], ["organizations.id"], ondelete="RESTRICT"),
    )


def downgrade() -> None:
    op.drop_table("suppliers")
    op.drop_table("payment_methods")
    op.drop_table("categories")
    op.drop_table("tax_rates")
    op.execute("DELETE FROM currencies WHERE code IN ('EUR', 'USD', 'GBP')")
    op.drop_table("currencies")
    op.drop_index("idx_sessions_expires", table_name="sessions")
    op.drop_index("idx_sessions_org", table_name="sessions")
    op.drop_index("idx_sessions_user", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("idx_users_org", table_name="users")
    op.drop_table("users")
    op.drop_table("organizations")
