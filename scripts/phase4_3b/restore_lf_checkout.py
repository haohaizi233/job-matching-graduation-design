# -*- coding: utf-8 -*-
"""把工作区里被 CRLF 污染的文本文件还原为 LF（Phase4-3B 数据完整性修复）。

问题（实测证据见 reports/phase4-3b/14-line-ending-integrity.md）：
  * 本仓库的冻结完整性校验 `src/job_matching/annotation/freeze.py::verify_freeze`
    对数据文件做**逐字节** SHA-256；
  * Windows 下 `core.autocrlf=true` 在 checkout 时把 blob 里的 LF smudge 成 CRLF，
    使工作区字节与 blob 不一致；
  * 结果：`verify_freeze` 误报「冻结产物被改动」，而实际语义内容完全未变——
    实测 4 个冻结文件的 **LF 归一化 SHA-256 与 manifest 记录逐个精确吻合**。

本脚本职责（**只做行尾还原，绝不改动任何语义内容**）：
  1. 只处理 `git ls-files` 追踪到的文本文件（按扩展名白名单）；
  2. 跳过声明了 `* -text` 的 UI/ 目录（其字节稳定性由 UI/.gitattributes 保证）；
  3. 只在文件确实含 CRLF 时改写，改写后 `git status` 必须依然干净（零内容差异）；
  4. 输出逐文件的前后字节数与 SHA-256，便于审计。

用法:
    python scripts/phase4_3b/restore_lf_checkout.py           # 干跑，只报告
    python scripts/phase4_3b/restore_lf_checkout.py --apply   # 实际改写
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _paths  # noqa: E402

ROOT = _paths.ROOT

#: 参与字节级完整性校验的文本扩展名白名单
TEXT_EXTS = {
    ".py", ".md", ".json", ".jsonl", ".csv", ".tsv", ".txt",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".html", ".css",
    ".js", ".ts", ".tsx", ".jsx", ".vue", ".sql", ".mako",
    ".env", ".example", ".gitignore", ".gitattributes",
}

#: 明确不做行尾转换的目录（有各自的 `* -text` 策略，字节必须原样保留）
SKIP_PREFIXES = ("UI/",)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                         cwd=str(ROOT), check=True).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


def is_text_target(rel: str) -> bool:
    if rel.replace("\\", "/").startswith(SKIP_PREFIXES):
        return False
    name = rel.replace("\\", "/").rsplit("/", 1)[-1]
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if name in (".gitignore", ".gitattributes", ".env.example"):
        return True
    return ext in TEXT_EXTS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际改写工作区文件")
    args = ap.parse_args()

    records = []
    for rel in tracked_files():
        if not is_text_target(rel):
            continue
        p = ROOT / rel
        if not p.exists():
            continue
        raw = p.read_bytes()
        if b"\r\n" not in raw:
            continue
        lf = raw.replace(b"\r\n", b"\n")
        rec = {
            "path": rel.replace("\\", "/"),
            "before_bytes": len(raw),
            "after_bytes": len(lf),
            "crlf_count": raw.count(b"\r\n"),
            "before_sha256": _sha(raw),
            "after_sha256": _sha(lf),
        }
        if args.apply:
            p.write_bytes(lf)
            rec["applied"] = True
        else:
            rec["applied"] = False
        records.append(rec)

    payload = {
        "tool": "scripts/phase4_3b/restore_lf_checkout.py",
        "root": str(ROOT),
        "mode": "apply" if args.apply else "dry-run",
        "skipped_prefixes": list(SKIP_PREFIXES),
        "files_touched": len(records),
        "records": records,
    }
    out = _paths.PHASE4_3B_DIR / "line-ending-restore.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8", newline="\n")

    print(f"mode={payload['mode']}  files_with_crlf={len(records)}  -> {out}")
    for r in records[:20]:
        print(f"  {r['path']}: crlf={r['crlf_count']} "
              f"{r['before_bytes']}->{r['after_bytes']}B applied={r['applied']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
