# -*- coding: utf-8 -*-
"""数据集完整性校验工具：流式计算 SHA-256，避免把大文件载入内存。

用法：
    python scripts/hash_datasets.py <路径1> [<路径2> ...] [--json 输出文件]

对文件输出 {path, size, sha256}；对目录递归处理其中所有文件。
"""
import argparse
import hashlib
import json
import os
import sys

CHUNK = 1024 * 1024  # 1 MB


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def collect(paths):
    out = []
    for p in paths:
        p = os.path.abspath(p)
        if os.path.isfile(p):
            out.append(p)
        elif os.path.isdir(p):
            for dp, _, fns in os.walk(p):
                for fn in sorted(fns):
                    out.append(os.path.join(dp, fn))
        else:
            print("跳过（不存在）: %s" % p, file=sys.stderr)
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    results = []
    for p in collect(args.paths):
        size = os.path.getsize(p)
        results.append({"path": p, "size": size, "sha256": sha256_file(p)})
        print("%s  %12d  %s" % (results[-1]["sha256"], size, p), file=sys.stderr)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print("已写出: %s" % args.json_out, file=sys.stderr)
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
