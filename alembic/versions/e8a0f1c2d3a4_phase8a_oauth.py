"""Phase8-A 统一 OAuth 2.0：身份映射 / 授权事务 / 一次性票据 + password_hash 可空

Revision ID: e8a0f1c2d3a4
Revises: d7e8f9a0b1c2
Create Date: 2026-11-01 04:30:00.000000

设计说明（Phase8-A / M3）：
  * oauth_identities：第三方身份 <-> 本站用户映射。
      UNIQUE(provider, client_id, subject) —— 同一平台身份不能绑定两个本站用户；
      client_id 参与唯一键，不同 AppID 的 OpenID 不会意外碰撞。
  * oauth_auth_transactions：短期授权事务（state 只存 SHA-256 摘要 + TTL + 一次性消费
      + 浏览器绑定摘要；PKCE verifier 按平台契约可选落库）。
  * oauth_login_tickets：一次性登录/绑定票据（摘要落库、原子消费、30-60s TTL）。
  * users.password_hash 改为可空：纯 OAuth 账号 password_hash=NULL，
      禁止固定/空/可预测密码占位；既有账号数据不受影响（只放宽约束，不改值）。

回滚纪律（downgrade）：
  * 先删三张 OAuth 表；
  * 再把 password_hash 收回 NOT NULL —— 但若库里存在 password_hash IS NULL 的
    纯 OAuth 账号，**拒绝回滚并显式报错**（不静默删号、不伪造密码），
    运维必须先为这些账号设置密码或导出处置后再回滚。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'e8a0f1c2d3a4'
down_revision = 'd7e8f9a0b1c2'
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    # ---------------- oauth_identities ----------------
    op.create_table(
        'oauth_identities',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('client_id', sa.String(length=128), nullable=False),
        sa.Column('subject', sa.String(length=128), nullable=False),
        sa.Column('union_id', sa.String(length=128), nullable=True),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('avatar_url', sa.String(length=512), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'client_id', 'subject',
                            name='uq_oauth_identities_subject'),
    )
    op.create_index('ix_oauth_identities_user_id', 'oauth_identities', ['user_id'])
    op.create_index('ix_oauth_identities_user_provider', 'oauth_identities',
                    ['user_id', 'provider'])

    # ---------------- oauth_auth_transactions ----------------
    op.create_table(
        'oauth_auth_transactions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('rid', sa.String(length=16), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('mode', sa.String(length=16), nullable=False),
        sa.Column('state_digest', sa.String(length=64), nullable=False),
        sa.Column('browser_binding_digest', sa.String(length=64), nullable=False),
        sa.Column('browser_binding_key', sa.String(length=32), nullable=False),
        sa.Column('initiator_user_id', sa.String(length=36), nullable=True),
        sa.Column('initiator_session_digest', sa.String(length=64), nullable=True),
        sa.Column('redirect_uri', sa.String(length=512), nullable=False),
        sa.Column('return_path', sa.String(length=256), nullable=False),
        sa.Column('code_verifier', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('consumed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['initiator_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rid', name='uq_oauth_tx_rid'),
        sa.UniqueConstraint('state_digest', name='uq_oauth_tx_state_digest'),
    )
    op.create_index('ix_oauth_tx_expires', 'oauth_auth_transactions', ['expires_at'])
    op.create_index('ix_oauth_tx_state', 'oauth_auth_transactions', ['state_digest'])

    # ---------------- oauth_login_tickets ----------------
    op.create_table(
        'oauth_login_tickets',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('ticket_digest', sa.String(length=64), nullable=False),
        sa.Column('mode', sa.String(length=16), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('browser_binding_digest', sa.String(length=64), nullable=False),
        sa.Column('browser_binding_key', sa.String(length=32), nullable=False),
        sa.Column('payload_json', JSON_TYPE, nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('consumed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticket_digest', name='uq_oauth_tickets_digest'),
    )
    op.create_index('ix_oauth_tickets_expires', 'oauth_login_tickets', ['expires_at'])

    # ---------------- users.password_hash -> NULLABLE ----------------
    # 只放宽约束、不改任何既有值：原有账号与 Token 完全不受影响。
    with op.batch_alter_table('users') as batch:
        batch.alter_column('password_hash', existing_type=sa.String(length=255),
                           nullable=True)


def downgrade() -> None:
    # 回滚前置检查：存在纯 OAuth 账号（password_hash IS NULL）时**拒绝**收约束，
    # 避免 NOT NULL 违约或被迫删除/伪造账号数据。
    conn = op.get_bind()
    n = conn.execute(sa.text(
        "SELECT COUNT(*) FROM users WHERE password_hash IS NULL")).scalar() or 0
    if n:
        raise RuntimeError(
            f"拒绝回滚：存在 {n} 个 password_hash IS NULL 的纯 OAuth 账号。"
            "请先为这些账号设置本站密码或导出处置后再执行 downgrade"
            "（回滚不得静默删号/伪造密码）。")

    op.drop_table('oauth_login_tickets')
    op.drop_table('oauth_auth_transactions')
    op.drop_table('oauth_identities')

    with op.batch_alter_table('users') as batch:
        batch.alter_column('password_hash', existing_type=sa.String(length=255),
                           nullable=False)
