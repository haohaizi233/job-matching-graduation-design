# -*- coding: utf-8 -*-
"""P12 推理超时契约 / 降级契约 / 统一模型输出信封（Phase4-3B / M6）。

补齐 reports/phase4-3b/13-regression-results.md 遗留缺口 #1（推理超时未覆盖）。

覆盖：
  * 预算构造合法性（超时/规模/长度必须为正）；
  * 软预算超时必须显式抛 `InferenceTimeoutError`，不得静默给分；
  * 协作式 deadline check 在长循环内可中断；
  * `ModelResult` 契约：NaN/Inf 拒绝、概率语义拒绝、隐私字段拒绝；
  * 统一输出信封字段稳定（任务书第九节）；
  * Windows 无 SIGALRM 时如实登记 `timeout_mode="soft_poll"`，不伪装硬中断。
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from job_matching.models.runtime_guard import (  # noqa: E402
    BudgetExceeded, InferenceTimeoutError, ModelResult, RuntimeBudget,
    build_result, make_deadline_checker, run_with_budget)

ENVELOPE_KEYS = ("model_id", "model_version", "score", "score_type",
                 "explanation", "feature_version", "degradation")


class P12RuntimeBudget(unittest.TestCase):
    def test_budget_rejects_non_positive_values(self):
        with self.assertRaises(ValueError):
            RuntimeBudget(timeout_seconds=0)
        with self.assertRaises(ValueError):
            RuntimeBudget(timeout_seconds=-1.0)
        with self.assertRaises(ValueError):
            RuntimeBudget(max_candidates=0)
        with self.assertRaises(ValueError):
            RuntimeBudget(max_text_chars=0)

    def test_budget_to_dict_is_stable(self):
        b = RuntimeBudget(timeout_seconds=1.5, max_candidates=7, max_text_chars=9)
        self.assertEqual({"timeout_seconds": 1.5, "max_candidates": 7,
                          "max_text_chars": 9, "alarm": False}, b.to_dict())

    def test_run_with_budget_fast_path_reports_elapsed(self):
        out, info = run_with_budget(lambda: 42, budget=RuntimeBudget(timeout_seconds=5))
        self.assertEqual(42, out)
        self.assertFalse(info["timed_out"])
        self.assertIsNone(info["degradation"])
        self.assertGreaterEqual(info["elapsed_ms"], 0.0)
        self.assertEqual(5, info["timeout_seconds"])

    def test_soft_poll_mode_declared_on_windows(self):
        import platform
        _out, info = run_with_budget(lambda: 1, budget=RuntimeBudget(timeout_seconds=5))
        if platform.system() == "Windows":
            self.assertEqual("soft_poll", info["timeout_mode"])
        self.assertIn(info["timeout_mode"], ("soft_poll", "hard_alarm"))

    def test_deadline_checker_raises_after_timeout(self):
        check = make_deadline_checker(0.02, t0=time.perf_counter() - 1.0)
        with self.assertRaises(InferenceTimeoutError) as cm:
            check()
        self.assertGreater(cm.exception.elapsed_seconds,
                           cm.exception.budget_seconds)

    def test_deadline_checker_silent_before_timeout(self):
        check = make_deadline_checker(30.0)
        check()  # 不应抛

    def test_cooperative_loop_is_interrupted(self):
        """长循环内调用注入的 deadline check 必须在超时后立刻中断。

        护栏判定语义（防 flaky）：循环上限的理论耗时必须远大于超时预算，
        否则循环会先跑完而测不到中断。用计数器而非 list 省内存；
        若协作式 check 失效，循环将跑满上限 → `assertLess` 失败，
        即使 run_with_budget 事后补报超时也能被本用例识别。
        """
        state = {"n": 0}
        cap = 5_000_000

        def long_job(__deadline_check__=None):
            for i in range(cap + 1_000_000):
                if __deadline_check__ is not None:
                    __deadline_check__()
                state["n"] = i + 1
                if i >= cap:  # 保险：避免测试本身跑飞
                    break
            return state["n"]

        with self.assertRaises(InferenceTimeoutError):
            run_with_budget(long_job, budget=RuntimeBudget(timeout_seconds=0.05))
        self.assertGreater(state["n"], 0, "循环应已开始执行")
        self.assertLess(state["n"], cap, "超时后必须立刻中断，不得跑满全部迭代")

    def test_soft_budget_raises_when_fn_exceeds_budget(self):
        def slow():
            time.sleep(0.25)
            return "done"

        with self.assertRaises(InferenceTimeoutError) as cm:
            run_with_budget(slow, budget=RuntimeBudget(timeout_seconds=0.05))
        self.assertGreater(cm.exception.elapsed_seconds, 0.05)

    def test_timeout_error_is_budget_exceeded_subclass(self):
        self.assertTrue(issubclass(InferenceTimeoutError, BudgetExceeded))

    def test_hard_alarm_not_available_on_windows(self):
        import platform
        if platform.system() != "Windows":
            self.skipTest("仅在 Windows 上验证无 SIGALRM 的如实降级")
        _out, info = run_with_budget(
            lambda: 1, budget=RuntimeBudget(timeout_seconds=5, alarm=True))
        self.assertEqual("soft_poll", info["timeout_mode"],
                         "Windows 无 SIGALRM 时不得伪装成硬中断")


class P12ModelResultContract(unittest.TestCase):
    def test_envelope_has_required_keys(self):
        res = build_result("m-1", "v1", 0.5, explanation={"skill": 0.2})
        d = res.to_dict()
        for k in ENVELOPE_KEYS:
            self.assertIn(k, d)
        self.assertEqual("ranking_score", d["score_type"])
        self.assertEqual({"skill": 0.2}, d["explanation"])

    def test_nan_and_inf_scores_rejected(self):
        with self.assertRaises(ValueError):
            build_result("m", "v", float("nan"))
        with self.assertRaises(ValueError):
            build_result("m", "v", float("inf"))
        with self.assertRaises(ValueError):
            build_result("m", "v", float("-inf"))

    def test_none_score_allowed_for_degraded(self):
        res = build_result("m", "v", None, degradation={"reason": "timeout"})
        self.assertIsNone(res.to_dict()["score"])
        self.assertEqual({"reason": "timeout"}, res.to_dict()["degradation"])

    def test_score_type_must_be_ranking_not_probability(self):
        with self.assertRaises(ValueError):
            ModelResult("m", "v", 0.1, score_type="probability").validate()
        with self.assertRaises(ValueError):
            build_result("m", "v", 0.1,
                         explanation={"note": "这是录用概率"}).validate()

    def test_privacy_fields_blocked_in_explanation(self):
        with self.assertRaises(ValueError):
            build_result("m", "v", 0.1, explanation={"resume_text": "某人简历原文"})

    def test_negative_score_is_allowed_for_ranking(self):
        """排名分数可为任意有限实数，不做 [0,1] 假约束。"""
        res = build_result("m", "v", -3.25)
        self.assertEqual(-3.25, res.to_dict()["score"])

    def test_extra_and_elapsed_are_serialisable(self):
        import json
        res = build_result("m", "v", 0.3, elapsed_ms=12.3456,
                           extra={"pool_size": 10})
        s = json.dumps(res.to_dict(), ensure_ascii=False)
        self.assertIn('"pool_size": 10', s)
        self.assertEqual(12.346, res.to_dict()["elapsed_ms"])

    def test_result_is_immutable_to_forged_probability(self):
        d = build_result("m", "v", 0.9, explanation={"k": "v"}).to_dict()
        self.assertNotIn("probability", str(d).lower())


if __name__ == "__main__":
    unittest.main()
