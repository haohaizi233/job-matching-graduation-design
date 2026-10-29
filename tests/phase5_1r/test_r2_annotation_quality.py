# -*- coding: utf-8 -*-
"""R2：人工标注独立性 / 仲裁 / 完成状态门禁回归（Phase5-1R F-002、F-003）。

业务不变量：
  * 「系统记录了风险」不等于「阻止了风险」：独立性异常、导入非法行、仲裁违规、
    unjudgeable 强行转换、最终标签不完整都必须阻断 complete 宣告；
  * 相同标签本身不是违规；整表逐字镜像才阻断，部分镜像转人工复核；
  * 分歧为 0 时仲裁状态 not_required，不得强制要求人工仲裁文件；
  * 分歧 > 0 时仲裁记录必须与分歧集合一一对应，缺一即 pending，非法/越权即 invalid；
  * 标注未完成 -> 冻结前置门禁必须阻断（与 F-001 联动）。
"""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import _util as U

from job_matching.annotation import blind_guard
from job_matching.annotation import completion as C
from job_matching.annotation.importer import (check_missing_annotations,
                                              check_unjudgeable_not_forced)

PV = U.PV


def pair(i: int) -> dict:
    return {"pair_id": f"pair-{i:04d}", "resume_id": f"resume_{i:03d}",
            "job_id": f"job_{i:04d}"}


def row(pid: str, relevance: str, *, who: str, ts: str = U.TS_A,
        reason: str = "判断依据", evidence: str = "证据：简历与 JD 对照") -> dict:
    return U.annotation_row(pid, relevance, who=who, reason=reason,
                            evidence=evidence, timestamp=ts)


def dual_rows(pairs, label: str = "1") -> dict:
    return {
        U.ANNOTATOR_A: [row(p["pair_id"], label, who=U.ANNOTATOR_A) for p in pairs],
        U.ANNOTATOR_B: [row(p["pair_id"], label, who=U.ANNOTATOR_B, ts=U.TS_B,
                            reason="B 判断依据", evidence="B 证据：JD 与简历对照")
                        for p in pairs],
    }


def final_rows_for(pairs, rows_by, label: str = "1") -> list[dict]:
    return [{"pair_id": p["pair_id"], "final_relevance": label,
             "annotator_a_id": U.ANNOTATOR_A, "annotator_b_id": U.ANNOTATOR_B}
            for p in pairs]


def assess(pairs, rows_by, **over) -> dict:
    kwargs = dict(
        pairs=pairs,
        rows_by_annotator=rows_by,
        import_reports={k: {"file": f"{k}.csv", "status": "validated",
                            "errors": [], "warnings": []} for k in rows_by},
        independence=blind_guard.check_annotator_independence(
            rows_by.get(U.ANNOTATOR_A, []), rows_by.get(U.ANNOTATOR_B, [])),
        final_rows=final_rows_for(pairs, rows_by),
        arbitration_status="not_required",
        unjudgeable_forced=[],
        disagreements=[],
    )
    kwargs.update(over)
    return C.assess_annotation_completion(**kwargs)


class R2CompletionStatus(unittest.TestCase):
    """标注完成状态五态判定（F-002）。"""

    def setUp(self):
        self.pairs = [pair(i) for i in range(4)]

    def test_complete_when_all_checks_pass(self):
        res = assess(self.pairs, dual_rows(self.pairs))
        self.assertEqual(res["annotation_status"], "complete")
        self.assertFalse(res["blocking"])

    def test_shared_annotator_id_blocks(self):
        rows = dual_rows(self.pairs)
        for r in rows[U.ANNOTATOR_B]:
            r["annotator_id"] = U.ANNOTATOR_A
        indep = blind_guard.check_annotator_independence(rows[U.ANNOTATOR_A],
                                                         rows[U.ANNOTATOR_B])
        self.assertTrue(any(v["code"] == "shared_annotator_id"
                            for v in indep["violations"]))
        res = assess(self.pairs, rows, independence=indep)
        self.assertEqual(res["annotation_status"], "blocked")
        self.assertTrue(any("shared_annotator_id" in b for b in res["blocking"]))

    def test_fully_mirrored_annotations_block(self):
        rows = {U.ANNOTATOR_A: [row(p["pair_id"], "1", who=U.ANNOTATOR_A) for p in self.pairs],
                U.ANNOTATOR_B: [row(p["pair_id"], "1", who=U.ANNOTATOR_B) for p in self.pairs]}
        indep = blind_guard.check_annotator_independence(rows[U.ANNOTATOR_A],
                                                         rows[U.ANNOTATOR_B])
        self.assertTrue(any(v["code"] == "mirrored_annotations"
                            for v in indep["violations"]))
        res = assess(self.pairs, rows, independence=indep)
        self.assertEqual(res["annotation_status"], "blocked")

    def test_partially_mirrored_needs_review(self):
        rows = dual_rows(self.pairs)
        # 第一条镜像（标签/置信度/理由/证据/时间戳全同），其余不同
        rows[U.ANNOTATOR_B][0] = dict(rows[U.ANNOTATOR_A][0])
        rows[U.ANNOTATOR_B][0]["annotator_id"] = U.ANNOTATOR_B
        indep = blind_guard.check_annotator_independence(rows[U.ANNOTATOR_A],
                                                         rows[U.ANNOTATOR_B])
        self.assertTrue(any(v["code"] == "partially_mirrored_annotations"
                            for v in indep["violations"]))
        res = assess(self.pairs, rows, independence=indep)
        self.assertEqual(res["annotation_status"], "needs_review")

    def test_same_label_is_not_a_violation(self):
        # 两人独立给出相同标签（理由/时间戳不同）必须允许 complete
        res = assess(self.pairs, dual_rows(self.pairs, label="2"))
        self.assertEqual(res["annotation_status"], "complete", res["reasons"])

    def test_missing_annotations_in_progress(self):
        rows = dual_rows(self.pairs)
        rows[U.ANNOTATOR_A] = rows[U.ANNOTATOR_A][:-1]
        rows[U.ANNOTATOR_B] = rows[U.ANNOTATOR_B][:-1]
        res = assess(self.pairs, rows)
        self.assertEqual(res["annotation_status"], "in_progress")

    def test_import_errors_block_completion(self):
        rows = dual_rows(self.pairs)
        res = assess(self.pairs, rows,
                     import_reports={U.ANNOTATOR_A: {
                         "file": "a.csv", "status": "validated_with_errors",
                         "errors": [{"message": "标签值非法: '5'"}], "warnings": []},
                         U.ANNOTATOR_B: {
                             "file": "b.csv", "status": "validated",
                             "errors": [], "warnings": []}})
        self.assertEqual(res["annotation_status"], "blocked")
        self.assertTrue(any("非法记录" in b for b in res["blocking"]))

    def test_arbitration_pending_keeps_in_progress(self):
        rows = dual_rows(self.pairs)
        rows[U.ANNOTATOR_B][0] = row("pair-0000", "0", who=U.ANNOTATOR_B, ts=U.TS_B)
        res = assess(self.pairs, rows, arbitration_status="pending",
                     disagreements=[{"pair_id": "pair-0000"}])
        self.assertEqual(res["annotation_status"], "in_progress")

    def test_arbitration_invalid_blocks(self):
        res = assess(self.pairs, dual_rows(self.pairs), arbitration_status="invalid",
                     disagreements=[{"pair_id": "pair-0000"}])
        self.assertEqual(res["annotation_status"], "blocked")

    def test_unjudgeable_forced_blocks(self):
        res = assess(self.pairs, dual_rows(self.pairs),
                     unjudgeable_forced=[{"pair_id": "pair-0000",
                                          "message": "强行归类"}])
        self.assertEqual(res["annotation_status"], "blocked")

    def test_final_label_problems_block(self):
        rows = dual_rows(self.pairs)
        res = assess(self.pairs, rows,
                     final_rows=[{"pair_id": "pair-0000", "final_relevance": "1"},
                                 {"pair_id": "pair-0000", "final_relevance": "2"},
                                 {"pair_id": "pair-unknown", "final_relevance": "1"}])
        self.assertEqual(res["annotation_status"], "blocked")

    def test_empty_inputs_are_pending(self):
        self.assertEqual(assess([], {})["annotation_status"], "pending")
        self.assertEqual(assess(self.pairs, {U.ANNOTATOR_A: [], U.ANNOTATOR_B: []})
                         ["annotation_status"], "pending")


class R2ArbitrationStatus(unittest.TestCase):
    """仲裁四态判定（F-003）。"""

    def test_no_disagreement_not_required(self):
        res = C.assess_arbitration_status(disagreements=[], arbitration_rows=[])
        self.assertEqual(res["status"], "not_required")

    def test_no_disagreement_with_rows_keeps_record_but_no_rewrite(self):
        rows = [U.arbitration_row("pair-0000", "1")]
        res = C.assess_arbitration_status(disagreements=[], arbitration_rows=rows)
        self.assertEqual(res["status"], "not_required")
        self.assertTrue(any("不得改写" in r for r in res["reasons"]))

    def test_override_attempt_is_invalid_without_disagreement(self):
        rows = [U.arbitration_row("pair-0000", "2")]
        rows[0]["_override_attempt"] = "双方一致为 1，仲裁却改为 2"
        res = C.assess_arbitration_status(disagreements=[], arbitration_rows=rows)
        self.assertEqual(res["status"], "invalid")

    def test_override_attempt_is_invalid_with_disagreement(self):
        rows = [U.arbitration_row("pair-0000", "2"),
                U.arbitration_row("pair-0001", "1")]
        rows[1]["_override_attempt"] = "越权改写一致结论"
        res = C.assess_arbitration_status(
            disagreements=[{"pair_id": "pair-0000"}, {"pair_id": "pair-0001"}],
            arbitration_rows=rows)
        self.assertEqual(res["status"], "invalid")

    def test_all_disputes_arbitrated_completed(self):
        rows = [U.arbitration_row("pair-0000", "1"), U.arbitration_row("pair-0001", "0")]
        res = C.assess_arbitration_status(
            disagreements=[{"pair_id": "pair-0000"}, {"pair_id": "pair-0001"}],
            arbitration_rows=rows)
        self.assertEqual(res["status"], "completed")

    def test_partial_arbitration_pending(self):
        rows = [U.arbitration_row("pair-0000", "1")]
        res = C.assess_arbitration_status(
            disagreements=[{"pair_id": "pair-0000"}, {"pair_id": "pair-0001"}],
            arbitration_rows=rows)
        self.assertEqual(res["status"], "pending")
        self.assertEqual(res["unresolved_pairs"], ["pair-0001"])

    def test_invalid_rows_make_arbitration_invalid(self):
        res = C.assess_arbitration_status(
            disagreements=[{"pair_id": "pair-0000"}],
            arbitration_rows=[U.arbitration_row("pair-0000", "1")],
            arbitration_report={"errors": [{"message": "标签值非法: '5'"}]})
        self.assertEqual(res["status"], "invalid")

    def test_illegal_status_value_rejected(self):
        res = C.assess_arbitration_status(disagreements=[{"pair_id": "p"}],
                                          arbitration_rows=[],
                                          arbitration_report={})
        self.assertIn(res["status"], C.ARBITRATION_STATUSES)


class R2UnjudgeableAndIntegrity(unittest.TestCase):
    """unjudgeable 保护 + 最终标签一对一（F-002 条件 8/9/10）。"""

    def test_unjudgeable_not_forced(self):
        anns = [{"pair_id": "p1", "relevance": "unjudgeable", "annotator_id": U.ANNOTATOR_A},
                {"pair_id": "p1", "relevance": "unjudgeable", "annotator_id": U.ANNOTATOR_B}]
        ok = [{"pair_id": "p1", "final_relevance": "unjudgeable",
               "annotator_a_id": U.ANNOTATOR_A, "annotator_b_id": U.ANNOTATOR_B}]
        self.assertEqual(check_unjudgeable_not_forced(ok, anns), [])

        forced = [{"pair_id": "p1", "final_relevance": "1", "arbitrator_id": ""}]
        problems = check_unjudgeable_not_forced(forced, anns)
        self.assertEqual(problems[0]["code"], "unjudgeable_forced")

        arbitrated = [{"pair_id": "p1", "final_relevance": "1",
                       "arbitrator_id": U.ARBITRATOR}]
        self.assertEqual(check_unjudgeable_not_forced(arbitrated, anns), [])

    def test_final_label_integrity(self):
        pairs = [{"pair_id": "p1"}, {"pair_id": "p2"}]
        res = C.check_final_label_integrity(
            pairs, [{"pair_id": "p1", "final_relevance": "1"},
                    {"pair_id": "p1", "final_relevance": "2"},
                    {"pair_id": "pX", "final_relevance": "1"}])
        self.assertFalse(res["ok"])
        self.assertEqual(res["duplicate_pair_ids"], ["p1"])
        self.assertEqual(res["unknown_pair_ids"], ["pX"])
        self.assertIn("p2", res["missing_pair_ids"])

    def test_missing_annotation_statistics(self):
        """口径与历史测试 test_p4_single_annotator_is_incomplete 一致：
        不足 required_annotators 的配对（含部分标注）一律计入缺失。"""
        pairs = [{"pair_id": "p1"}, {"pair_id": "p2"}, {"pair_id": "p3"}]
        rows = [{"pair_id": "p1", "annotator_id": U.ANNOTATOR_A},          # 仅 1 人 → 缺失
                {"pair_id": "p3", "annotator_id": U.ANNOTATOR_A},
                {"pair_id": "p3", "annotator_id": U.ANNOTATOR_B}]          # 2 人  → 完整
        res = check_missing_annotations(pairs, rows)
        self.assertEqual(res["pairs_total"], 3)
        self.assertEqual(res["pairs_fully_annotated"], 1)
        self.assertEqual(res["pairs_missing_annotations"], 2)
        got = {m["pair_id"]: m["annotations_received"] for m in res["missing_detail"]}
        self.assertEqual(got, {"p1": 1, "p2": 0})
        # 不变量：完整 + 缺失 == 总数，缺失标注不得被填补
        self.assertEqual(res["pairs_fully_annotated"] + res["pairs_missing_annotations"],
                         res["pairs_total"])


class R2AnnotationCliChain(unittest.TestCase):
    """annotation_qa CLI + 冻结联动（F-002/F-003 与 F-001 联动）。"""

    def setUp(self):
        self._before = U.guard_snapshot()

    def tearDown(self):
        diff = U.diff_snapshots(self._before, U.guard_snapshot())
        self.assertEqual(diff, [], f"测试不得触碰历史资产: {diff}")

    def _fresh(self, n_pairs=8):
        td = tempfile.TemporaryDirectory(prefix="ph51r_r2_")
        self.addCleanup(td.cleanup)
        return U.FixtureWorkspace(Path(td.name), n_pairs=n_pairs)

    def test_no_disagreement_freezes_without_arbitration_file(self):
        ws = self._fresh()
        ws.agree_all("1")
        ws.build()
        ws.run_qa()
        prog = ws.progress()
        self.assertEqual(prog["annotation_status"], "complete")
        self.assertEqual(prog["arbitration"]["status"], "not_required")
        self.assertFalse(ws.arbitration_file.exists())

        _, res, _ = ws.run_freeze()
        self.assertEqual(res["status"], "frozen", res)
        manifest = U.jload(ws.evalset_dir / "manifest.json")
        arb = manifest["extra"]["arbitration_manifest"]
        self.assertFalse(arb["arbitration_file_registered"])
        self.assertIn("not_required", arb["reason"])

    def test_disagreement_needs_arbitration_before_freeze(self):
        ws = self._fresh()
        ws.agree_all("1")
        disputed = ws.disagree([1, 3])
        ws.build()
        ws.run_qa()
        prog = ws.progress()
        self.assertIn(prog["annotation_status"], ("in_progress", "needs_review"))
        self.assertEqual(prog["arbitration"]["status"], "pending")
        self.assertEqual(prog["open_disagreements"], len(disputed))

        _, res, _ = ws.run_freeze()
        self.assertEqual(res["status"], "blocked")
        self.assertFalse(res["freeze_written"])

    def test_arbitration_completed_enables_freeze(self):
        ws = self._fresh()
        ws.agree_all("1")
        disputed = ws.disagree([1, 3], label_a="1", label_b="0")
        for pid in disputed:
            ws.arb_rows.append(U.arbitration_row(pid, "1"))
        ws.build()
        ws.run_qa()
        prog = ws.progress()
        self.assertEqual(prog["annotation_status"], "complete", prog["status_assessment"])
        self.assertEqual(prog["arbitration"]["status"], "completed")

        _, res, _ = ws.run_freeze()
        self.assertEqual(res["status"], "frozen", res)
        manifest = U.jload(ws.evalset_dir / "manifest.json")
        self.assertTrue(manifest["extra"]["arbitration_manifest"]
                        ["arbitration_file_registered"])

    def test_partial_arbitration_not_complete(self):
        ws = self._fresh()
        ws.agree_all("1")
        disputed = ws.disagree([1, 3])
        ws.arb_rows.append(U.arbitration_row(disputed[0], "1"))
        ws.build()
        ws.run_qa()
        prog = ws.progress()
        self.assertEqual(prog["arbitration"]["status"], "pending")
        self.assertNotEqual(prog["annotation_status"], "complete")

    def test_invalid_arbitration_rows_block(self):
        ws = self._fresh()
        ws.agree_all("1")
        disputed = ws.disagree([1])
        ws.arb_rows.append(U.arbitration_row(disputed[0], "5"))  # 非法标签
        ws.build()
        ws.run_qa()
        prog = ws.progress()
        self.assertEqual(prog["arbitration"]["status"], "invalid")
        self.assertEqual(prog["annotation_status"], "blocked")

    def test_fake_arbitration_cannot_override_agreement(self):
        ws = self._fresh()
        ws.agree_all("1")          # 双方全部一致 = 无分歧
        ws.arb_rows.append(U.arbitration_row(ws.pairs[0]["pair_id"], "2"))
        ws.build()
        ws.run_qa()
        prog = ws.progress()
        self.assertEqual(prog["arbitration"]["status"], "invalid")
        self.assertEqual(prog["annotation_status"], "blocked")

        _, res, _ = ws.run_freeze()
        self.assertEqual(res["status"], "blocked", "虚假仲裁记录不得绕过冻结门禁")

    def test_shared_annotator_id_blocked(self):
        ws = self._fresh()
        ws.agree_all("1")
        for r in ws.rows_b:
            r["annotator_id"] = U.ANNOTATOR_A
        ws.build()
        ws.run_qa()
        prog = ws.progress()
        self.assertEqual(prog["annotation_status"], "blocked")
        self.assertTrue(any(v["code"] == "shared_annotator_id"
                            for v in prog["independence"]["violations"]))

    def test_mirrored_annotations_blocked(self):
        ws = self._fresh()
        ws.rows_a = [U.annotation_row(p["pair_id"], "1", who=U.ANNOTATOR_A)
                     for p in ws.pairs]
        ws.rows_b = [U.annotation_row(p["pair_id"], "1", who=U.ANNOTATOR_B)
                     for p in ws.pairs]
        ws.build()
        ws.run_qa()
        prog = ws.progress()
        self.assertEqual(prog["annotation_status"], "blocked")

    def test_import_error_rows_block_completion(self):
        ws = self._fresh()
        ws.agree_all("1")
        ws.rows_a.append(U.annotation_row(ws.pairs[0]["pair_id"], "5", who=U.ANNOTATOR_A))
        ws.build()
        ws.run_qa()
        prog = ws.progress()
        self.assertEqual(prog["annotation_status"], "blocked")

    def test_unjudgeable_stays_unjudgeable(self):
        ws = self._fresh()
        ws.agree_all("unjudgeable")
        ws.build()
        ws.run_qa()
        prog = ws.progress()
        self.assertEqual(prog["annotation_status"], "complete", prog["status_assessment"])
        labels = U.jload(ws.reports / "agreement-results.json")
        self.assertGreater(labels["final_labels"]["counts"].get("unjudgeable", 0), 0)
        self.assertEqual(labels["final_labels"]["unjudgeable_forced"], [])


if __name__ == "__main__":
    unittest.main()
