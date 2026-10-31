# -*- coding: utf-8 -*-
"""P7-0：研究协议预注册锁定与防篡改校验。

职责（只读校验 + 写一份审计产物）：
  1. 计算 `configs/phase7-preregistered-protocol-v1.json` 的 SHA-256，
     与侧车锁定文件 `configs/phase7-preregistered-protocol-v1.sha256` 比对；
  2. 校验预注册的关键字段仍在位（主指标、切分边界、通过条件、选型规则、
     tie-breaking、not_computable 处理、amendment 策略）；
  3. 校验 blind_test 结果产物**尚未**产生（防止提前读取盲测指标）；
  4. 输出 `reports/phase7/00-preregistration-lock.json`。

退出码：0 = 全部通过；1 = 存在篡改/缺字段/提前产出盲测产物。

纪律：本脚本不修改协议文件本身；协议修订必须新建版本文件并走 amendment 流程。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, report_path, sha256_file, write_json  # noqa: E402

PROTOCOL = ROOT / "configs" / "phase7-preregistered-protocol-v1.json"
LOCKFILE = ROOT / "configs" / "phase7-preregistered-protocol-v1.sha256"

#: 预注册必须在位的关键字段（缺一即视为协议被削弱）
REQUIRED_INVARIANTS = {
    "evaluation_task.label_schema": ["0", "1", "2", "unjudgeable"],
    "metrics.primary": "NDCG@10",
    "statistical_method.resampling_unit": "查询组（resume_id）",
    "statistical_method.method": "paired bootstrap",
    "statistical_method.n_boot": 1000,
    "statistical_method.seed": 20261205,
    "data_boundaries.split_unit": "resume_id（查询组）",
    "data_boundaries.blind_test.unlock_condition_required": True,
    "pass_criteria.no_downgrade_rule_required": True,
    "model_selection_rule.lock_before_blind_test": True,
    "not_computable_policy.status_value": "not_computable",
}

#: 正式 blind_test 结果产物（一旦存在即说明预注册前已读取盲测，必须阻断）
BLIND_RESULT_GLOBS = (
    "reports/phase7/04-real-model-evaluation.json",
    "reports/phase7/blind_test/**",
    "data/independent_eval/frozen/**/blind_results*.json",
)


def _dig(obj, dotted: str):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def check_invariants(proto: dict) -> list[dict]:
    out = []
    for key, expect in REQUIRED_INVARIANTS.items():
        if key.endswith("_required"):
            base = key[: -len("_required")]
            got = _dig(proto, base)
            ok = bool(got) if isinstance(got, bool) else got is not None and got != ""
            out.append({"key": key, "ok": ok, "expected": "non-empty/true", "actual": got})
            continue
        got = _dig(proto, key)
        ok = (got == expect)
        out.append({"key": key, "ok": ok, "expected": expect, "actual": got})
    return out


def find_premature_blind_outputs() -> list[str]:
    hits: list[str] = []
    for pattern in BLIND_RESULT_GLOBS:
        for p in ROOT.glob(pattern):
            if p.is_file():
                hits.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    return sorted(set(hits))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Phase7 预注册协议锁定校验（只读）")
    ap.add_argument("--write-report", action="store_true",
                    help="写出 reports/phase7/00-preregistration-lock.json")
    args = ap.parse_args(argv)

    if not PROTOCOL.exists():
        print(f"[FAIL] 预注册协议文件缺失: {PROTOCOL}")
        return 1

    digest = sha256_file(str(PROTOCOL))
    lock_ok = False
    lock_recorded = None
    if LOCKFILE.exists():
        recorded = LOCKFILE.read_text(encoding="utf-8").strip().split()[0]
        lock_recorded = recorded
        lock_ok = (recorded.lower() == digest.lower())
    else:
        print(f"[FAIL] 锁定文件缺失: {LOCKFILE}（必须登记预注册 SHA-256）")

    proto = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    inv = check_invariants(proto)
    inv_ok = all(i["ok"] for i in inv)
    blind_hits = find_premature_blind_outputs()
    blind_ok = not blind_hits

    status = "PASS" if (lock_ok and inv_ok and blind_ok) else "FAIL"
    payload = {
        "artifact": "phase7-preregistration-lock",
        "status": status,
        "protocol_id": proto.get("protocol_id"),
        "protocol_path": str(PROTOCOL.relative_to(ROOT)).replace("\\", "/"),
        "sha256": digest,
        "sha256_recorded": lock_recorded,
        "hash_lock_ok": lock_ok,
        "invariants_ok": inv_ok,
        "invariants": inv,
        "premature_blind_outputs": blind_hits,
        "blind_test_outputs_absent": blind_ok,
        "discipline": [
            "预注册后禁止修改主评价指标 / 切分方式 / 通过条件以追求更好成绩",
            "blind_test 结果在模型锁定前不得读取",
            "不可计算项必须写 not_computable + reason，禁止填 0 或用代理标签补足",
        ],
    }

    print(f"[{status}] protocol={payload['protocol_id']} sha256={digest[:16]}… "
          f"hash_lock={lock_ok} invariants={inv_ok} blind_absent={blind_ok}")
    for i in inv:
        if not i["ok"]:
            print(f"  - 不变式未满足: {i['key']} expected={i['expected']!r} actual={i['actual']!r}")
    for h in blind_hits:
        print(f"  - 提前存在的盲测产物: {h}")

    if args.write_report:
        p = write_json(report_path("reports", "phase7", "00-preregistration-lock.json"), payload)
        print(f"  报告已写出: {p}")

    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
