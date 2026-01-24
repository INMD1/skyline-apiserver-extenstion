import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = "000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_details",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        ## 수정 가능한 퀄럼
        sa.Column("student_id", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(op.f("ix_user_details_user_id"), "user_details", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_details_user_id"), table_name="user_details")
    op.drop_table("user_details")
