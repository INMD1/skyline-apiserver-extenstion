import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instance_lifecycle",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("instance_id", sa.String(length=64), nullable=False),
        sa.Column("instance_name", sa.String(length=255), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("user_email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.Integer, nullable=False),
        sa.Column("expires_at", sa.Integer, nullable=False),
        sa.Column("email_status", sa.String(length=32), nullable=False, server_default="none"),
        sa.Column("email_sent_at", sa.Integer, nullable=True),
        sa.Column("extended", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index(
        op.f("ix_instance_lifecycle_instance_id"),
        "instance_lifecycle",
        ["instance_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_instance_lifecycle_instance_id"), table_name="instance_lifecycle")
    op.drop_table("instance_lifecycle")
