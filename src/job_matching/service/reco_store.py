# -*- coding: utf-8 -*-
"""推荐执行、历史快照与反馈闭环（Phase5-2 / Batch 4.2–4.4）。

评分复用纪律（任务 6.2）：
  * 排序计算**只**经 Phase5-1 `MatchingService.rank()`，禁止另写一套数据库版匹配逻辑；
  * 分数语义不变：heuristic_score / model_raw_score 是排序参考分，**不是录用概率**；
  * 结果解释直接存 `build_match_result` 的快照，不二次加工证据。

快照纪律（任务 6.3）：每次运行保存 学生画像版本 / 参与岗位集合与版本 /
评分方法 / 模型版本 / 配置版本 / 排序 / 分数类型 / 解释 / 运行时间与状态。
之后无论简历被修改还是 JD 被更新，历史推荐仍可完整解释。

反馈纪律（任务 6.4）：反馈是**用户业务反馈**；未经独立标注协议与数据质量审核，
禁止自动转化为人工 Gold 标签（反馈对象只落 recommendation_feedback）。

事务纪律：运行记录 + 条目在同一事务写入；评分失败不落任何行（无半成功记录）。
重复提交：同用户同请求指纹只保留一条运行记录（幂等返回既有运行）。
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime
from typing import Callable

from ..infra.persistence import (Job, RecommendationFeedback, RecommendationItem,
                                 RecommendationRun, get_session_factory,
                                 session_scope)
from .contracts import StudentProfile as StudentProfileContract
from .errors import ServiceError

FEEDBACK_TYPES = ("interested", "not_interested", "applied", "interview", "irrelevant")
MAX_TOP_K = 200
MAX_PAGE_SIZE = 100


def _now() -> datetime:
    return datetime.utcnow()


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


class RecommendationService:
    """推荐闭环服务（画像 -> 岗位 -> MatchingService.rank -> 快照 -> 反馈）。"""

    def __init__(self, *, services, job_service, profile_service,
                 session_factory: Callable | None = None):
        self._services = services
        self._jobs = job_service
        self._profiles = profile_service
        self._session_factory = session_factory or get_session_factory()

    # ============================================================ 执行
    def run(self, user: dict, *, mode: str = "baseline", top_k: int | None = None,
            job_ids: list[str] | None = None, category: str | None = None,
            city: str | None = None, model_id: str | None = None,
            allow_fallback: bool = True,
            idempotency_key: str | None = None) -> dict:
        t0 = time.monotonic()
        # 1) 读取**已确认**的学生画像
        prof = self._profiles.latest_profile(user)
        if not prof.get("confirmed"):
            raise ServiceError("INVALID_REQUEST",
                               "请先确认学生画像（POST /api/v1/students/me/profile confirm=true）")
        profile_data = dict(prof.get("profile_data") or {})
        profile_dict = profile_data.get("profile") or {}
        try:
            student = StudentProfileContract.from_dict(profile_dict)
        except (ValueError, KeyError) as e:
            raise ServiceError("MODEL_INAPPLICABLE",
                               f"学生画像无法用于匹配: {e}") from e

        # 2) 查询符合基础过滤条件的岗位（已发布 + 已解析画像）
        pairs = self._jobs.matchable_jobs(job_ids)
        if category:
            pairs = [(j, p) for j, p in pairs if j.job_category == category]
        if city:
            pairs = [(j, p) for j, p in pairs if j.city == city]
        if not pairs:
            raise ServiceError("NOT_FOUND", "没有符合过滤条件且已解析画像的岗位")

        job_profiles = [p for _j, p in pairs]
        job_set_snapshot = [
            {"job_id": j.id, "title": j.title, "job_category": j.job_category,
             "city": j.city, "updated_at": _iso(j.updated_at),
             "profile_snapshot_version": self._job_snapshot_version(j)}
            for j, _p in pairs]

        # 3) 复用 Phase5-1 评分（不重写匹配逻辑；score_type 语义不变）
        options = {"mode": mode, "allow_fallback": bool(allow_fallback)}
        if model_id:
            options["model_id"] = model_id
        if top_k is not None:
            options["top_k"] = max(1, min(MAX_TOP_K, int(top_k)))
        try:
            result = self._services.matching.rank(student, job_profiles, options)
        except ServiceError:
            raise
        except Exception as e:  # noqa: BLE001
            # 评分失败：不落任何行（无半成功业务记录）
            raise ServiceError("INTERNAL_ERROR", f"推荐执行失败: {e}") from e

        # 4) 指纹（重复提交幂等）
        fingerprint = self._fingerprint(
            user_id=user["id"], profile_version=prof["profile_version"],
            mode=mode, top_k=options.get("top_k"), model_id=model_id or "",
            job_ids=[j.id for j, _p in pairs], idempotency_key=idempotency_key)

        runtime_ms = round((time.monotonic() - t0) * 1000, 3)
        run_out, created = self._persist_run(
            user=user, prof=prof, pairs=pairs, result=result,
            fingerprint=fingerprint, runtime_ms=runtime_ms)
        return {"run": run_out, "created": created,
                "result_summary": {
                    "mode": result.get("mode"),
                    "scoring_method": result.get("scoring_method"),
                    "score_type": result.get("score_type"),
                    "model_version": result.get("model_version"),
                    "evaluation_status": result.get("evaluation_status"),
                    "formal_evaluation": result.get("formal_evaluation"),
                    "warnings": result.get("warnings", [])}}

    # ============================================================ 历史
    def history(self, user: dict, *, page: int = 1, page_size: int = 20) -> dict:
        page = max(1, int(page))
        page_size = min(MAX_PAGE_SIZE, max(1, int(page_size)))
        session = self._session_factory()
        try:
            query = (session.query(RecommendationRun)
                     .filter(RecommendationRun.user_id == user["id"]))
            total = query.count()
            rows = (query.order_by(RecommendationRun.created_at.desc())
                    .offset((page - 1) * page_size).limit(page_size).all())
            items = [self._run_row(session, r, with_items=False) for r in rows]
            return {"items": items, "page": page, "page_size": page_size, "total": total}
        finally:
            session.close()

    def get_run(self, user: dict, run_id: str) -> dict:
        session = self._session_factory()
        try:
            row = (session.query(RecommendationRun)
                   .filter(RecommendationRun.id == run_id,
                           RecommendationRun.user_id == user["id"]).first())
            if row is None:
                # 越权/不存在统一 404（防资源枚举）
                raise ServiceError("NOT_FOUND", "推荐运行不存在")
            return self._run_row(session, row, with_items=True)
        finally:
            session.close()

    # ============================================================ 反馈
    def submit_feedback(self, user: dict, *, run_id: str, item_id: str,
                        feedback_type: str, note: str | None = None) -> dict:
        if feedback_type not in FEEDBACK_TYPES:
            raise ServiceError("INVALID_REQUEST",
                               f"feedback_type 只允许 {FEEDBACK_TYPES}")
        with session_scope(self._session_factory) as s:
            item = (s.query(RecommendationItem)
                    .join(RecommendationRun,
                          RecommendationRun.id == RecommendationItem.run_id)
                    .filter(RecommendationItem.id == item_id,
                            RecommendationItem.run_id == run_id,
                            RecommendationRun.user_id == user["id"]).first())
            if item is None:
                raise ServiceError("NOT_FOUND", "推荐条目不存在")
            row = (s.query(RecommendationFeedback)
                   .filter(RecommendationFeedback.user_id == user["id"],
                           RecommendationFeedback.recommendation_item_id == item_id)
                   .first())
            if row is None:
                row = RecommendationFeedback(
                    user_id=user["id"], recommendation_item_id=item_id,
                    feedback_type=feedback_type,
                    note=(note or "")[:512] or None)
                s.add(row)
                created = True
            else:
                row.feedback_type = feedback_type
                row.note = (note or "")[:512] or None
                created = False
            s.flush()
            s.refresh(row)
            out = {"id": row.id, "user_id": row.user_id,
                   "recommendation_item_id": row.recommendation_item_id,
                   "feedback_type": row.feedback_type, "note": row.note,
                   "created_at": _iso(row.created_at)}
        out["created"] = created
        out["gold_label_note"] = ("业务反馈，不是人工 Gold 标签；"
                                  "未经独立标注协议与审核不得进入评估集")
        return out

    def list_feedback(self, user: dict) -> list[dict]:
        session = self._session_factory()
        try:
            rows = (session.query(RecommendationFeedback)
                    .filter(RecommendationFeedback.user_id == user["id"])
                    .order_by(RecommendationFeedback.created_at.desc()).all())
            return [{"id": r.id, "recommendation_item_id": r.recommendation_item_id,
                     "feedback_type": r.feedback_type, "note": r.note,
                     "created_at": _iso(r.created_at)} for r in rows]
        finally:
            session.close()

    # ============================================================ 内部
    @staticmethod
    def _fingerprint(*, user_id: str, profile_version: int, mode: str,
                     top_k: int | None, model_id: str, job_ids: list[str],
                     idempotency_key: str | None) -> str:
        if idempotency_key:
            basis = f"idk:{user_id}:{idempotency_key}"
        else:
            basis = "|".join([user_id, str(profile_version), mode, model_id,
                              str(top_k or ""), ",".join(sorted(job_ids))])
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()

    @staticmethod
    def _job_snapshot_version(j: Job) -> str:
        return f"{j.id}:{_iso(j.updated_at)}"

    def _persist_run(self, *, user: dict, prof: dict, pairs, result: dict,
                     fingerprint: str, runtime_ms: float) -> tuple[dict, bool]:
        job_by_id = {j.id: j for j, _p in pairs}
        try:
            with session_scope(self._session_factory) as s:
                run = RecommendationRun(
                    user_id=user["id"], resume_id=prof.get("resume_id"),
                    profile_version=int(prof["profile_version"]),
                    scoring_method=str(result.get("scoring_method") or "unknown"),
                    model_version=result.get("model_version"),
                    scoring_config_version="scoring_config_v1",
                    job_set_snapshot=[{"job_id": j.id, "title": j.title,
                                       "updated_at": _iso(j.updated_at),
                                       "snapshot_version": self._job_snapshot_version(j)}
                                      for j, _p in pairs],
                    request_fingerprint=fingerprint,
                    status="completed", runtime_ms=runtime_ms,
                    finished_at=_now())
                s.add(run)
                s.flush()
                rows = result.get("results") or []
                for item in rows:
                    job = job_by_id.get(str(item.get("job_id")))
                    if job is None:
                        continue
                    s.add(RecommendationItem(
                        run_id=run.id, job_id=job.id, rank=int(item.get("rank")),
                        score=float(item.get("score")), score_type=str(item.get("score_type")),
                        explanation_snapshot=dict(item),
                        job_snapshot_version=self._job_snapshot_version(job)))
                s.flush()
                s.refresh(run)
                out = self._run_row(s, run, with_items=False)
                return out, True
        except Exception as e:  # noqa: BLE001
            # 唯一约束命中 = 并发重复提交：幂等返回既有运行（不算失败）
            if "uq_reco_runs_user_fingerprint" in str(e) or "UNIQUE" in str(e).upper():
                session = self._session_factory()
                try:
                    row = (session.query(RecommendationRun)
                           .filter(RecommendationRun.user_id == user["id"],
                                   RecommendationRun.request_fingerprint == fingerprint)
                           .first())
                    if row is not None:
                        return self._run_row(session, row, with_items=False), False
                finally:
                    session.close()
            raise

    def _run_row(self, session, run: RecommendationRun, *,
                 with_items: bool) -> dict:
        out = {"id": run.id, "user_id": run.user_id, "resume_id": run.resume_id,
               "profile_version": run.profile_version,
               "scoring_method": run.scoring_method,
               "model_version": run.model_version,
               "scoring_config_version": run.scoring_config_version,
               "job_set_snapshot": run.job_set_snapshot,
               "status": run.status, "runtime_ms": run.runtime_ms,
               "created_at": _iso(run.created_at), "finished_at": _iso(run.finished_at),
               "semantics": "score_type 为排序参考分，不是录用概率"}
        if with_items:
            items = (session.query(RecommendationItem)
                     .filter(RecommendationItem.run_id == run.id)
                     .order_by(RecommendationItem.rank).all())
            out["items"] = [
                {"id": it.id, "job_id": it.job_id, "rank": it.rank, "score": it.score,
                 "score_type": it.score_type,
                 "explanation_snapshot": it.explanation_snapshot,
                 "job_snapshot_version": it.job_snapshot_version}
                for it in items]
        else:
            out["item_count"] = (session.query(RecommendationItem)
                                 .filter(RecommendationItem.run_id == run.id).count())
        return out
