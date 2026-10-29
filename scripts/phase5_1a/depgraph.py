# -*- coding: utf-8 -*-
"""模块依赖图实测（Phase5-1A）：生成 reports/phase5-1a/dependency-graph.{json,md}。

用法：python scripts/phase5_1a/depgraph.py
输出：跨层依赖表 + 各模块第三方库 + annotation 反向依赖检查（静态 AST，无运行时副作用）。
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "src"


def imports_of(path: Path) -> set[str]:
    pkg_parts = path.relative_to(SRC).parts[:-1]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("job_matching"):
                    out.add(a.name)
                else:
                    out.add("ext:" + a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(pkg_parts) - (node.level - 1)
                base = pkg_parts[:max(0, keep)]
                full = ".".join([*base, node.module]) if node.module else ".".join(base)
                out.add(full)
            elif node.module:
                if node.module.startswith("job_matching"):
                    out.add(node.module)
                else:
                    out.add("ext:" + node.module.split(".")[0])
    return out


def layer(mod: str) -> str:
    parts = mod.split(".")
    return parts[1] if len(parts) > 2 else "top"


def main() -> int:
    edges = {}
    for p in sorted((SRC / "job_matching").rglob("*.py")):
        if "__pycache__" in str(p):
            continue
        mod = ".".join(p.relative_to(SRC).with_suffix("").parts)
        edges[mod] = sorted(imports_of(p))

    out = ROOT / "reports" / "phase5-1a"
    out.mkdir(parents=True, exist_ok=True)
    (out / "dependency-graph.json").write_text(
        json.dumps({"generated_by": "scripts/phase5_1a/depgraph.py", "edges": edges},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")

    cross = [(m, d) for m, ds in edges.items() for d in ds
             if d.startswith("job_matching") and layer(m) != layer(d)]
    lines = ["# src/job_matching 跨层依赖（Phase5-1A 实测）", "",
             "| 源模块 | 目标模块 |", "|---|---|"]
    for m, d in sorted(cross):
        lines.append(f"| {m.replace('job_matching.', '')} | {d.replace('job_matching.', '')} |")
    lines += ["", "## 第三方库依赖（按模块）", "", "| 模块 | 第三方库 |", "|---|---|"]
    for m, ds in sorted(edges.items()):
        ext = sorted({d[4:] for d in ds if d.startswith("ext:")})
        if ext:
            lines.append(f"| {m.replace('job_matching.', '')} | {', '.join(ext)} |")
    (out / "dependency-graph.md").write_text("\n".join(lines) + "\n",
                                             encoding="utf-8", newline="\n")

    rev = {}
    for m, ds in edges.items():
        if layer(m) == "annotation":
            continue
        for d in ds:
            if d.startswith("job_matching.annotation"):
                rev.setdefault(d, []).append(m)
    print("annotation 反向依赖（业务侧应为空）:")
    for d, ms in sorted(rev.items()):
        print("  ", d.replace("job_matching.", ""), "<-",
              [x.replace("job_matching.", "") for x in ms])
    print("written:", out / "dependency-graph.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
