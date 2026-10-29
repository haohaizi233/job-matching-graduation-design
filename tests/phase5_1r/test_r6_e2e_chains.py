# -*- coding: utf-8 -*-
"""R6：端到端正向链路 B / C（Phase5-1R 十二、链路 B 简历岗位推荐、链路 C 模型错误与降级）。

链路 B 不变量（全链路走真实实现，不用 Mock 掩盖集成）：
  中文简历文本 -> 文本抽取 -> StudentProfile -> 中文 JD -> JobProfile
  -> 学历/届别/经验约束 -> Baseline 排序 -> 匹配解释 -> API 响应；
  * 技能匹配证据与原文一致；缺失技能只报「证据不足」，不报资格否决；
  * 资格判断（学历/届别/经验）逐项正确，score_type 正确；
  * 整条链可复现（同输入 -> 同输出，除 request_id/latency）；
  * 响应与日志不出现 PII。

链路 C 不变量（错误必须被识别、区分、按策略处理）：
  * 模型未注册 / 权重缺失 / 模型损坏 / 输入不兼容 / 语言不支持 /
    未通过真实 Gold 验证 / 推理超时 —— 七类失败可区分；
  * 降级只发生在策略允许的失败上，且返回中写明降级来源；
  * 永不产生伪造的模型输出（降级结果必须标记为 baseline 启发式分）。
"""
from __future__ import annotations

import base64
import unittest

import _util as U  # noqa: F401

from job_matching.service import api as api_mod
from job_matching.service.contracts import (Field, JobProfile, SkillEntry,
                                            StudentProfile)
from job_matching.service.errors import ServiceError
from job_matching.service.matching import MatchingService, RankOptions
from job_matching.service.model_registry import (EVALUATION_STATUSES, ModelRegistration,
                                                 ModelRegistry,
                                                 register_builtin_models)

RESUME_TXT = (
    "求职意向：Java开发工程师\n"
    "姓名：张三\n"
    "联系方式：13812345678\n"
    "邮箱：zhangsan@example.com\n"
    "毕业年份：2027\n"
    "学历：本科\n"
    "专业：软件工程\n"
    "专业技能：Java、MySQL、Spring Boot\n"
    "项目经历：\n"
    "1. 电商后台系统，使用 Java 与 MySQL 开发订单模块\n"
)

JOB_TXT = (
    "职位名称：Java开发工程师\n"
    "岗位职责：\n1. 负责后端服务开发\n"
    "任职要求：\n"
    "1. 本科及以上学历\n"
    "2. 仅限2027届\n"
    "3. 接受应届毕业生\n"
    "4. 熟悉 Java、MySQL\n"
    "5. 熟悉 Redis 者优先\n"
)

JOB_TXT_2026 = JOB_TXT.replace("仅限2027届", "仅限2026届")


class StubPredictor:
    """与 MatchPredictor 同形接口（链路 C 用；不触碰历史 checkpoint）。"""

    def __init__(self, model_name: str = "stub_match", run_id: str = "stub-run-v1"):
        self.model_name = model_name
        self.run_id = run_id

    def rank_jobs(self, resume: dict, jobs: list[dict]) -> list[dict]:
        rows = [{"input_position": pos, "job": j, "score": 0.5}
                for pos, j in enumerate(jobs)]
        rows.sort(key=lambda d: (-d["score"], d["input_position"]))
        return [{"rank": i + 1, "score": round(r["score"], 8),
                 "job_id": r["job"].get("job_id"), "job": r["job"]}
                for i, r in enumerate(rows)]

    def info(self) -> dict:
        return {"run_id": self.run_id, "model_name": self.model_name}


def student_minimal(*, intention: str = "Java开发工程师",
                    bare: bool = False) -> StudentProfile:
    if bare:
        return StudentProfile(profile_id="stu_c", skills=[])
    return StudentProfile(
        profile_id="stu_c",
        employment_intention=Field(value=intention, status="ok",
                                   fact_source="stated_in_source",
                                   evidence_text=f"求职意向：{intention}"),
        major=Field(value="软件工程", status="ok", fact_source="stated_in_source",
                    evidence_text="专业：软件工程"),
        skills=[SkillEntry(skill_id="s_java", canonical_name="Java",
                           evidence_source="stated_in_source",
                           evidence_text="专业技能：Java",
                           raw_form="Java", extraction_method="dict_v1")],
    )


def job_minimal(job_id: str = "job_c") -> JobProfile:
    return JobProfile(job_id=job_id,
                      job_title=Field(value="Java开发工程师", status="ok",
                                      fact_source="stated_in_source",
                                      evidence_text="职位名称：Java开发工程师"))


class ChainBResumeToRanking(unittest.TestCase):
    """链路 B：中文简历 + 中文 JD -> 排序 + 解释 -> API 响应。"""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        cls.client = TestClient(api_mod.create_app(api_mod.make_services()))

    def _full_chain(self, job_text: str = JOB_TXT):
        b64 = base64.b64encode(RESUME_TXT.encode("utf-8")).decode()
        r1 = self.client.post("/api/v1/profiles/resume/parse",
                              json={"file_name": "resume.txt", "content_base64": b64,
                                    "profile_id": "stu_e2e", "is_synthetic": True})
        self.assertEqual(r1.status_code, 200, r1.text)
        profile = r1.json()["data"]["profile"]

        r2 = self.client.post("/api/v1/profiles/job/parse",
                              json={"text": job_text, "job_id": "job_e2e",
                                    "is_synthetic": True})
        self.assertEqual(r2.status_code, 200, r2.text)
        job = r2.json()["data"]["job_profile"]

        r3 = self.client.post("/api/v1/matching/rank",
                              json={"resume_profile": profile,
                                    "jobs": [{"profile": job}],
                                    "options": {"mode": "baseline"}})
        self.assertEqual(r3.status_code, 200, r3.text)
        return r1.json(), r2.json(), r3.json()

    def test_profile_extracted_from_uploaded_document(self):
        r1, _, _ = self._full_chain()
        profile = r1["data"]["profile"]
        self.assertEqual(profile["parse_status"], "ok")
        self.assertEqual(profile["graduation_year"]["value"], "2027")
        names = [s["canonical_name"].lower() for s in profile["skills"]]
        self.assertIn("java", names)
        self.assertIn("mysql", names)

    def test_skill_evidence_consistent(self):
        _, _, r3 = self._full_chain()
        item = r3["data"]["ranking"]["results"][0]
        matched = {m["canonical_name"].lower() for m in item["matched_skills"]}
        self.assertIn("java", matched)
        self.assertIn("mysql", matched)
        # 匹配证据必须携带双方原文摘录（可追溯）
        for m in item["matched_skills"]:
            self.assertTrue(m.get("evidence_text") or m.get("student_evidence_text"))
        # 缺失技能只报证据不足，不出现资格否决
        missing = {m["canonical_name"].lower()
                   for m in item["missing_required_skills"]
                   + item["preferred_skills_missing"]}
        self.assertIn("redis", missing)
        self.assertEqual(item["skill_constraint_status"], "satisfied")  # 必要技能已覆盖
        for ev in item["evidence"]:
            if ev["type"] == "skill_evidence_missing":
                self.assertIn("证据", ev["note"])

    def test_qualification_judgements(self):
        _, _, r3 = self._full_chain()
        item = r3["data"]["ranking"]["results"][0]
        self.assertEqual(item["education_constraint"]["status"], "satisfied")
        self.assertEqual(item["graduation_cohort_constraint"]["status"], "satisfied")
        self.assertEqual(item["experience_constraint"]["status"], "satisfied")
        self.assertTrue(item["education_constraint"]["needs_human_review"])

    def test_cohort_mismatch_reported(self):
        """2027 届学生 vs 仅限 2026 届 JD：届别约束必须报 not_satisfied。"""
        _, _, r3 = self._full_chain(JOB_TXT_2026)
        item = r3["data"]["ranking"]["results"][0]
        self.assertEqual(item["graduation_cohort_constraint"]["status"], "not_satisfied")
        # 但自动判断不做资格否决，仍标注需人工复核
        self.assertTrue(item["graduation_cohort_constraint"]["needs_human_review"])

    def test_score_type_and_identity(self):
        _, _, r3 = self._full_chain()
        ranking = r3["data"]["ranking"]
        self.assertEqual(ranking["score_type"], "heuristic_score")
        self.assertEqual(ranking["scoring_method"], "baseline_skill_text_v1")
        self.assertEqual(ranking["model_version"], "baseline_skill_text_v1-20261029")
        self.assertFalse(ranking["formal_evaluation"])
        self.assertTrue(any("不是录用概率" in w for w in ranking["warnings"]))

    def test_chain_reproducible(self):
        _, _, r3a = self._full_chain()
        _, _, r3b = self._full_chain()
        self.assertEqual(r3a["data"]["ranking"]["results"],
                         r3b["data"]["ranking"]["results"])
        self.assertEqual(r3a["data"]["ranking"]["score_type"],
                         r3b["data"]["ranking"]["score_type"])

    def test_no_pii_in_response_or_logs(self):
        import io
        import logging
        from job_matching.service.logging_utils import get_service_logger
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        lg = get_service_logger("job_matching.service")
        lg.setLevel(logging.DEBUG)
        lg.addHandler(handler)
        try:
            _, _, r3 = self._full_chain()
            logs = stream.getvalue()
        finally:
            lg.removeHandler(handler)
        blob = str(r3) + logs
        self.assertNotIn("13812345678", blob)
        self.assertNotIn("zhangsan@example.com", blob)
        self.assertNotIn("张三", str(r3))

    def test_direct_service_chain_matches_api(self):
        """同一输入的服务层直调与 API 链路结论一致（不是只测返回值形状）。"""
        from job_matching.service.resume_parser import parse_resume_text
        from job_matching.service.job_parser import parse_job_text
        from job_matching.service.matching import MatchingService
        from job_matching.service.model_registry import ModelRegistry, register_builtin_models
        reg = register_builtin_models(ModelRegistry())
        svc = MatchingService(reg)
        stu = parse_resume_text(RESUME_TXT, profile_id="stu_d", is_synthetic=True)
        job = parse_job_text(JOB_TXT, job_id="job_d", is_synthetic=True)
        res = svc.rank(stu, [job], RankOptions(mode="baseline"))
        item = res["results"][0]
        self.assertEqual(item["graduation_cohort_constraint"]["status"], "satisfied")
        self.assertEqual(item["score_type"], "heuristic_score")
        self.assertEqual(res["scoring_method"], "baseline_skill_text_v1")


class ChainCModelErrorsAndDegradation(unittest.TestCase):
    """链路 C：错误识别 -> 按策略拒绝或降级 -> 降级来源显式 -> 不伪造模型输出。"""

    def _registry(self, loader_impl, *regs: ModelRegistration) -> ModelRegistry:
        reg = ModelRegistry(loader_impl=loader_impl)
        for r in regs:
            reg.register(r)
        return reg

    def _reg(self, model_id: str, **over) -> ModelRegistration:
        kw = dict(model_id=model_id, model_version="v1", task_type="match_ranking",
                  training_data_version="dv-test", loader="legacy_match",
                  loader_kwargs={})
        kw.update(over)
        return ModelRegistration(**kw)

    def _svc(self, registry: ModelRegistry, default_model_id: str) -> MatchingService:
        return MatchingService(registry, default_model_id=default_model_id)

    # ---- 1) 模型未注册
    def test_unregistered_model_explicit_error(self):
        reg = self._registry(lambda r: StubPredictor())
        svc = self._svc(reg, "ghost_model")
        with self.assertRaises(ServiceError) as cm:
            svc.rank(student_minimal(), [job_minimal()],
                     RankOptions(mode="experimental_model", allow_fallback=True))
        self.assertEqual(cm.exception.code, "MODEL_MISSING")
        self.assertEqual(cm.exception.detail.get("failure_kind"), "model_not_registered")

    # ---- 2) 模型文件缺失
    def test_artifact_missing_degrades_with_source(self):
        def loader_missing(r):
            raise FileNotFoundError("model.pkl not found")
        reg = self._registry(lambda r: loader_missing(r), self._reg("m_missing"))
        svc = self._svc(reg, "m_missing")
        res = svc.rank(student_minimal(), [job_minimal()],
                       RankOptions(mode="experimental_model", allow_fallback=True))
        self.assertTrue(res["degradation"]["degraded"])
        self.assertEqual(res["degradation"]["reason_code"], "MODEL_MISSING")
        self.assertEqual(res["degradation"]["failure_kind"], "artifact_missing")
        self.assertEqual(res["degradation"]["requested_model_id"], "m_missing")
        self.assertEqual(res["degradation"]["actual_scoring_method"], "baseline_skill_text_v1")
        self.assertTrue(any(w.startswith("degraded_to_baseline:MODEL_MISSING")
                            for w in res["warnings"]))

    def test_artifact_missing_refused_when_fallback_disabled(self):
        def loader_missing(r):
            raise FileNotFoundError("model.pkl not found")
        reg = self._registry(lambda r: loader_missing(r), self._reg("m_missing2"))
        svc = self._svc(reg, "m_missing2")
        with self.assertRaises(ServiceError) as cm:
            svc.rank(student_minimal(), [job_minimal()],
                     RankOptions(mode="experimental_model", allow_fallback=False))
        self.assertEqual(cm.exception.code, "MODEL_MISSING")

    # ---- 3) 模型损坏
    def test_corrupt_model_distinct_from_missing(self):
        def loader_corrupt(r):
            raise ValueError("bad pickle: corrupt weights")
        reg = self._registry(lambda r: loader_corrupt(r), self._reg("m_corrupt"))
        svc = self._svc(reg, "m_corrupt")
        res = svc.rank(student_minimal(), [job_minimal()],
                       RankOptions(mode="experimental_model", allow_fallback=True))
        d = res["degradation"]
        self.assertEqual(d["reason_code"], "MODEL_CORRUPT")
        self.assertEqual(d["failure_kind"], "artifact_corrupt_or_load_failed")
        self.assertTrue(any("degraded_to_baseline:MODEL_CORRUPT" in w
                            for w in res["warnings"]))

    # ---- 4) 输入不兼容
    def test_inapplicable_input_degrades_or_refuses(self):
        reg = self._registry(lambda r: StubPredictor(), self._reg("m_stub"))
        svc = self._svc(reg, "m_stub")
        stu = student_minimal(intention="")     # 缺求职意向 -> 无法合法构建特征
        res = svc.rank(stu, [job_minimal()],
                       RankOptions(mode="experimental_model", allow_fallback=True))
        self.assertEqual(res["degradation"]["reason_code"], "MODEL_INAPPLICABLE")
        # 拒绝路径必须给出具体缺失字段（降级来源可诊断）
        with self.assertRaises(ServiceError) as cm:
            svc.rank(stu, [job_minimal()],
                     RankOptions(mode="experimental_model", allow_fallback=False))
        self.assertEqual(cm.exception.code, "MODEL_INAPPLICABLE")
        self.assertIn("student.employment_intention",
                      cm.exception.detail.get("missing_fields", []))

    # ---- 5) 模型语言不支持 / 6) 未通过真实 Gold 验证
    def test_formal_mode_rejects_unverified_model(self):
        reg = self._registry(
            lambda r: StubPredictor(),
            self._reg("m_en_only", evaluation_status="research_only_proxy_labels",
                      supported_languages=["en"]))
        svc = self._svc(reg, "m_en_only")
        with self.assertRaises(ServiceError) as cm:
            svc.rank(student_minimal(), [job_minimal()],
                     RankOptions(mode="experimental_model", formal=True))
        self.assertEqual(cm.exception.code, "MODEL_FORMAL_USE_FORBIDDEN")
        detail = cm.exception.detail
        self.assertEqual(detail["supported_languages"], ["en"])
        self.assertEqual(detail["evaluation_status"], "research_only_proxy_labels")

    def test_future_model_unavailable(self):
        reg = self._registry(lambda r: StubPredictor(),
                             self._reg("m_future", loader="future",
                                       evaluation_status="pending_phase4_3b"))
        svc = self._svc(reg, "m_future")
        with self.assertRaises(ServiceError) as cm:
            svc.rank(student_minimal(), [job_minimal()],
                     RankOptions(mode="future_verified"))
        self.assertEqual(cm.exception.code, "FUTURE_MODEL_UNAVAILABLE")

    def test_future_mode_never_degrades_silently(self):
        reg = self._registry(lambda r: StubPredictor(),
                             self._reg("m_future2", loader="future",
                                       evaluation_status="pending_phase4_3b"))
        svc = self._svc(reg, "m_future2")
        with self.assertRaises(ServiceError):
            svc.rank(student_minimal(), [job_minimal()],
                     RankOptions(mode="future_verified", allow_fallback=True))

    # ---- 7) 推理超时
    @staticmethod
    def _slow_loader(r):
        import time
        time.sleep(0.05)        # 保证越过 timeout_ms=0 的截止时刻（Windows 计时粒度）
        return StubPredictor()

    def test_timeout_is_error_not_silent_fallback(self):
        reg = self._registry(self._slow_loader, self._reg("m_stub2"))
        svc = self._svc(reg, "m_stub2")
        with self.assertRaises(ServiceError) as cm:
            svc.rank(student_minimal(), [job_minimal()],
                     RankOptions(mode="experimental_model", allow_fallback=True,
                                 timeout_ms=0))
        self.assertEqual(cm.exception.code, "INFERENCE_TIMEOUT")

    def test_timeout_does_not_mark_degraded(self):
        reg = self._registry(self._slow_loader, self._reg("m_stub3"))
        svc = self._svc(reg, "m_stub3")
        try:
            res = svc.rank(student_minimal(), [job_minimal()],
                           RankOptions(mode="experimental_model", allow_fallback=True,
                                       timeout_ms=0))
        except ServiceError as e:
            self.assertEqual(e.code, "INFERENCE_TIMEOUT")
            self.assertNotIn("degradation", getattr(e, "detail", {}))
            return
        self.fail("超时必须显式失败，不得静默返回降级结果")

    # ---- 降级结果绝不伪装模型输出
    def test_degraded_result_never_claims_model_output(self):
        def loader_missing(r):
            raise FileNotFoundError("model.pkl not found")
        reg = self._registry(lambda r: loader_missing(r), self._reg("m_missing3"))
        svc = self._svc(reg, "m_missing3")
        res = svc.rank(student_minimal(), [job_minimal()],
                       RankOptions(mode="experimental_model", allow_fallback=True))
        self.assertEqual(res["score_type"], "heuristic_score")
        self.assertEqual(res["scoring_method"], "baseline_skill_text_v1")
        self.assertNotEqual(res["score_type"], "model_raw_score")
        for item in res["results"]:
            self.assertEqual(item["score_type"], "heuristic_score")

    def test_working_model_keeps_model_identity(self):
        reg = self._registry(lambda r: StubPredictor(), self._reg("m_stub4"))
        svc = self._svc(reg, "m_stub4")
        res = svc.rank(student_minimal(), [job_minimal()],
                       RankOptions(mode="experimental_model"))
        self.assertEqual(res["score_type"], "model_raw_score")
        self.assertNotIn("degradation", res)
        self.assertTrue(any("experimental_model" in w for w in res["warnings"]))

    # ---- 加载时机（初始化/缓存失效才真正加载）
    def test_load_only_on_init_or_cache_invalidation(self):
        calls = {"n": 0}

        def loader_counted(r):
            calls["n"] += 1
            return StubPredictor()
        reg = self._registry(loader_counted, self._reg("m_cache"))
        a = reg.load("m_cache")
        b = reg.load("m_cache")
        self.assertIs(a, b)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(reg.load_count, 1)
        self.assertEqual(reg.cache_hits, 1)
        reg.cache_clear("m_cache")
        reg.load("m_cache")
        self.assertEqual(calls["n"], 2)

    def test_registered_statuses_valid(self):
        for st in EVALUATION_STATUSES:
            reg = ModelRegistry()
            reg.register(self._reg("m_x", evaluation_status=st, loader="none"))
            self.assertEqual(reg.get("m_x").evaluation_status, st)

    def test_unregistered_future_slot_rejected_on_load(self):
        reg = register_builtin_models(ModelRegistry())
        with self.assertRaises(ServiceError) as cm:
            reg.load("chinese_match_future_v1")
        self.assertEqual(cm.exception.code, "FUTURE_MODEL_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
