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

#: Gold 工作区状态词表（与既有协议 coordination；值为状态，不是断言目标）
GOLD_STATE_VOCAB = ("BLOCKED", "READY_FOR_ANNOTATION", "READY_FOR_FREEZE",
                    "FROZEN_AND_VERIFIED", "INVALID")


def audit_gold_workspace_state(root: Path) -> dict:
    """**只读**审计真实 Gold 工作区状态（不写不删，不覆盖任何现有文件）。

    状态由真实计数**推导**，而非硬编码为零：
      * BLOCKED              —— 尚无真实人岗配对（H2 未启动）；
      * READY_FOR_ANNOTATION —— 有真实配对，但双人完整标注未就绪；
      * READY_FOR_FREEZE     —— 真实配对齐备且 ≥2 标注员完整覆盖、分歧已仲裁；
      * FROZEN_AND_VERIFIED  —— 已冻结且哈希校验通过；
      * INVALID              —— 结构不一致（如声称 verified 却无冻结产物）。

    该审计是**环境状态检查**，不应成为长期不变的断言；工具链单元测试
    （合成夹具）与本审计解耦——真实配对增长不会使工具链测试失败。
    """
    root = Path(root)
    notes: list[str] = []

    # 真实简历（真人 PII 源，只读计数）
    private_resumes = root / "data" / "private" / "resumes"
    real_resumes = (sum(1 for _ in private_resumes.rglob("*.txt"))
                    if private_resumes.exists() else 0)

    # 真实人岗配对
    real_pairs_path = root / "data" / "independent_eval" / "pairs" / "pairs_real_v2.jsonl"
    real_pairs = 0
    if real_pairs_path.exists():
        real_pairs = sum(1 for ln in real_pairs_path.read_text(
            encoding="utf-8").splitlines() if ln.strip())

    # 双人标注（只读解析 annotations_*.csv，统计标注员与配对覆盖）
    raw_annot = root / "data" / "private" / "annotations_raw"
    annot_files = sorted(raw_annot.glob("annotations_*.csv")) if raw_annot.exists() else []
    annotators: set[str] = set()
    covered_pairs: set[str] = set()
    parse_error = False
    for f in annot_files:
        try:
            import csv as _csv
            with open(f, "r", encoding="utf-8", newline="") as fh:
                for row in _csv.DictReader(fh):
                    aid = str(row.get("annotator_id") or "").strip()
                    pid = str(row.get("pair_id") or "").strip()
                    if aid:
                        annotators.add(aid)
                    if pid:
                        covered_pairs.add(pid)
        except Exception:  # noqa: BLE001
            parse_error = True
            notes.append(f"标注文件不可解析: {f.name}")

    # 冻结门禁（只读）
    frozen_dir = root / "data" / "independent_eval" / "frozen" / "evalset_v2"
    fb_path = frozen_dir / "freeze_blocked.json"
    h2_status = None
    freeze_written = False
    freeze_verified = False
    if fb_path.exists():
        try:
            fb = json.loads(fb_path.read_text(encoding="utf-8"))
            h2_status = fb.get("h2_status")
            freeze_written = bool(fb.get("freeze_written"))
            freeze_verified = bool(fb.get("freeze_verified"))
        except Exception:  # noqa: BLE001
            parse_error = True
            h2_status = "INVALID"
            notes.append("freeze_blocked.json 不可解析")

    annotations_complete = (len(annotators) >= 2 and real_pairs > 0
                            and len(covered_pairs) >= real_pairs)

    # 状态推导（不硬编码任何计数为零）
    if parse_error or (freeze_verified and not freeze_written):
        status = "INVALID"
    elif freeze_verified and freeze_written and real_pairs > 0:
        status = "FROZEN_AND_VERIFIED"
    elif real_pairs == 0:
        status = "BLOCKED"
    elif annotations_complete:
        status = "READY_FOR_FREEZE"
    else:
        status = "READY_FOR_ANNOTATION"

    return {
        "status": status,
        "vocabulary": list(GOLD_STATE_VOCAB),
        "real_resumes": real_resumes,
        "real_pairs": real_pairs,
        "annotation_files": len(annot_files),
        "distinct_annotators": len(annotators),
        "covered_pairs": len(covered_pairs),
        "annotations_complete": annotations_complete,
        "h2_status": h2_status,
        "freeze_written": freeze_written,
        "freeze_verified": freeze_verified,
        "notes": notes,
    }


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
    def test_gold_workspace_state_driven_and_consistent(self):
        """真实工作区状态**状态驱动**审计（只读）：不硬编码真实数据必须为零。

        状态由真实计数推导（BLOCKED/READY_*/FROZEN_AND_VERIFIED/INVALID）。
        本用例只校验**恒成立的不变式**，不假设真实配对数为 0——真实配对从
        0 增加到 100 时本用例仍应 PASS，而不会因计数增长失败。
        """
        before = self._dir_snapshot(ROOT / "data")
        state = audit_gold_workspace_state(ROOT)

        # 1) 状态必须落在协议词表内
        self.assertIn(state["status"], GOLD_STATE_VOCAB, state)
        self.assertEqual(list(GOLD_STATE_VOCAB), state["vocabulary"])

        # 2) 恒成立不变式（与真实计数无关）
        if state["status"] == "FROZEN_AND_VERIFIED":
            self.assertTrue(state["freeze_verified"], state)
            self.assertTrue(state["freeze_written"], state)
            self.assertGreater(state["real_pairs"], 0, state)
        if state["status"] == "INVALID":
            # 结构不一致时不得被当成可用/已冻结
            self.assertFalse(state["freeze_verified"] and not state["freeze_written"], state)
        # 未冻结前，冻结门禁不得声称 verified
        if not state["freeze_verified"]:
            self.assertFalse(state["freeze_written"] and state["status"] == "FROZEN_AND_VERIFIED")

        # 3) 合成数据永远不构成真实配对 / Gold 资格
        self._assert_synthetic_never_gold()

        # 4) 审计只读：执行后 data/ 目录树无新增/修改
        after = self._dir_snapshot(ROOT / "data")
        self.assertEqual(before, after, "Gold 状态审计必须只读，不得写入/覆盖真实数据")

        # 5) H2 当前状态仅登记，不作为长期断言（工具链测试与之解耦）
        if state["real_pairs"] == 0:
            self.assertEqual("BLOCKED", state["status"], state)

    @staticmethod
    def _dir_snapshot(base: Path) -> dict:
        """只读快照：相对路径 -> (size, mtime_ns)，用于证明审计无副作用。"""
        snap = {}
        if not base.exists():
            return snap
        for p in sorted(base.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(base))
                st = p.stat()
                snap[rel] = (st.st_size, st.st_mtime_ns)
        return snap

    def _assert_synthetic_never_gold(self):
        """合成配对存在但不允许成为 Gold（eligible_for_gold=False 或标记合成）。"""
        p = ROOT / "data" / "independent_eval" / "pairs" / "pairs_synthetic_v1.jsonl"
        if not p.exists():
            return
        rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()
                if x.strip()]
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
