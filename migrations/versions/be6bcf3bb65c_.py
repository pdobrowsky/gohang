"""empty message

Revision ID: be6bcf3bb65c
Revises: 
Create Date: 2023-03-02 00:07:56.639271

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'be6bcf3bb65c'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('user',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=True),
    sa.Column('first_name', sa.String(length=255), nullable=True),
    sa.Column('last_name', sa.String(length=255), nullable=True),
    sa.Column('phone_number', sa.String(length=255), nullable=True),
    sa.Column('email', sa.String(length=120), nullable=True),
    sa.Column('user_type', sa.String(length=255), nullable=True),
    sa.Column('max_hang_per_week', sa.Integer(), nullable=True),
    sa.Column('password_hash', sa.String(length=128), nullable=True),
    sa.Column('last_seen', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_email'), ['email'], unique=True)
        batch_op.create_index(batch_op.f('ix_user_phone_number'), ['phone_number'], unique=True)
        batch_op.create_index(batch_op.f('ix_user_user_type'), ['user_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_username'), ['username'], unique=True)

    op.create_table('friend',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('creator_user_id', sa.Integer(), nullable=True),
    sa.Column('friend_user_id', sa.Integer(), nullable=True),
    sa.Column('cadence', sa.Integer(), nullable=True),
    sa.Column('provided_name', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['creator_user_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['friend_user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('friend', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_friend_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_friend_creator_user_id'), ['creator_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_friend_friend_user_id'), ['friend_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_friend_updated_at'), ['updated_at'], unique=False)

    op.create_table('schedule',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('week_of', sa.DateTime(), nullable=True),
    sa.Column('avails', sa.Text(), nullable=True),
    sa.Column('processed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_schedule_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_schedule_processed_at'), ['processed_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_schedule_updated_at'), ['updated_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_schedule_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_schedule_week_of'), ['week_of'], unique=False)

    op.create_table('hang',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id_1', sa.Integer(), nullable=True),
    sa.Column('user_id_2', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('schedule', sa.Text(), nullable=True),
    sa.Column('week_of', sa.Integer(), nullable=True),
    sa.Column('state', sa.String(length=255), nullable=True),
    sa.Column('priority', sa.Float(), nullable=True),
    sa.Column('schedule_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['schedule_id'], ['schedule.id'], ),
    sa.ForeignKeyConstraint(['user_id_1'], ['user.id'], ),
    sa.ForeignKeyConstraint(['user_id_2'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('hang', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_hang_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_hang_priority'), ['priority'], unique=False)
        batch_op.create_index(batch_op.f('ix_hang_state'), ['state'], unique=False)
        batch_op.create_index(batch_op.f('ix_hang_updated_at'), ['updated_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_hang_user_id_1'), ['user_id_1'], unique=False)
        batch_op.create_index(batch_op.f('ix_hang_user_id_2'), ['user_id_2'], unique=False)
        batch_op.create_index(batch_op.f('ix_hang_week_of'), ['week_of'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('hang', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_hang_week_of'))
        batch_op.drop_index(batch_op.f('ix_hang_user_id_2'))
        batch_op.drop_index(batch_op.f('ix_hang_user_id_1'))
        batch_op.drop_index(batch_op.f('ix_hang_updated_at'))
        batch_op.drop_index(batch_op.f('ix_hang_state'))
        batch_op.drop_index(batch_op.f('ix_hang_priority'))
        batch_op.drop_index(batch_op.f('ix_hang_created_at'))

    op.drop_table('hang')
    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_schedule_week_of'))
        batch_op.drop_index(batch_op.f('ix_schedule_user_id'))
        batch_op.drop_index(batch_op.f('ix_schedule_updated_at'))
        batch_op.drop_index(batch_op.f('ix_schedule_processed_at'))
        batch_op.drop_index(batch_op.f('ix_schedule_created_at'))

    op.drop_table('schedule')
    with op.batch_alter_table('friend', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_friend_updated_at'))
        batch_op.drop_index(batch_op.f('ix_friend_friend_user_id'))
        batch_op.drop_index(batch_op.f('ix_friend_creator_user_id'))
        batch_op.drop_index(batch_op.f('ix_friend_created_at'))

    op.drop_table('friend')
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_username'))
        batch_op.drop_index(batch_op.f('ix_user_user_type'))
        batch_op.drop_index(batch_op.f('ix_user_phone_number'))
        batch_op.drop_index(batch_op.f('ix_user_email'))

    op.drop_table('user')
    # ### end Alembic commands ###
