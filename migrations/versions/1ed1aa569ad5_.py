"""empty message

Revision ID: 1ed1aa569ad5
Revises: 78ca04337fc8
Create Date: 2023-02-28 23:06:51.082512

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1ed1aa569ad5'
down_revision = '78ca04337fc8'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.add_column(sa.Column('processed_at', sa.DateTime(), nullable=True))
        batch_op.drop_index('ix_schedule_processed')
        batch_op.create_index(batch_op.f('ix_schedule_processed_at'), ['processed_at'], unique=False)
        batch_op.drop_column('processed')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.add_column(sa.Column('processed', sa.BOOLEAN(), nullable=True))
        batch_op.drop_index(batch_op.f('ix_schedule_processed_at'))
        batch_op.create_index('ix_schedule_processed', ['processed'], unique=False)
        batch_op.drop_column('processed_at')

    # ### end Alembic commands ###
