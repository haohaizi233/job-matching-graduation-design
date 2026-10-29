# -*- coding: utf-8 -*-
"""推荐执行、历史快照与反馈闭环（Phase5-2 / Batch 4.2–4.4，Phase5-2R 幂等与指纹修订）。

评分复用纪律（任务 6.2）：
  * 排序计算**只**经 Phase5-1 `MatchingService.rank()`，禁止另写一套数据库版匹配逻辑；
  * 分数语义不变：heuristic_score / model_raw_score 是排序参考分，**不是录用概率**；
  * 结果解释直接存 `build_match_result` 的快照，不二次加工证据。

快照纪律（任务 6.3）：每次运行保存 学生画像版本与内容指纹 / 参与岗位集合与内容与画像版本 /
评分方法 / 模型版本 / 配置版本 / 排序 / 分数类型 / 解释 / 运行时间与状态。
之后无论简历被修改还是 JD 被更新，历史推荐仍可完整解释（内容哈希口径，不靠 updated_at）。

反馈纪律（任务 6.4）：反馈是**用户业务反馈**；未经独立标注协议与数据质量审核，
禁止自动转化为人工 Gold 标签（反馈对象只落 recommendation_feedback）。

事务纪律：运行记录 + 条目在同一事务写入；评分失败不落任何行（无半成功记录）。
所有条目属于唯一运行记录（run_id 外键 + (run_id, rank) / (run_id, job_id) 唯一约束）。

Phase5-2R 幂等语义（P0-02）——**两个概念严格分离**：
  A. 请求幂等（调用方给 `Idempotency-Key`）
     * 同用户 + 同 Key + 同请求语义 -> 返回既有运行（created=false）；
     * 同用户 + 同 Key + **不同**请求语义 -> 409 CONFLICT（绝不静默合并）；
     * 唯一键 (user_id, idempotency_key) 由数据库保证，并发下只落一条。
  B. 结果自然去重（不给 Key）
     * 指纹 = 规范化 JSON（sort_keys、固定分隔符）后 SHA-256，覆盖**全部有效输入**：
       用户 / 画像版本与内容指纹 / 岗位集合与各岗位内容与画像版本 / 排序模式 /
       模型 ID 与模型版本 / 评分配置版本 / top_k / 筛选条件 / allow_fallback；
     * 只有全部有效输入都相同才复用；任一变化 -> 新运行记录。
     * 唯一键 (user_id, request_fingerprint) 由数据库保证。
  冲突识别使用 SQLAlchemy `IntegrityError` + 约束名与业务键二次核对，
  **不**用 `"UNIQUE" in str(exception)` 之类的字符串匹配作为唯一判据。
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from typing import Callable

from sqlalchemy.exc import IntegrityError

from ..infra.persistence import (Job, RecommendationFeedback, RecommendationItem,
                                 RecommendationRun, get_session_factory,
                                 session_scope)
from .contracts import StudentProfile as StudentProfileContract
from .errors import ServiceError

FEEDBACK_TYPES = ("interested", "not_interested", "applied", "interview", "irrelevant")
MAX_TOP_K = 200
MAX_PAGE_SIZE = 100

# 评分配置版本（口径变化时必须递增，否则历史指纹会错误复用）
SCORING_CONFIG_VERSION = "scoring_config_v1"
# 指纹 schema 版本（口径变化必须递增）
FINGERPRINT_SCHEMA = "reco_fingerprint_v2"

# 唯一约束名（用于 IntegrityError 的约束级识别）
CONSTRAINT_IDEM_KEY = "uq_reco_runs_user_idem_key"
CONSTRAINT_FINGERPRINT = "uq_reco_runs_user_fingerprint"


def _now() -> datetime:
    return datetime.utcnow()


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def canonical_json(payload) -> str:
    """规范化 JSON：sort_keys + 固定分隔符 + 非 ASCII 保留。

    与字典插入顺序、对象 repr 等非确定性表示完全无关。
    """
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _constraint_hint(exc: BaseException) -> str:
    """从数据库异常里提取约束提示（只用于**辅助**识别，不作为唯一判据）。"""
    parts = []
    for attr in ("orig", "args"):
        v = getattr(exc, attr, None)
        if v:
            parts.append(" ".join(str(x) for x in (v if isinstance(v, tuple) else (v,))))
    parts.append(str(exc))
    return " ".join(parts)


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
        idem_key = (str(idempotency_key).strip()[:128] or None) if idempotency_key else None

        # 1) 读取**已确认**的学生画像（快照口径：同时取内容指纹，不靠 updated_at）
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
        profile_content_hash = sha256_text(canonical_json(profile_data))

        # 2) 查询符合基础过滤条件的岗位（已发布 + **画像与原文一致**，P0-01）
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
             "job_content_hash": j.job_content_hash,
             "profile_status": j.profile_status,
             "profile_snapshot_version": self._job_snapshot_version(j)}
            for j, _p in pairs]

        # 3) 复用 Phase5-1 评分（不重写匹配逻辑；score_type 语义不变）
        top_k_value = (max(1, min(MAX_TOP_K, int(top_k))) if top_k is not None else None)
        options = {"mode": mode, "allow_fallback": bool(allow_fallback)}
        if model_id:
            options["model_id"] = model_id
        if top_k_value is not None:
            options["top_k"] = top_k_value
        try:
            result = self._services.matching.rank(student, job_profiles, options)
        except ServiceError:
            raise
        except Exception as e:  # noqa: BLE001
            # 评分失败：不落任何行（无半成功业务记录）
            raise ServiceError("INTERNAL_ERROR", f"推荐执行失败: {e}") from e

        # 4) 指纹（P0-02）：请求幂等与自然去重两个概念分离
        semantic_hash, fingerprint = self._fingerprints(
            user=user, prof=prof, profile_content_hash=profile_content_hash,
            pairs=pairs, result=result, mode=mode, top_k=top_k_value,
            model_id=model_id, category=category, city=city,
            allow_fallback=bool(allow_fallback), idempotency_key=idem_key)

        runtime_ms = round((time.monotonic() - t0) * 1000, 3)
        run_out, created = self._persist_run(
            user=user, prof=prof, pairs=pairs, result=result,
            fingerprint=fingerprint, semantic_hash=semantic_hash,
            idempotency_key=idem_key, profile_content_hash=profile_content_hash,
            runtime_ms=runtime_ms)
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

    # ============================================================ 指纹
    @staticmethod
    def semantic_payload(*, user_id: str, profile_version: int,
                         profile_content_hash: str, resume_id: str | None,
                         mode: str, model_id: str, model_version: str,
                         scoring_method: str, top_k: int | None,
                         job_entries: list[dict], category: str | None,
                         city: str | None, allow_fallback: bool) -> dict:
        """推荐结果的**全部有效输入**（P0-02 B）。任一项变化都必须产生不同指纹。"""
        return {
            "schema": FINGERPRINT_SCHEMA,
            "user_id": str(user_id),
            "profile_version": int(profile_version),
            "profile_content_hash": str(profile_content_hash or ""),
            "resume_id": str(resume_id or ""),
            "mode": str(mode or ""),
            "model_id": str(model_id or ""),
            "model_version": str(model_version or ""),
            "scoring_method": str(scoring_method or ""),
            "scoring_config_version": SCORING_CONFIG_VERSION,
            "top_k": (int(top_k) if top_k is not None else None),
            "jobs": sorted(job_entries, key=lambda d: str(d.get("job_id", ""))),
            "filters": {"category": str(category or ""), "city": str(city or "")},
            "allow_fallback": bool(allow_fallback),
        }

    def _fingerprints(self, *, user, prof, profile_content_hash, pairs, result,
                      mode, top_k, model_id, category, city, allow_fallback,
                      idempotency_key) -> tuple[str, str]:
        """返回 (request_semantic_hash, request_fingerprint)。

        * semantic_hash：只看有效输入，与是否携带幂等键无关（用于 409 冲突判定）；
        * fingerprint：去重身份。
            - 无幂等键 -> 只由语义决定（自然去重：全同才复用）；
            - 有幂等键 -> 绑定 (user, key) 命名空间（同 Key 同语义 = 同一请求；
              同 Key 不同语义由唯一约束拦下并转 409）。
        """
        job_entries = [
            {"job_id": j.id,
             "job_content_hash": str(j.job_content_hash or ""),
             "profile_source_hash": str(j.profile_source_hash or ""),
             "profile_status": str(j.profile_status or "")}
            for j, _p in pairs]
        payload = self.semantic_payload(
            user_id=user["id"], profile_version=int(prof["profile_version"]),
            profile_content_hash=profile_content_hash,
            resume_id=prof.get("resume_id"), mode=mode,
            model_id=model_id or "",
            model_version=str(result.get("model_version") or ""),
            scoring_method=str(result.get("scoring_method") or ""),
            top_k=top_k, job_entries=job_entries, category=category, city=city,
            allow_fallback=allow_fallback)
        semantic_json = canonical_json(payload)
        semantic_hash = sha256_text(semantic_json)
        if idempotency_key:
            fingerprint = sha256_text(f"idk:{user['id']}:{idempotency_key}")
        else:
            fingerprint = sha256_text(f"sem:{semantic_json}")
        return semantic_hash, fingerprint

    @staticmethod
    def _job_snapshot_version(j: Job) -> str:
        """岗位快照版本 = job_id + 内容哈希（内容口径；不用 updated_at 证明一致性）。"""
        return f"{j.id}:{str(j.job_content_hash or '')[:16]}"

    # ============================================================ 落库
    def _find_reusable_run(self, *, user: dict, fingerprint: str,
                           semantic_hash: str,
                           idempotency_key: str | None) -> tuple[dict, bool] | None:
        """插入前自然去重（P0-02）：同一业务键 + 语义一致 -> 直接复用，不依赖异常路径。

        * 无幂等键 -> 按 (user, request_fingerprint) 找既有运行；
        * 有幂等键 -> 按 (user, idempotency_key) 找既有运行，语义不一致返回 409。
        """
        session = self._session_factory()
        try:
            if idempotency_key:
                row = (session.query(RecommendationRun)
                       .filter(RecommendationRun.user_id == user["id"],
                               RecommendationRun.idempotency_key == idempotency_key)
                       .first())
            else:
                row = (session.query(RecommendationRun)
                       .filter(RecommendationRun.user_id == user["id"],
                               RecommendationRun.request_fingerprint == fingerprint)
                       .first())
            if row is None:
                return None
            if (idempotency_key and row.request_semantic_hash
                    and row.request_semantic_hash != semantic_hash):
                # 同 Key 不同请求语义 -> 明确冲突，绝不合并
                raise ServiceError(
                    "CONFLICT",
                    "Idempotency-Key 已被用于语义不同的推荐请求，请更换 Key 或复用原请求",
                    {"idempotency_key": idempotency_key,
                     "existing_run_id": row.id,
                     "existing_semantic_hash": row.request_semantic_hash,
                     "request_semantic_hash": semantic_hash})
            return self._run_row(session, row, with_items=False), False
        finally:
            session.close()

    def _persist_run(self, *, user: dict, prof: dict, pairs, result: dict,
                     fingerprint: str, semantic_hash: str,
                     idempotency_key: str | None, profile_content_hash: str,
                     runtime_ms: float) -> tuple[dict, bool]:
        reused = self._find_reusable_run(
            user=user, fingerprint=fingerprint, semantic_hash=semantic_hash,
            idempotency_key=idempotency_key)
        if reused is not None:
            return reused
        job_by_id = {j.id: j for j, _p in pairs}
        try:
            with session_scope(self._session_factory) as s:
                run = RecommendationRun(
                    user_id=user["id"], resume_id=prof.get("resume_id"),
                    profile_version=int(prof["profile_version"]),
                    scoring_method=str(result.get("scoring_method") or "unknown"),
                    model_version=result.get("model_version"),
                    scoring_config_version=SCORING_CONFIG_VERSION,
                    job_set_snapshot=[{"job_id": j.id, "title": j.title,
                                       "updated_at": _iso(j.updated_at),
                                       "job_content_hash": j.job_content_hash,
                                       "profile_status": j.profile_status,
                                       "snapshot_version": self._job_snapshot_version(j)}
                                      for j, _p in pairs],
                    request_fingerprint=fingerprint,
                    request_semantic_hash=semantic_hash,
                    idempotency_key=idempotency_key,
                    profile_content_hash=profile_content_hash,
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
                        job_snapshot_version=self._job_snapshot_version(job),
                        job_content_hash=job.job_content_hash,
                        profile_status_at_run=job.profile_status))
                s.flush()
                s.refresh(run)
                out = self._run_row(s, run, with_items=False)
                return out, True
        except IntegrityError as e:
            # P0-02 并发控制：先按异常类型（IntegrityError）识别，再按约束名 + 业务键二次核对。
            # 唯一约束命中 = 并发重复提交：解析为幂等复用或 409，不算业务失败。
            resolved = self._resolve_unique_conflict(
                user=user, fingerprint=fingerprint, semantic_hash=semantic_hash,
                idempotency_key=idempotency_key, exc=e)
            if resolved is not None:
                return resolved
            raise

    def _resolve_unique_conflict(self, *, user, fingerprint, semantic_hash,
                                 idempotency_key, exc) -> tuple[dict, bool] | None:
        """识别具体冲突的约束与业务键；解析不了就原样抛出（不吞错）。"""
        hint = _constraint_hint(exc)
        # PostgreSQL 报约束名；SQLite 只报列名（"UNIQUE constraint failed: t.col, ..."），
        # 故约束名与列名两种口径都识别；真正的判据仍是下面的业务键二次核对。
        by_idem = (CONSTRAINT_IDEM_KEY in hint) or ("idempotency_key" in hint)
        by_fp = (CONSTRAINT_FINGERPRINT in hint) or ("request_fingerprint" in hint)
        if not (by_idem or by_fp):
            # 不是本模块登记的唯一约束（可能是外键/其它约束）-> 不得当作幂等复用
            return None

        session = self._session_factory()
        try:
            if idempotency_key:
                row = (session.query(RecommendationRun)
                       .filter(RecommendationRun.user_id == user["id"],
                               RecommendationRun.idempotency_key == idempotency_key)
                       .first())
                if row is None and by_fp:
                    row = (session.query(RecommendationRun)
                           .filter(RecommendationRun.user_id == user["id"],
                                   RecommendationRun.request_fingerprint == fingerprint)
                           .first())
                if row is not None:
                    if row.request_semantic_hash and row.request_semantic_hash != semantic_hash:
                        # 同 Key 不同请求语义 -> 明确冲突，绝不合并
                        raise ServiceError(
                            "CONFLICT",
                            "Idempotency-Key 已被用于语义不同的推荐请求，请更换 Key 或复用原请求",
                            {"idempotency_key": idempotency_key,
                             "existing_run_id": row.id,
                             "existing_semantic_hash": row.request_semantic_hash,
                             "request_semantic_hash": semantic_hash})
                    return self._run_row(session, row, with_items=False), False
                return None
            row = (session.query(RecommendationRun)
                   .filter(RecommendationRun.user_id == user["id"],
                           RecommendationRun.request_fingerprint == fingerprint)
                   .first())
            if row is not None:
                return self._run_row(session, row, with_items=False), False
            return None
        finally:
            session.close()

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
               # ---- Phase5-2R 新增（只加不减）----
               "request_fingerprint": run.request_fingerprint,
               "request_semantic_hash": run.request_semantic_hash,
               "idempotency_key": run.idempotency_key,
               "profile_content_hash": run.profile_content_hash,
               "semantics": "score_type 为排序参考分，不是录用概率"}
        if with_items:
            items = (session.query(RecommendationItem)
                     .filter(RecommendationItem.run_id == run.id)
                     .order_by(RecommendationItem.rank).all())
            out["items"] = [
                {"id": it.id, "job_id": it.job_id, "rank": it.rank, "score": it.score,
                 "score_type": it.score_type,
                 "explanation_snapshot": it.explanation_snapshot,
                 "job_snapshot_version": it.job_snapshot_version,
                 "job_content_hash": it.job_content_hash,
                 "profile_status_at_run": it.profile_status_at_run}
                for it in items]
        else:
            out["item_count"] = (session.query(RecommendationItem)
                                 .filter(RecommendationItem.run_id == run.id).count())
        return out
