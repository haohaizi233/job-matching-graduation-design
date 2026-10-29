"""phase5-2r 业务一致性字段（岗位画像失效 / 数据来源 / 推荐幂等 / 文件生命周期）

Revision ID: b7d21c4a5f13
Revises: 99510af3982b
Create Date: 2026-10-29 16:45:00.000000

设计说明（Phase5-2R）：
  * jobs 增加 job_content_hash / profile_source_hash / profile_status / profile_error /
    parser_version —— 解决"JD 改了但旧结构化画像继续被推荐使用"（P0-01）；
  * jobs / resumes 增加 data_source / data_source_declared / source_audit —— 解决
    "真实岗位被硬编码标为合成"（P1-03）；来源声明可审计；
  * recommendation_runs 增加 request_semantic_hash / idempotency_key / profile_content_hash
    —— 解决"幂等指纹不完整导致错误复用"（P0-02）；
  * recommendation_items 增加 job_content_hash / profile_status_at_run —— 历史解释证据快照（P2）；
  * resumes 增加 storage_key 索引 —— 文件生命周期引用检查/孤儿扫描（P1-04）。

存量数据回填口径（**保守且诚实**，不做乐观假设）：
  * job_content_hash 由现有 title + job_description 现算（内容哈希无历史值可考）；
  * 已有 structured_profile 的岗位一律回填 profile_status='needs_reparse'、
    profile_source_hash=NULL —— 旧实现允许"改 JD 不失效画像"，因此**无法证明**
    既有画像与当前 JD 对应；在重新解析成功前不得作为可信解析结果参与推荐。
    一次性重新解析（POST /api/v1/jobs/{id}/parse）即可恢复。
  * data_source 仅在来源字段明确声明合成时回填 'synthetic'，许可明确时回填
    'licensed_dataset'，其余一律 'unknown'（不冒充授权数据、不臆造 user_provided）。
"""
from __future__ import annotations

import hashlib
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'b7d21c4a5f13'
down_revision = '99510af3982b'
branch_labels = None
depends_on = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def _content_hash(title: str, jd: str) -> str:
    """与 job_store.job_content_hash 同口径：规范化 JSON -> SHA-256。"""
    payload = json.dumps({"title": str(title or ""), "job_description": str(jd or "")},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _legacy_data_source(source: str, license_: str) -> str:
    s = (str(source or "") + " " + str(license_ or "")).lower()
    if "synthetic" in s or "合成" in s or "mock" in s:
        return "synthetic"
    lic = str(license_ or "").strip()
    if lic and lic.upper() not in ("UNKNOWN", "UNLICENSED", "NONE", "N/A"):
        return "licensed_dataset"
    return "unknown"


def upgrade() -> None:
    # ---------------- jobs ----------------
    op.add_column('jobs', sa.Column('job_content_hash', sa.String(length=64),
                                    nullable=False, server_default=''))
    op.add_column('jobs', sa.Column('profile_source_hash', sa.String(length=64), nullable=True))
    op.add_column('jobs', sa.Column('profile_status', sa.String(length=16),
                                    nullable=False, server_default='unparsed'))
    op.add_column('jobs', sa.Column('profile_error', sa.String(length=512), nullable=True))
    op.add_column('jobs', sa.Column('parser_version', sa.String(length=32), nullable=True))
    op.add_column('jobs', sa.Column('data_source', sa.String(length=24),
                                    nullable=False, server_default='unknown'))
    op.add_column('jobs', sa.Column('data_source_declared', sa.Integer(),
                                    nullable=False, server_default='0'))
    op.add_column('jobs', sa.Column('data_source_declared_by', sa.String(length=64),
                                    nullable=True))
    op.add_column('jobs', sa.Column('data_source_declared_at', sa.DateTime(), nullable=True))
    op.add_column('jobs', sa.Column('source_audit', JSON_TYPE, nullable=False,
                                    server_default='[]'))
    op.create_index('ix_jobs_status_profile_status', 'jobs', ['status', 'profile_status'],
                    unique=False)

    # ---------------- resumes ----------------
    op.add_column('resumes', sa.Column('data_source', sa.String(length=24),
                                       nullable=False, server_default='unknown'))
    op.add_column('resumes', sa.Column('data_source_declared', sa.Integer(),
                                       nullable=False, server_default='0'))
    op.add_column('resumes', sa.Column('source_audit', JSON_TYPE, nullable=False,
                                       server_default='[]'))
    op.create_index('ix_resumes_storage_key', 'resumes', ['storage_key'], unique=False)

    # ---------------- recommendation_runs ----------------
    # 注：新增唯一性用 **唯一索引** 表达（不是 ADD CONSTRAINT）。
    # 原因：SQLite 的 ALTER TABLE 不支持 ADD CONSTRAINT，而 batch 模式会重建
    # recommendation_runs 表，存在被 recommendation_items 外键引用的结构风险。
    # 唯一索引在 SQLite / PostgreSQL 上都由数据库强制，IntegrityError 同样携带该名字，
    # 满足"数据库唯一约束 + 明确事务处理"的并发控制要求（P0-02）。
    op.add_column('recommendation_runs',
                  sa.Column('request_semantic_hash', sa.String(length=64),
                            nullable=False, server_default=''))
    op.add_column('recommendation_runs',
                  sa.Column('idempotency_key', sa.String(length=128), nullable=True))
    op.add_column('recommendation_runs',
                  sa.Column('profile_content_hash', sa.String(length=64), nullable=True))
    op.create_index('uq_reco_runs_user_idem_key', 'recommendation_runs',
                    ['user_id', 'idempotency_key'], unique=True)

    # ---------------- recommendation_items ----------------
    op.add_column('recommendation_items',
                  sa.Column('job_content_hash', sa.String(length=64), nullable=True))
    op.add_column('recommendation_items',
                  sa.Column('profile_status_at_run', sa.String(length=16), nullable=True))

    # ---------------- 存量数据回填（保守口径） ----------------
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, title, job_description, structured_profile, source, source_license "
        "FROM jobs")).fetchall()
    for row in rows:
        jid, title, jd, sp, source, license_ = row
        ch = _content_hash(title, jd)
        has_profile = sp is not None and sp != '' and sp != {}
        bind.execute(
            sa.text("UPDATE jobs SET job_content_hash = :ch, "
                    "profile_status = :ps, profile_source_hash = NULL, "
                    "parser_version = NULL, data_source = :ds "
                    "WHERE id = :id"),
            {"ch": ch,
             "ps": ("needs_reparse" if has_profile else "unparsed"),
             "ds": _legacy_data_source(source, license_),
             "id": jid})
    # resumes 存量行无法回溯上传声明 -> 一律 unknown（不臆造来源）
    bind.execute(sa.text("UPDATE resumes SET data_source = 'unknown' "
                         "WHERE data_source IS NULL OR data_source = ''"))
    # recommendation_runs 存量行语义指纹无历史值可考 -> 置空串；
    # request_fingerprint 保持原值不动（历史唯一约束不破坏）。
    # 注：新列保留 server_default 作为原始 SQL 写入的兜底值（ORM 每次都显式赋值，
    # 不依赖数据库默认值），避免 SQLite 无法 ALTER DEFAULT 的重建表风险。


def downgrade() -> None:
    op.drop_column('recommendation_items', 'profile_status_at_run')
    op.drop_column('recommendation_items', 'job_content_hash')
    op.drop_index('uq_reco_runs_user_idem_key', table_name='recommendation_runs')
    op.drop_column('recommendation_runs', 'profile_content_hash')
    op.drop_column('recommendation_runs', 'idempotency_key')
    op.drop_column('recommendation_runs', 'request_semantic_hash')
    op.drop_index('ix_resumes_storage_key', table_name='resumes')
    op.drop_column('resumes', 'source_audit')
    op.drop_column('resumes', 'data_source_declared')
    op.drop_column('resumes', 'data_source')
    op.drop_index('ix_jobs_status_profile_status', table_name='jobs')
    op.drop_column('jobs', 'source_audit')
    op.drop_column('jobs', 'data_source_declared_at')
    op.drop_column('jobs', 'data_source_declared_by')
    op.drop_column('jobs', 'data_source_declared')
    op.drop_column('jobs', 'data_source')
    op.drop_column('jobs', 'parser_version')
    op.drop_column('jobs', 'profile_error')
    op.drop_column('jobs', 'profile_status')
    op.drop_column('jobs', 'profile_source_hash')
    op.drop_column('jobs', 'job_content_hash')
