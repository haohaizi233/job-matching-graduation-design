"""phase5-3 推荐降级信息持久化（模型不可用降级可追溯）

Revision ID: d7e8f9a0b1c2
Revises: c3a1f5d27e44
Create Date: 2026-10-31 12:20:00.000000

设计说明（Phase5-3 / M5 任务书第七节）：
  * recommendation_runs 增加 degradation_info（JSON，可空）——记录当次推荐是否发生
    「模型不可用 -> 显式降级 Baseline」及原因码/请求模型/失败分类；
  * 降级必须可追溯：历史记录不得在事后显示"未降级"而掩盖真实降级（只加不减）；
  * 未降级的运行保持 NULL，不做任何乐观回填。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'd7e8f9a0b1c2'
down_revision = 'c3a1f5d27e44'
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    op.add_column('recommendation_runs',
                  sa.Column('degradation_info', JSON_TYPE, nullable=True))


def downgrade() -> None:
    op.drop_column('recommendation_runs', 'degradation_info')
