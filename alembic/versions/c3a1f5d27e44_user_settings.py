"""phase5-3 用户级设置（个人设置服务端持久化）

Revision ID: c3a1f5d27e44
Revises: b7d21c4a5f13
Create Date: 2026-10-31 04:10:00.000000

设计说明（Phase5-3 / M2 任务书 4.3）：
  * 新增 user_settings：用户级业务设置（基本资料/通知偏好/简历解析偏好/隐私权限/
    求职意向），一行一用户，payload 为受服务端严格校验的 JSON 分区结构；
  * 主题等纯客户端显示偏好**不入库**；用户偏好绝不写入运维部署配置；
  * 外键 users.id ON DELETE CASCADE：账号删除则设置一并删除（用户隔离边界）。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'c3a1f5d27e44'
down_revision = 'b7d21c4a5f13'
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    op.create_table(
        'user_settings',
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('payload', JSON_TYPE, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade() -> None:
    op.drop_table('user_settings')
