# -*- coding: utf-8 -*-
"""数据集完整性校验：按迁移清单复核 data\\raw\\ 下所有原始文件的大小与 SHA-256。

用法：
    python scripts/verify_data_integrity.py [--manifest 清单路径] [--quiet]

对照 reports/workspace-migration-manifest.json 中的 file_inventory：
  * 逐文件检查是否仍存在于登记路径
  * 比对字节数与 SHA-256（流式，1 MB 分块，大文件不占内存）
  * 顺带检查是否出现未登记的新文件（避免"意外新增的大型数据副本"）

退出码：0 全部一致；1 存在缺失 / 不一致 / 未登记文件。
"""
import argparse
import hashlib
import json
import os
import sys

CHUNK = 1024 * 1024
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MANIFEST = os.path.join(ROOT, "reports", "workspace-migration-manifest.json")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def walk_files(base):
    out = []
    for dp, _, fns in os.walk(base):
        for fn in fns:
            out.append(os.path.relpath(os.path.join(dp, fn), ROOT).replace("\\", "/"))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    inventory = manifest["file_inventory"]
    registered = {item["relative_path"] for item in inventory}
    problems, checked = [], 0

    for item in inventory:
        rel = item["relative_path"]
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.isfile(path):
            problems.append("缺失: %s" % rel)
            continue
        size = os.path.getsize(path)
        if size != item["bytes"]:
            problems.append("大小不一致: %s  期望 %d, 实际 %d" % (rel, item["bytes"], size))
            continue
        digest = sha256_file(path)
        checked += 1
        if digest != item["sha256"]:
            problems.append("SHA-256 不一致: %s\n    期望 %s\n    实际 %s" % (rel, item["sha256"], digest))
        elif not args.quiet:
            print("[OK] %s  %12d  %s" % (digest[:16], size, rel))

    # 未登记文件（重点看是否意外多出大型数据副本）
    data_raw = os.path.join(ROOT, "data", "raw")
    extras = []
    if os.path.isdir(data_raw):
        for rel in walk_files(data_raw):
            if rel not in registered:
                extras.append(rel)
    for rel in extras:
        p = os.path.join(ROOT, rel.replace("/", os.sep))
        mb = os.path.getsize(p) / 1048576.0
        tag = "  <== 大文件，请确认" if mb > 1 else ""
        problems.append("未登记文件: %s (%.3f MB)%s" % (rel, mb, tag))

    print("=" * 70)
    print("清单: %s" % args.manifest)
    print("登记文件 %d 个, 已校验 %d 个" % (len(inventory), checked))
    print("问题 %d 项:" % len(problems))
    for p in problems:
        print("  - %s" % p)
    print("=" * 70)
    if problems:
        print("结论: FAIL —— 请先核对 reports/workspace-migration-manifest.json 再做任何处理")
        return 1
    print("结论: PASS —— 全部原始数据文件与基线一致，无未登记副本")
    return 0


if __name__ == "__main__":
    sys.exit(main())
