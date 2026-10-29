# -*- coding: utf-8 -*-
"""Phase5-1R 整改回归测试公共工具（stdlib unittest）。

约束（与既有测试套件一致）：
  * 只用**纯合成工程夹具**，不读 data/raw 全量语料、不跑任何 GPU 训练；
  * 所有 CLI 链路测试在 `tempfile` 隔离工作区执行（PHASE4_3A_2_WORKSPACE），
    绝不触碰真实 Gold 目录 data/independent_eval/ 与 data/private/；
  * 工程夹具结果一律标记 fixture_mode，不生成真实 H2 PASS；
  * 不硬编码绝对路径，ROOT 由 __file__ 推导；
  * 严禁跳过失败测试或降低既有门禁标准。
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(ROOT / "scripts" / "phase4_3a_2")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

REPORT_DIR = ROOT / "reports" / "phase5-1r"

ANNOTATOR_A = "annotator_A"
ANNOTATOR_B = "annotator_B"
ARBITRATOR = "arbitrator_1"
PV = "phase4-3a-annotation-v1"
TS_A = "2026-10-29T10:00:00"
TS_B = "2026-10-29T10:07:00"

# 历史资产保护对象（只读）
GUARD_ROOTS = (
    ROOT / "models",
    ROOT / "data" / "raw",
    ROOT / "data" / "independent_eval" / "frozen",
)

ANNOTATION_FIELDS = ("annotator_id", "pair_id", "relevance", "confidence", "reason",
                     "evidence", "annotation_timestamp", "protocol_version")
ARBITRATION_FIELDS = ("arbitrator_id", "pair_id", "final_relevance", "final_confidence",
                      "reason", "evidence", "annotation_timestamp", "protocol_version")


# ------------------------------------------------------------------ IO
def jload(p: Path):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def jdump(obj, p: Path) -> Path:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    return p


def write_csv(rows: list[dict], columns: tuple[str, ...], p: Path) -> Path:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=list(columns), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})
    return p


def write_jsonl(rows: list[dict], p: Path) -> Path:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return p


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ CLI 执行
def run_cli(script_rel: str, *args: str, workspace: Path | None = None,
            expect_rc: int | None = 0, timeout: int = 180) -> tuple[int, dict, str]:
    """在隔离工作区跑真实 CLI，返回 (returncode, 解析出的 JSON, 原始 stdout)。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    if workspace is not None:
        env["PHASE4_3A_2_WORKSPACE"] = str(workspace)
    proc = subprocess.run(
        [sys.executable, str(ROOT / script_rel), *args],
        cwd=str(ROOT), env=env, capture_output=True, timeout=timeout)
    out = proc.stdout.decode("utf-8", errors="replace")
    parsed: dict = {}
    try:
        parsed = json.loads(out)
    except Exception:
        # 允许脚本在 JSON 前打印少量日志
        for line in reversed(out.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    parsed = json.loads(line)
                    break
                except Exception:
                    continue
    if expect_rc is not None and proc.returncode != expect_rc:
        raise AssertionError(
            f"{script_rel} {' '.join(args)} 退出码 {proc.returncode} != {expect_rc}\n"
            f"stdout:\n{out[:3000]}\nstderr:\n{proc.stderr.decode('utf-8', errors='replace')[:3000]}")
    return proc.returncode, parsed, out


# ------------------------------------------------------------------ 合成工程夹具
def make_pair(i: int, *, n_per_resume: int = 2, synthetic: bool = False,
              blind_eligible: bool = True, training_overlap: bool = False) -> dict:
    rid = f"resume_{i // n_per_resume:03d}"
    return {
        "pair_id": f"pair-{i:04d}",
        "resume_id": rid,
        "job_id": f"job_{i:04d}",
        "resume_source": "engineering_fixture",
        "job_source": "engineering_fixture",
        "resume_text": f"工程夹具简历正文 {rid} 技能 python sql",
        "job_text": f"工程夹具岗位正文 job_{i:04d} 技能 python sql",
        "job_title": "数据开发工程师",
        "job_category": "INFORMATION-TECHNOLOGY",
        "job_category_source": "engineering_fixture",
        "language": "zh",
        "graduation_cohort": "2027",
        "employment_type": "校招",
        "required_skills": "python,sql",
        "preferred_skills": "",
        "education_requirement": "本科及以上",
        "experience_requirement": "经验不限",
        "city": "上海",
        "salary_expectation": "面议",
        "resume_target_position": "数据开发工程师",
        "resume_skills": "python,sql",
        "resume_education_level": "本科",
        "resume_years_experience": "1",
        "difficulty_tier": "medium_skill_overlap",
        "content_hash": f"fixturehash{i:04d}",
        "dataset_version": "dv-engineering-fixture",
        "is_synthetic": synthetic,
        "pair_provenance": "engineering_fixture",
        "eligible_for_gold": True,
        "blind_eligible": blind_eligible,
        "training_overlap": training_overlap,
        "split": "dev_validation",
        "consent_status": "granted",
    }


def annotation_row(pair_id: str, relevance: str, *, who: str = ANNOTATOR_A,
                   confidence: str = "high", reason: str = "必备技能满足",
                   evidence: str = "简历：技能 python；JD：任职要求 python",
                   timestamp: str = TS_A, protocol_version: str = PV) -> dict:
    return {
        "annotator_id": who, "pair_id": pair_id, "relevance": relevance,
        "confidence": confidence, "reason": reason, "evidence": evidence,
        "annotation_timestamp": timestamp, "protocol_version": protocol_version,
    }


def arbitration_row(pair_id: str, final_relevance: str, *, who: str = ARBITRATOR,
                    confidence: str = "high", reason: str = "仲裁复核原文后裁定",
                    evidence: str = "JD：任职要求 python；简历：项目经历含 python",
                    timestamp: str = TS_B, protocol_version: str = PV) -> dict:
    return {
        "arbitrator_id": who, "pair_id": pair_id, "final_relevance": final_relevance,
        "final_confidence": confidence, "reason": reason, "evidence": evidence,
        "annotation_timestamp": timestamp, "protocol_version": protocol_version,
    }


class FixtureWorkspace:
    """隔离工程夹具工作区：结构满足门禁，但内容全部为合成工程数据。

    生成的任何结果都是 fixture_mode，**不构成真实 Gold**，不产生真实 H2 PASS。
    """

    def __init__(self, root: Path, *, n_pairs: int = 8, n_per_resume: int = 2):
        self.root = Path(root)
        self.n_pairs = int(n_pairs)
        self.n_per_resume = int(n_per_resume)
        self.pairs = [make_pair(i, n_per_resume=n_per_resume)
                      for i in range(n_pairs)]
        self.rows_a: list[dict] = []
        self.rows_b: list[dict] = []
        self.arb_rows: list[dict] = []
        self.intake_extra: dict = {"consent_complete": True}

    # ---- 路径
    @property
    def pairs_file(self) -> Path:
        return self.root / "data" / "independent_eval" / "pairs" / "pairs_real_v2.jsonl"

    @property
    def annot_a(self) -> Path:
        return (self.root / "data" / "private" / "annotations_raw"
                / f"annotations_{ANNOTATOR_A}.csv")

    @property
    def annot_b(self) -> Path:
        return (self.root / "data" / "private" / "annotations_raw"
                / f"annotations_{ANNOTATOR_B}.csv")

    @property
    def arbitration_file(self) -> Path:
        return (self.root / "data" / "private" / "annotations_raw"
                / "arbitration_filled.csv")

    @property
    def reports(self) -> Path:
        return self.root / "reports" / "phase4-3a-2"

    @property
    def evalset_dir(self) -> Path:
        return self.root / "data" / "independent_eval" / "frozen" / "evalset_v2"

    # ---- 标注内容
    def agree_all(self, label: str = "1", *, skip: int = 0) -> None:
        """两名标注员对全部样本给出一致标签（理由/时间戳不同 => 非镜像）。"""
        for i, p in enumerate(self.pairs):
            if i < skip:
                continue
            self.rows_a.append(annotation_row(p["pair_id"], label, who=ANNOTATOR_A,
                                              reason=f"A 判断依据 {i}",
                                              evidence=f"A 证据：简历技能与 JD 要求匹配 {i}",
                                              timestamp=TS_A))
            self.rows_b.append(annotation_row(p["pair_id"], label, who=ANNOTATOR_B,
                                              reason=f"B 判断依据 {i}",
                                              evidence=f"B 证据：JD 要求与简历技能匹配 {i}",
                                              timestamp=TS_B))

    def disagree(self, indices: list[int], label_a: str = "1", label_b: str = "0") -> list[str]:
        """在指定样本上制造分歧，返回 pair_id 列表。"""
        out = []
        for i in indices:
            pid = self.pairs[i]["pair_id"]
            out.append(pid)
            self.rows_a = [r for r in self.rows_a if r["pair_id"] != pid]
            self.rows_b = [r for r in self.rows_b if r["pair_id"] != pid]
            self.rows_a.append(annotation_row(pid, label_a, who=ANNOTATOR_A,
                                              reason=f"A 分歧判断 {i}",
                                              evidence=f"A 分歧证据 {i}", timestamp=TS_A))
            self.rows_b.append(annotation_row(pid, label_b, who=ANNOTATOR_B,
                                              reason=f"B 分歧判断 {i}",
                                              evidence=f"B 分歧证据 {i}", timestamp=TS_B))
        return out

    def drop_annotations(self, indices: list[int]) -> None:
        for i in indices:
            pid = self.pairs[i]["pair_id"]
            self.rows_a = [r for r in self.rows_a if r["pair_id"] != pid]
            self.rows_b = [r for r in self.rows_b if r["pair_id"] != pid]

    # ---- 落盘
    def build(self) -> "FixtureWorkspace":
        write_jsonl(self.pairs, self.pairs_file)
        write_csv(self.rows_a, ANNOTATION_FIELDS, self.annot_a)
        write_csv(self.rows_b, ANNOTATION_FIELDS, self.annot_b)
        if self.arb_rows:
            write_csv(self.arb_rows, ARBITRATION_FIELDS, self.arbitration_file)
        elif self.arbitration_file.exists():
            self.arbitration_file.unlink()
        write_jsonl([{"job_id": p["job_id"], "job_text": p["job_text"],
                      "job_source": "engineering_fixture", "language": "zh",
                      "historical_gold": False, "strict_unseen_jd_eligible": True}
                     for p in self.pairs],
                    self.root / "data" / "independent_eval" / "pool" / "job_pool_v2.jsonl")
        jdump({"resume_intake": {"records_real": len({p["resume_id"] for p in self.pairs}),
                                 "records_synthetic_excluded": 0},
               "note": "工程夹具：合成数据结构，不构成真实简历"},
              self.reports / "real-pair-manifest.json")
        jdump({"unresolved_blocking_findings": [],
               "note": "工程夹具：无泄漏阻断项"},
              self.reports / "leakage-check.json")
        jdump({"consent_complete": bool(self.intake_extra.get("consent_complete", True)),
               "accepted_real_gold": len({p["resume_id"] for p in self.pairs}),
               "note": "工程夹具：授权记录为结构模拟"},
              self.reports / "resume-intake-audit.json")
        jdump({"admission_checklist": [
                  {"item": "来源可追溯", "status": "ok", "note": "工程夹具"},
                  {"item": "许可明确", "status": "ok", "note": "工程夹具"},
              ],
               "unresolved_blocking_findings": [],
               "note": "工程夹具：来源与许可为结构模拟"},
              self.reports / "source-audit.json")
        docs = self.root / "docs" / "evaluation"
        docs.mkdir(parents=True, exist_ok=True)
        for name in ("consent-template.md", "annotation-guidelines.md"):
            (docs / name).write_text("# 工程夹具文档\n", encoding="utf-8", newline="\n")
        return self

    # ---- CLI
    def run_qa(self, expect_rc: int | None = 0):
        return run_cli("scripts/phase4_3a_2/annotation_qa.py",
                       workspace=self.root, expect_rc=expect_rc)

    def run_freeze(self, *args: str, expect_rc: int | None = 0, min_real_pairs: int = 4):
        return run_cli("scripts/phase4_3a_2/freeze_gold.py", "--fixture-mode",
                       f"--min-real-pairs={min_real_pairs}", *args,
                       workspace=self.root, expect_rc=expect_rc)

    def run_verify(self, manifest: Path | None = None, expect_rc: int | None = 0):
        manifest = manifest or (self.evalset_dir / "manifest.json")
        return run_cli("scripts/phase4_3a_2/freeze_gold.py", "verify",
                       "--manifest", str(manifest),
                       workspace=self.root, expect_rc=expect_rc)

    def progress(self) -> dict:
        return jload(self.reports / "annotation-progress.json")

    def freeze_report(self) -> dict:
        return jload(self.reports / "freeze-verification.json")


def new_workspace(prefix: str = "ph51r_") -> tuple[tempfile.TemporaryDirectory, FixtureWorkspace]:
    td = tempfile.TemporaryDirectory(prefix=prefix)
    ws = FixtureWorkspace(Path(td.name))
    return td, ws


# ------------------------------------------------------------------ 历史资产保护
def guard_snapshot(roots=GUARD_ROOTS) -> dict:
    snap: dict[str, str] = {}
    for root in roots:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            rel_s = str(p.relative_to(ROOT)).replace("\\", "/")
            st = p.stat()
            if st.st_size <= 2_000_000:
                snap[rel_s] = "sha256:" + sha256_file(p)
            else:
                snap[rel_s] = f"size:{st.st_size}:mtime:{st.st_mtime_ns}"
    return snap


def diff_snapshots(before: dict, after: dict) -> list[str]:
    changed = []
    for k, v in before.items():
        if k not in after:
            changed.append(f"deleted:{k}")
        elif after[k] != v:
            changed.append(f"modified:{k}")
    for k in after:
        if k not in before:
            changed.append(f"added:{k}")
    return sorted(changed)
