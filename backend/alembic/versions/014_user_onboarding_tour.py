"""Per-user welcome-tour completion state.

Revision ID: 014_user_onboarding_tour
Revises: 013_api_tokens
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "014_user_onboarding_tour"
down_revision = "013_api_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing installations are established users and must not receive a tour
    # solely because they upgraded. New users get the runtime default of zero.
    op.add_column(
        "users",
        sa.Column("onboarding_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.alter_column("users", "onboarding_version", server_default="0")
    op.execute("DELETE FROM app_settings WHERE key = 'instance_onboarding'")


def downgrade() -> None:
    op.drop_column("users", "onboarding_version")
