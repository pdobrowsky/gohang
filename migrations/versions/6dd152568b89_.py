"""empty message

Revision ID: 6dd152568b89
Revises: f86803b21533
Create Date: 2023-03-18 12:12:47.065789

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6dd152568b89'
down_revision = 'f86803b21533'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.add_column(sa.Column('week_of_int', sa.Integer(), nullable=True))
        batch_op.drop_index('ix_schedule_week_of')
        batch_op.create_index(batch_op.f('ix_schedule_week_of_int'), ['week_of_int'], unique=False)
        batch_op.drop_column('week_of')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.add_column(sa.Column('week_of', sa.DATETIME(), nullable=True))
        batch_op.drop_index(batch_op.f('ix_schedule_week_of_int'))
        batch_op.create_index('ix_schedule_week_of', ['week_of'], unique=False)
        batch_op.drop_column('week_of_int')

    # ### end Alembic commands ###
