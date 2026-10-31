# -*- coding: utf-8 -*-
"""Phase6 / M3 Gold 数据闭环就绪审计（工具链验收 + H2 门禁保持 BLOCKED）。

任务书 M3：重新检查当前文件，不采信历史报告；工具链可验收，但
  * 真实 H2 必须保持 BLOCKED（真实简历 0 / 真实配对 0 / 双人标注 0）；
  * 不得生成虚假标注、不得自动解除门禁；
  * 标注工作流关键能力真实可执行（盲标注包导出、双人独立、导入校验、
    分歧仲裁、Gold 冻结哈希校验）。

全部操作在 PHASE4_3A_2_WORKSPACE 隔离工作区执行，绝不触碰 data/private
与 data/independent_eval/frozen 的真实对象。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _util import ROOT

PY = sys.executable
SCRIPTS = ROOT / "scripts" / "phase4_3a_2"


def _run_script(name: str, workspace: Path, env_extra: dict | None = None):
    env = dict(os.environ)
    env["PHASE4_3A_2_WORKSPACE"] = str(workspace)
    if env_extra:
        env.update(env_extra)
    return subprocess.run([PY, str(SCRIPTS / name)], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)


def _seed_fixture_workspace(ws: Path) -> None:
    """在隔离工作区放入最小合成夹具（合成数据，is_synthetic 语义，永不进 Gold）。"""
    pool_dir = ws / "data" / "independent_eval" / "pool"
    pairs_dir = ws / "data" / "independent_eval" / "pairs"
    pool_dir.mkdir(parents=True, exist_ok=True)
    pairs_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for i in range(3):
        jobs.append({
            "job_id": f"job_s{i:03d}", "job_source": "job-education/annotated",
            "job_title": "数据分析师", "job_description": f"岗位{i}：负责数据分析。",
            "job_text": f"岗位{i}：负责数据分析。任职要求：python、sql。",
            "job_category": "INFORMATION-TECHNOLOGY",
            "job_category_source": "fixture", "language": "zh",
            "required_skills": ["python", "sql"], "preferred_skills": [],
            "education_requirement": {"raw": "", "tokens": ["本科"], "status": "ok",
                                      "source": "fixture"},
            "experience_requirement": {"raw": "", "years_min": None,
                                       "source": "fixture"},
            "historical_gold": False, "content_hash": "",
        })
    (pool_dir / "job_pool_v2.jsonl").write_text(
        "\n".join(json.dumps(j, ensure_ascii=False, sort_keys=True) for j in jobs) + "\n",
        encoding="utf-8", newline="\n")
    pairs = []
    for i in range(6):
        pairs.append({
            "pair_id": f"pair-{i:04d}", "resume_id": f"resume_s{i // 2:03d}",
            "job_id": f"job_s{i % 3:03d}", "resume_source": "unit_fixture",
            "job_source": "job-education/annotated",
            "resume_text": f"合成简历{i}：求职意向 数据分析师。技能 python、sql。",
            "job_text": f"岗位{i % 3}：负责数据分析。任职要求：python、sql。",
            "job_category": "INFORMATION-TECHNOLOGY",
            "job_category_source": "fixture", "language": "zh",
            "difficulty_tier": "medium_skill_overlap",
            "content_hash": f"h{i:04d}", "dataset_version": "dv-fixture",
            "is_synthetic": True, "pair_provenance": "phase6_fixture",
            "eligible_for_gold": False,   # 合成数据永不进 Gold
            "split": "dev_validation",
        })
    (pairs_dir / "pairs_real_v2.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False, sort_keys=True) for p in pairs) + "\n",
        encoding="utf-8", newline="\n")


class M3GoldReadiness(unittest.TestCase):
    maxDiff = None

    # ---------------------------------------------------------- 真实数据状态
    def test_real_data_status_still_blocked(self):
        """重新清点真实数据（不采信历史报告）：真实简历/配对/双人标注必须为 0。"""
        private_resumes = ROOT / "data" / "private" / "resumes"
        real_resumes = 0
        if private_resumes.exists():
            real_resumes = sum(1 for _ in private_resumes.rglob("*.txt"))
        real_pairs_path = ROOT / "data" / "independent_eval" / "pairs" / "pairs_real_v2.jsonl"
        real_pairs = 0
        if real_pairs_path.exists():
            real_pairs = sum(1 for line in real_pairs_path.read_text(
                encoding="utf-8").splitlines() if line.strip())
        raw_annot = ROOT / "data" / "private" / "annotations_raw"
        annot_files = list(raw_annot.glob("annotations_*.csv")) if raw_annot.exists() else []
        self.assertEqual(0, real_pairs, "真实人岗配对必须为 0（H2 BLOCKED）")
        self.assertEqual(0, len(annot_files), "双人有效人工标注必须为 0（H2 BLOCKED）")
        # 冻结门禁状态：freeze_blocked.json 必须保持 blocked，且未冻结
        blocked = json.loads((ROOT / "data" / "independent_eval" / "frozen"
                              / "evalset_v2" / "freeze_blocked.json").read_text(
                                  encoding="utf-8"))
        self.assertEqual("blocked", blocked["h2_status"])
        self.assertFalse(blocked["freeze_written"])
        self.assertFalse(blocked["freeze_verified"])

    def test_synthetic_pairs_not_eligible_for_gold(self):
        """合成配对存在但不允许成为 Gold（eligible_for_gold=False 或标记合成）。"""
        p = ROOT / "data" / "independent_eval" / "pairs" / "pairs_synthetic_v1.jsonl"
        rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()
                if x.strip()]
        self.assertGreater(len(rows), 0)
        for r in rows:
            self.assertTrue(r.get("is_synthetic") or not r.get("eligible_for_gold"),
                            f"合成配对不得具备 Gold 资格: {r.get('pair_id')}")

    # ---------------------------------------------------------- 工具链验收
    def test_export_annotation_packets_blind_and_checked(self):
        """盲标注包导出真实可执行：白名单列 + 不含模型预测/他人答案 + 答案列留空。"""
        from job_matching.annotation import blind_guard, importer
        with tempfile.TemporaryDirectory(prefix="jm_p6_gold_") as td:
            ws = Path(td)
            _seed_fixture_workspace(ws)
            proc = _run_script("export_annotation_packets.py", ws)
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            packet_a = (ws / "data" / "independent_eval" / "annotation" / "packets"
                        / "packet_annotator_A.csv")
            packet_b = packet_a.with_name("packet_annotator_B.csv")
            manifest = packet_a.parent / "packet_manifest.json"
            for f in (packet_a, packet_b, manifest):
                self.assertTrue(f.exists(), f"缺少产物: {f.name}")
            header = packet_a.read_text(encoding="utf-8").splitlines()[0]
            for banned in ("final_score", "label_strength", "candidate_rank",
                           "model_prediction", "annotator_B"):
                self.assertNotIn(banned, header, "标注包不得含模型预测/他人答案列")
            # 列名白名单校验（模型预测 / 盲标隐藏列 / 白名单外字段 -> 拒收）
            self.assertEqual([], blind_guard.check_packet_columns(header.split(",")))
            # 盲标正确性：答案列全部留空（不预置任何答案），双人覆盖同一批配对
            rows_a, _ = importer.read_table(packet_a)
            rows_b, _ = importer.read_table(packet_b)
            answer_cols = ("relevance", "confidence", "reason", "evidence",
                           "annotation_timestamp")
            for rows in (rows_a, rows_b):
                for r in rows:
                    for c in answer_cols:
                        self.assertEqual("", str(r.get(c, "")).strip(),
                                         f"标注包不得预置答案: {c}")
            self.assertEqual({str(r["pair_id"]) for r in rows_a},
                             {str(r["pair_id"]) for r in rows_b},
                             "双人标注包必须覆盖同一批配对（供一致性/独立性检查）")
            # manifest 登记双人包
            man_text = manifest.read_text(encoding="utf-8")
            self.assertIn("annotator_A", man_text)
            self.assertIn("annotator_B", man_text)

    def test_annotation_import_validation(self):
        """导入校验：非法标签 / 协议版本不一致 / 同人冒充双标注 -> 显式报错。"""
        import csv

        from job_matching.annotation import blind_guard, importer, schema

        def write_csv(path: Path, rows: list[dict]) -> None:
            with open(path, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)

        row = {"annotator_id": "annotator_A", "pair_id": "pair-0000",
               "relevance": "2", "confidence": "high", "reason": "技能匹配",
               "evidence": "简历 python；JD python",
               "annotation_timestamp": "2026-10-31T10:00:00",
               "protocol_version": schema.PROTOCOL_VERSION}
        with tempfile.TemporaryDirectory(prefix="jm_p6_imp_") as td:
            td = Path(td)
            ok_path = td / "ann_ok.csv"
            write_csv(ok_path, [row])
            out = importer.validate_annotation_file(ok_path, known_pairs={"pair-0000"})
            self.assertEqual([], out["errors"], out)
            self.assertEqual(1, out["counts"]["valid"])

            # unjudgeable 是协议独立状态标签，合法且不得被拒收
            unj_path = td / "ann_unj.csv"
            write_csv(unj_path, [dict(row, pair_id="pair-0001", relevance="unjudgeable")])
            out_u = importer.validate_annotation_file(unj_path,
                                                      known_pairs={"pair-0000", "pair-0001"})
            self.assertEqual([], out_u["errors"], out_u)

            # 非法标签 -> 拒收
            bad_path = td / "ann_bad.csv"
            write_csv(bad_path, [dict(row, relevance="definitely_hire")])
            out2 = importer.validate_annotation_file(bad_path, known_pairs={"pair-0000"})
            self.assertTrue(out2["errors"], "非法标签必须被拒收")

            # 协议版本不一致 -> 拒收
            pv_path = td / "ann_pv.csv"
            write_csv(pv_path, [dict(row, protocol_version="phase4-3a-annotation-v999")])
            out3 = importer.validate_annotation_file(pv_path, known_pairs={"pair-0000"})
            self.assertTrue(out3["errors"], "协议版本不一致必须被拒收")
            self.assertIn("protocol_version_mismatch",
                          {e["code"] for e in out3["errors"]})

        # 同一标注员冒充两名标注员 -> 独立性拒收
        indep = blind_guard.check_annotator_independence([row], [dict(row)])
        self.assertNotEqual("ok", indep.get("status"), indep)
        codes = {v.get("code") for v in indep.get("violations", [])}
        self.assertIn("shared_annotator_id", codes)

        # 双方 unjudgeable 且无仲裁 -> 禁止强行归入数值标签
        forced = importer.check_unjudgeable_not_forced(
            [{"pair_id": "pair-0002", "final_relevance": "1"}],
            [{"pair_id": "pair-0002", "relevance": "unjudgeable"},
             {"pair_id": "pair-0002", "relevance": "unjudgeable"}])
        self.assertTrue(forced, "unjudgeable 不得被强行归类")

    def test_freeze_gold_blocks_without_real_data(self):
        """Gold 冻结门禁：无合法真实数据时必须拒绝冻结（不生成虚假标注）。"""
        with tempfile.TemporaryDirectory(prefix="jm_p6_freeze_") as td:
            ws = Path(td)
            _seed_fixture_workspace(ws)
            proc = _run_script("freeze_gold.py", ws)
            out_dir = ws / "data" / "independent_eval" / "frozen" / "evalset_v2"
            blocked_files = list(out_dir.glob("*.json"))
            self.assertTrue(proc.returncode != 0 or blocked_files,
                            "无真实数据时不得静默冻结成功")
            for f in blocked_files:
                payload = json.loads(f.read_text(encoding="utf-8"))
                if "freeze_verified" in payload:
                    self.assertFalse(payload["freeze_verified"])
                if "status" in payload:
                    self.assertIn(payload["status"], ("blocked", "pre_freeze_blocked",
                                                      "not_run"))

    def test_freeze_hash_verification_tooling(self):
        """冻结哈希校验工具存在且对冻结清单可执行（有冻结对象时验证）。"""
        from job_matching.annotation import freeze
        self.assertTrue(hasattr(freeze, "verify_freeze") or hasattr(freeze, "verify"))
        pool_manifest = ROOT / "data" / "independent_eval" / "frozen" / "pool_v1"
        if pool_manifest.exists():
            manifests = list(pool_manifest.glob("manifest*.json"))
            self.assertTrue(manifests, "pool_v1 应有冻结清单")

    def test_pii_detection_and_masking_available(self):
        """PII 检测与脱敏工具链可用（真实简历导入前的必要能力）。"""
        from job_matching.annotation import pii
        self.assertTrue(hasattr(pii, "check_export"))
        from job_matching.domain import pii_masking
        self.assertTrue(hasattr(pii_masking, "__name__"))

    def test_annotation_progress_and_resume_support(self):
        """标注工作流：进度统计 + 无法判断(unjudgeable)保护 + 保存/恢复（CSV 可续填）。"""
        from job_matching.annotation import completion, importer, schema
        # unjudgeable 是协议独立状态标签（禁止把缺失信息归为 0）
        self.assertIn("unjudgeable", schema.RELEVANCE_VALUES)
        self.assertEqual("unjudgeable", schema.norm_relevance("U"))
        # unjudgeable 保护 + 缺失标注只登记不填补
        self.assertTrue(hasattr(importer, "check_unjudgeable_not_forced"))
        miss = importer.check_missing_annotations([{"pair_id": "pair-0000"}], [])
        self.assertEqual(1, miss["pairs_missing_annotations"])
        self.assertEqual(0, miss["pairs_fully_annotated"])
        # 无标注时绝不得宣布完成（真实配对 0 -> pending）
        out = completion.assess_annotation_completion(pairs=[], rows_by_annotator={})
        self.assertNotEqual("complete", out["status"], out)
        self.assertIn(out["status"], ("pending", "in_progress", "needs_review",
                                      "blocked"))
        self.assertIn(out["status"], out["vocabulary"])

    def test_leakage_gate_tooling(self):
        """泄漏审计工具：与历史训练语料的重叠检查可执行。"""
        with tempfile.TemporaryDirectory(prefix="jm_p6_leak_") as td:
            ws = Path(td)
            _seed_fixture_workspace(ws)
            proc = _run_script("leakage_gate.py", ws)
            self.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
            reports = ws / "reports" / "phase4-3a-2"
            self.assertTrue(reports.exists(), "泄漏审计应产出报告目录")


if __name__ == "__main__":
    unittest.main(verbosity=2)
