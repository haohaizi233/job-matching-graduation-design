# -*- coding: utf-8 -*-
"""Phase5-1 业务推理服务测试公共工具（stdlib unittest）。

约束：
  * 只用合成、无敏感信息夹具；不读 data/raw 全量语料、不跑 GPU 训练；
  * 不硬编码绝对路径，ROOT 由 __file__ 推导；
  * 不写入 models/ 与 data/independent_eval/（历史模型与 Gold 盲测数据只读）；
  * 夹具只验证工程链路，不代表任何真实人工标注或模型精度。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(ROOT / "scripts" / "phase5_1")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

REPORT_DIR = ROOT / "reports" / "phase5-1"

# 历史资产保护对象（只读）
GUARD_ROOTS = (
    ROOT / "models",
    ROOT / "data" / "independent_eval" / "frozen",
)

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


# ------------------------------------------------------------------ 合成简历 / JD
RESUME_TEXT = (
    "求职意向：Java开发工程师（校招）\n"
    "教育背景\n"
    "2027届 本科 计算机科学与技术\n"
    "专业技能\n"
    "Java、MySQL、Spring Boot\n"
    "项目经历\n"
    "1. 校园电商后端：使用 Spring Boot 与 MySQL 开发订单模块\n"
    "2. 学生选课系统：使用 Java 完成选课模块\n"
    "实习经历\n"
    "1. 某软件公司后端开发实习生（2026.06-2026.09）\n"
    "证书\n"
    "1. CET-6\n"
)

RESUME_TEXT_NO_EVIDENCE = (
    "求职意向：前端开发工程师\n"
    "自我评价：学习能力强。\n"
)

JD_TEXT = (
    "职位名称：Java开发工程师\n"
    "公司名称：示例科技有限公司\n"
    "工作地点：上海\n"
    "薪资：15-25K\n"
    "任职要求：\n"
    "1. 本科及以上学历，计算机相关专业\n"
    "2. 熟悉 Java、MySQL、Spring Boot\n"
    "3. 熟悉 Redis 者优先\n"
    "岗位职责：\n"
    "1. 负责核心业务系统开发\n"
)


def make_jd(title: str = "Java开发工程师", *, required: str = "熟悉 Java、MySQL",
            preferred: str = "", edu: str = "1. 本科及以上学历",
            duties: str = "1. 负责系统开发", city: str = "上海") -> str:
    parts = [f"职位名称：{title}", f"工作地点：{city}", "任职要求："]
    parts += ([edu] if edu else [])
    parts += ([required] if required else [])
    if preferred:
        parts += ["加分项：", preferred]
    parts += ["岗位职责：", duties]
    return "\n".join(parts) + "\n"


# ------------------------------------------------------------------ 文档夹具
def write_txt(path: Path, text: str, encoding: str = "utf-8") -> Path:
    path.write_text(text, encoding=encoding)
    return path


def write_docx(path: Path, text: str) -> Path:
    """最小 DOCX（zip + word/document.xml），与 resume_intake._extract_docx 兼容。"""
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{_xml_escape(line)}</w:t></w:r></w:p>"
        for line in text.splitlines())
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f"<w:body>{paragraphs}</w:body></w:document>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", document)
    return path


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def write_pdf_with_text(path: Path, text: str) -> Path:
    """可提取文本层的 PDF（PyMuPDF + 内置中文字体）。"""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), text, fontname="china-s", fontsize=11)
    doc.save(path)
    doc.close()
    return path


def write_pdf_scanned(path: Path) -> Path:
    """无文本层 PDF（模拟扫描版），抽取必须返回 ocr_required。"""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(50, 50, 400, 300))
    doc.save(path)
    doc.close()
    return path


# ------------------------------------------------------------------ 模型测试桩
class StubMatchPredictor:
    """与 MatchPredictor 同形接口的测试桩（不触碰历史 checkpoint）。"""

    def __init__(self, model_name: str = "stub", run_id: str = "stub-run-v1"):
        self.model_name = model_name
        self.run_id = run_id
        self.predict_calls = 0

    def predict_score(self, resume: dict, job: dict) -> float:
        self.predict_calls += 1
        return 0.5

    def rank_jobs(self, resume: dict, jobs: list[dict]) -> list[dict]:
        rows = []
        for pos, job in enumerate(jobs):
            rows.append({"input_position": pos, "job": job,
                         "score": self.predict_score(resume, job)})
        rows.sort(key=lambda d: (-d["score"], d["input_position"]))
        return [{"rank": i + 1, "score": round(r["score"], 8),
                 "job_id": r["job"].get("job_id"), "job": r["job"]}
                for i, r in enumerate(rows)]

    def info(self) -> dict:
        return {"run_id": self.run_id, "model_name": self.model_name}


class StubEducationNormalizer:
    """EducationNormalizer 同形测试桩（batch/normalize）。"""

    def __init__(self, labels=None, fallback: bool = False, model_version: str = "stub-edu-v1"):
        self.labels = list(labels if labels is not None else ["本科"])
        self.fallback = fallback
        self.model_version = model_version
        self.calls = 0

    def batch(self, texts, fallback_to_rules=None):
        self.calls += 1
        out = []
        for t in texts:
            rec = {"input": t, "normalized_input": t, "model_version": self.model_version,
                   "model_type": "stub", "expression_seen_in_train": True,
                   "labels": list(self.labels),
                   "scores": {l: 0.9 for l in self.labels},
                   "confidence": 0.9,
                   "confidence_meaning": "模型分数在预测标签上的均值，未经校准，不是真实正确概率",
                   "fallback_to_rule": self.fallback,
                   "rule": "stub_rule" if self.fallback else None, "note": {}}
            out.append(rec)
        return out

    def normalize(self, text, fallback_to_rules=None):
        return self.batch([text], fallback_to_rules=fallback_to_rules)[0]


# ------------------------------------------------------------------ 历史资产保护
def guard_snapshot() -> dict:
    """历史模型与 Gold 盲测数据的指纹快照（小文件哈希，大文件 size+mtime）。"""
    snap: dict[str, str] = {}
    for root in GUARD_ROOTS:
        if not root.exists():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            st = p.stat()
            if st.st_size <= 2_000_000:
                snap[rel] = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
            else:
                snap[rel] = f"size:{st.st_size}:mtime:{st.st_mtime_ns}"
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


_WRITE_CALL_RE = re.compile(
    r"(?:open\s*\(\s*([^\s,]+)\s*,\s*[\"'][^\"']*[wax+][^\"']*[\"']"
    r"|([A-Za-z_][\w\.]*)\.(?:write_text|write_bytes)\s*\()")


def find_protected_write_calls(sources: list[Path]) -> list[str]:
    """扫描源码里针对历史资产目录的写调用（返回违规描述；应为空）。"""
    out: list[str] = []
    for src in sources:
        text = src.read_text(encoding="utf-8")
        for m in _WRITE_CALL_RE.finditer(text):
            target = m.group(1) or m.group(2) or ""
            if re.search(r"models|independent_eval|frozen|gold", target):
                out.append(f"{src.name}: 可能写入历史资产 {target}")
    return out
