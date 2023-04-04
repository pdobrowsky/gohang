"""empty message

Revision ID: f565a781baf4
Revises: b4769fd28e99
Create Date: 2023-04-03 22:00:15.945278

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f565a781baf4'
down_revision = 'b4769fd28e99'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_index('ix_user_username')
        batch_op.drop_column('username')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('username', sa.VARCHAR(length=64), nullable=True))
        batch_op.create_index('ix_user_username', ['username'], unique=False)

    # ### end Alembic commands ###
