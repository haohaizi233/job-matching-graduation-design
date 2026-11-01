# -*- coding: utf-8 -*-
"""Phase7-B / B2：预注册协议状态机与合法盲测解锁。

状态迁移链（不可跳步）：
    PREREGISTERED → DATA_READY → GOLD_FROZEN → DEV_EVALUATED
        → MODEL_LOCKED → BLIND_UNLOCKED → BLIND_EVALUATED
        → FINAL_ACCEPTED / FINAL_NOT_MET

设计要点（可验证迁移，而非「只检查字段存在」）：
1. 追加式状态日志（JSONL）：每条记录含 prev_hash / record_hash
   （canonical-JSON sha256 链），任何改写/删除/插入都会破坏链校验；
2. 证据锚定真实文件：每次迁移登记证据文件的 sha256，校验时**重新计算**
   磁盘文件哈希——复制一个伪造的 MODEL_LOCKED JSON 无法通过校验，
   因为 protocol_hash 必须等于预注册协议文件真实哈希（含 .sha256 侧车对账），
   dataset_hash 必须等于冻结 Gold 清单真实哈希，model_lock_hash 必须等于
   链上 MODEL_LOCKED 记录自身的 record_hash；
3. 盲测一次性：BLIND_UNLOCKED 之后只允许一次正式盲测记录，
   重复盲测、解锁前输出指标一律拒绝；
4. 演练与真实隔离：合成夹具中的迁移一律标注 synthetic_drill=true，
   不得登记为真实 H2 成功。

残余风险（如实声明）：本机制无数字签名，防护锚点是 Git 提交的协议哈希与
冻结数据哈希；若攻击者可同时篡改全部文件与整条链，需要依赖 Git 历史审计发现。
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

# ---------------------------------------------------------------- 状态定义
STATE_ORDER = (
    "PREREGISTERED",
    "DATA_READY",
    "GOLD_FROZEN",
    "DEV_EVALUATED",
    "MODEL_LOCKED",
    "BLIND_UNLOCKED",
    "BLIND_EVALUATED",
    "FINAL_ACCEPTED",   # 终态
    "FINAL_NOT_MET",    # 终态
)
TERMINAL_STATES = ("FINAL_ACCEPTED", "FINAL_NOT_MET")

#: MODEL_LOCKED 记录必须携带的字段（缺一不可）
LOCK_REQUIRED_FIELDS = (
    "selected_model_id",
    "model_version",
    "scoring_config_version",
    "feature_version",
    "data_version",
    "hyperparameters",
    "selection_reason",
    "selection_timestamp",
    "protocol_sha256",
)

#: BLIND_UNLOCKED 记录必须携带的字段
UNLOCK_REQUIRED_FIELDS = (
    "unlock_id",
    "protocol_hash",
    "model_lock_hash",
    "dataset_hash",
    "unlock_timestamp",
    "evaluator_id",
    "evaluation_run_id",
)


class StateMachineError(RuntimeError):
    """状态机违规。message 为机器可读错误码前缀。"""


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def is_blocked_marker(path: Path) -> bool:
    """BLOCKED 状态记录（not_an_experiment_result 且无 results）不得误判为正式结果。

    与 scripts/phase7/verify_preregistration._is_blocked_marker 口径一致。
    """
    if Path(path).suffix.lower() != ".json":
        return False
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    if not isinstance(data, dict):
        return False
    return (bool(data.get("not_an_experiment_result"))
            and str(data.get("status", "")).upper() in ("BLOCKED", "NOT_RUN")
            and not data.get("results"))


class BlindEvalStateMachine:
    """预注册协议状态机（追加式哈希链 + 证据锚定）。"""

    def __init__(self, log_path: Path, protocol_path: Path,
                 protocol_sha_path: Path | None = None):
        self.log_path = Path(log_path)
        self.protocol_path = Path(protocol_path)
        self.protocol_sha_path = Path(protocol_sha_path) if protocol_sha_path else None
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------- 链操作
    def _read_records(self) -> list[dict]:
        if not self.log_path.is_file():
            return []
        out = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def _append(self, record: dict) -> dict:
        records = self._read_records()
        prev_hash = records[-1]["record_hash"] if records else ""
        rec = dict(record)
        rec["seq"] = len(records) + 1
        rec["timestamp"] = rec.get("timestamp") or _now()
        rec["prev_hash"] = prev_hash
        rec["record_hash"] = _sha256_text(_canonical({k: v for k, v in rec.items()
                                                     if k != "record_hash"}))
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def verify_chain(self) -> tuple[bool, str]:
        """校验哈希链完整性：任何改写/删除/插入都会被发现。"""
        records = self._read_records()
        prev_hash = ""
        for i, rec in enumerate(records, start=1):
            if rec.get("seq") != i:
                return False, f"seq 断裂于第 {i} 条"
            if rec.get("prev_hash") != prev_hash:
                return False, f"prev_hash 不匹配于第 {i} 条（链被改写/删除/插入）"
            body = {k: v for k, v in rec.items() if k != "record_hash"}
            if _sha256_text(_canonical(body)) != rec.get("record_hash"):
                return False, f"record_hash 不匹配于第 {i} 条（记录被篡改）"
            prev_hash = rec["record_hash"]
        return True, "chain_ok"

    def current_state(self) -> str:
        ok, detail = self.verify_chain()
        if not ok:
            raise StateMachineError(f"CHAIN_TAMPERED: {detail}")
        records = self._read_records()
        if not records:
            return "PREREGISTERED"
        return records[-1]["state"]

    def _records_of(self, state: str) -> list[dict]:
        return [r for r in self._read_records() if r.get("state") == state]

    def _require_state(self, expected: str):
        cur = self.current_state()
        if cur != expected:
            raise StateMachineError(
                f"ILLEGAL_TRANSITION: 当前状态 {cur}，要求 {expected}（禁止跳步）")

    # ---------------------------------------------------------- 证据锚定
    def protocol_sha256(self) -> str:
        actual = _sha256_file(self.protocol_path)
        if self.protocol_sha_path and self.protocol_sha_path.is_file():
            sidecar = self.protocol_sha_path.read_text(encoding="utf-8").strip().split()[0]
            if sidecar != actual:
                raise StateMachineError(
                    f"PROTOCOL_HASH_MISMATCH: 预注册协议文件哈希 {actual[:16]}… "
                    f"与 .sha256 侧车 {sidecar[:16]}… 不一致（协议被篡改）")
        return actual

    # ---------------------------------------------------------- 迁移
    def mark_registered(self, *, synthetic_drill: bool = False,
                        note: str = "") -> dict:
        """PREREGISTERED 起点登记（锚定预注册协议哈希）。"""
        if self.current_state() != "PREREGISTERED" or self._read_records():
            raise StateMachineError("ILLEGAL_TRANSITION: 起点只能登记一次")
        return self._append({
            "state": "PREREGISTERED", "event": "register",
            "protocol_hash": self.protocol_sha256(),
            "synthetic_drill": bool(synthetic_drill), "note": note,
        })

    def mark_data_ready(self, *, intake_evidence_path: Path,
                        consent_verified: int, intake_accepted: int,
                        synthetic_drill: bool = False) -> dict:
        self._require_state("PREREGISTERED")
        p = Path(intake_evidence_path)
        if not p.is_file():
            raise StateMachineError("EVIDENCE_MISSING: 数据接收证据文件不存在")
        if consent_verified <= 0 or intake_accepted <= 0:
            raise StateMachineError(
                "DATA_NOT_READY: 有效授权/接收数必须为正（业务上传≠授权研究数据）")
        return self._append({
            "state": "DATA_READY", "event": "data_ready",
            "evidence_path": str(p), "evidence_sha256": _sha256_file(p),
            "consent_verified": int(consent_verified),
            "intake_accepted": int(intake_accepted),
            "synthetic_drill": bool(synthetic_drill),
        })

    def freeze_gold(self, *, gold_manifest_path: Path,
                    synthetic_drill: bool = False) -> dict:
        self._require_state("DATA_READY")
        p = Path(gold_manifest_path)
        if not p.is_file():
            raise StateMachineError("GOLD_MISSING: Gold 冻结清单不存在（不得伪造解锁成功）")
        return self._append({
            "state": "GOLD_FROZEN", "event": "freeze_gold",
            "gold_manifest_path": str(p),
            "dataset_hash": _sha256_file(p),
            "synthetic_drill": bool(synthetic_drill),
        })

    def mark_dev_evaluated(self, *, dev_report_path: Path,
                           synthetic_drill: bool = False) -> dict:
        self._require_state("GOLD_FROZEN")
        p = Path(dev_report_path)
        if not p.is_file():
            raise StateMachineError("EVIDENCE_MISSING: 开发集评估报告不存在")
        if is_blocked_marker(p):
            raise StateMachineError(
                "DEV_EVAL_NOT_DONE: 开发集评估报告为 BLOCKED 状态记录，不得视为已评估")
        data = json.loads(p.read_text(encoding="utf-8"))
        if not data.get("results"):
            raise StateMachineError("DEV_EVAL_NOT_DONE: 开发集评估报告无真实 results")
        return self._append({
            "state": "DEV_EVALUATED", "event": "dev_evaluated",
            "dev_report_path": str(p), "dev_report_sha256": _sha256_file(p),
            "synthetic_drill": bool(synthetic_drill),
        })

    def lock_model(self, *, model_manifest_path: Path | None = None,
                   synthetic_drill: bool = False, **fields) -> dict:
        """MODEL_LOCKED：字段必须与真实模型清单/冻结数据/协议一致。"""
        self._require_state("DEV_EVALUATED")
        missing = [f for f in LOCK_REQUIRED_FIELDS if not fields.get(f)
                   and fields.get(f) != 0]
        if missing:
            raise StateMachineError(f"LOCK_FIELDS_MISSING: 缺少 {missing}")

        # 1) 预注册协议哈希必须与真实文件一致
        actual_protocol = self.protocol_sha256()
        if fields["protocol_sha256"] != actual_protocol:
            raise StateMachineError(
                "PROTOCOL_HASH_MISMATCH: lock.protocol_sha256 与预注册协议真实哈希不一致")

        # 2) 数据版本/哈希必须与 GOLD_FROZEN 记录一致
        gold_recs = self._records_of("GOLD_FROZEN")
        if not gold_recs:
            raise StateMachineError("GOLD_MISSING: 未冻结 Gold，不得锁定模型")
        dataset_hash = gold_recs[-1]["dataset_hash"]
        if fields.get("dataset_hash") and fields["dataset_hash"] != dataset_hash:
            raise StateMachineError("DATASET_HASH_MISMATCH: lock.dataset_hash 与冻结 Gold 哈希不一致")
        gold_manifest = Path(gold_recs[-1]["gold_manifest_path"])
        if not gold_manifest.is_file() or _sha256_file(gold_manifest) != dataset_hash:
            raise StateMachineError("DATASET_HASH_MISMATCH: Gold 清单文件缺失或哈希漂移")

        # 3) 模型清单证据（真实文件哈希 + 内部字段对账）
        lock_rec_body = {
            "state": "MODEL_LOCKED", "event": "lock_model",
            **{f: fields[f] for f in LOCK_REQUIRED_FIELDS},
            "dataset_hash": dataset_hash,
            "synthetic_drill": bool(synthetic_drill),
        }
        if model_manifest_path is not None:
            mp = Path(model_manifest_path)
            if not mp.is_file():
                raise StateMachineError("EVIDENCE_MISSING: 模型清单文件不存在")
            manifest = json.loads(mp.read_text(encoding="utf-8"))
            for key in ("selected_model_id", "model_version"):
                mv_key = {"selected_model_id": "model_id",
                          "model_version": "model_version"}[key]
                if str(manifest.get(mv_key)) != str(fields[key]):
                    raise StateMachineError(
                        f"MODEL_VERSION_MISMATCH: lock.{key}={fields[key]!r} "
                        f"与模型清单 {mv_key}={manifest.get(mv_key)!r} 不一致")
            lock_rec_body["model_manifest_path"] = str(mp)
            lock_rec_body["model_manifest_sha256"] = _sha256_file(mp)
        return self._append(lock_rec_body)

    def unlock_blind(self, *, unlock_id: str, evaluator_id: str,
                     evaluation_run_id: str,
                     synthetic_drill: bool = False) -> dict:
        """BLIND_UNLOCKED：一次性正式盲测解锁，全部哈希必须与链上真实记录一致。"""
        if self._records_of("BLIND_UNLOCKED"):
            raise StateMachineError("BLIND_ALREADY_UNLOCKED: 盲测已解锁过，禁止重复解锁")
        self._require_state("MODEL_LOCKED")
        if not unlock_id or not evaluator_id or not evaluation_run_id:
            raise StateMachineError("UNLOCK_FIELDS_MISSING: unlock_id/evaluator_id/evaluation_run_id 必填")

        lock_recs = self._records_of("MODEL_LOCKED")
        lock_rec = lock_recs[-1]
        actual_protocol = self.protocol_sha256()
        gold_recs = self._records_of("GOLD_FROZEN")
        dataset_hash = gold_recs[-1]["dataset_hash"]

        # 解锁前重新锚定证据：伪造/手工拼接的 MODEL_LOCKED 记录在此被拒绝
        if lock_rec.get("protocol_sha256") != actual_protocol:
            raise StateMachineError(
                "PROTOCOL_HASH_MISMATCH: MODEL_LOCKED 记录的协议哈希与预注册协议真实哈希不一致")
        if lock_rec.get("dataset_hash") != dataset_hash:
            raise StateMachineError(
                "DATASET_HASH_MISMATCH: MODEL_LOCKED 记录的数据哈希与冻结 Gold 哈希不一致")
        gold_manifest = Path(gold_recs[-1]["gold_manifest_path"])
        if not gold_manifest.is_file() or _sha256_file(gold_manifest) != dataset_hash:
            raise StateMachineError("DATASET_HASH_MISMATCH: Gold 清单文件缺失或哈希漂移")
        if lock_rec.get("model_manifest_path"):
            mp = Path(lock_rec["model_manifest_path"])
            if (not mp.is_file()
                    or _sha256_file(mp) != lock_rec.get("model_manifest_sha256")):
                raise StateMachineError("MODEL_VERSION_MISMATCH: 模型清单缺失或哈希漂移")

        return self._append({
            "state": "BLIND_UNLOCKED", "event": "unlock_blind",
            "unlock_id": unlock_id,
            "protocol_hash": actual_protocol,
            "model_lock_hash": lock_rec["record_hash"],
            "dataset_hash": dataset_hash,
            "unlock_timestamp": _now(),
            "evaluator_id": evaluator_id,
            "evaluation_run_id": evaluation_run_id,
            "synthetic_drill": bool(synthetic_drill),
        })

    def record_blind_results(self, *, evaluation_run_id: str, results: list,
                             synthetic_drill: bool = False) -> dict:
        """记录正式盲测结果：仅允许解锁后一次，且 run_id 必须与解锁登记一致。"""
        if self._records_of("BLIND_EVALUATED"):
            raise StateMachineError("BLIND_ALREADY_EVALUATED: 重复盲测被拒绝（只允许一次）")
        self._require_state("BLIND_UNLOCKED")
        unlock_rec = self._records_of("BLIND_UNLOCKED")[-1]
        if evaluation_run_id != unlock_rec["evaluation_run_id"]:
            raise StateMachineError(
                "EVAL_RUN_MISMATCH: evaluation_run_id 与解锁登记不一致")
        if not results:
            raise StateMachineError("BLIND_RESULTS_EMPTY: results 为空，不得登记为已评估")
        return self._append({
            "state": "BLIND_EVALUATED", "event": "blind_evaluated",
            "evaluation_run_id": evaluation_run_id,
            "results_digest": _sha256_text(_canonical(results)),
            "n_results": len(results),
            "synthetic_drill": bool(synthetic_drill),
        })

    def finalize(self, *, accepted: bool, note: str = "",
                 synthetic_drill: bool = False) -> dict:
        self._require_state("BLIND_EVALUATED")
        return self._append({
            "state": "FINAL_ACCEPTED" if accepted else "FINAL_NOT_MET",
            "event": "finalize", "note": note,
            "synthetic_drill": bool(synthetic_drill),
        })

    def assert_no_premature_blind_outputs(self, results_paths: list[Path]) -> None:
        """解锁/评估前，任何真实盲测结果产物都必须不存在（BLOCKED 记录除外）。"""
        for p in results_paths:
            p = Path(p)
            if p.is_file() and not is_blocked_marker(p):
                raise StateMachineError(
                    f"PREMATURE_BLIND_OUTPUT: {p} 存在真实盲测产物（提前输出被拒绝）")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Phase7-B 盲测状态机状态查看/链校验")
    ap.add_argument("--log", required=True, help="状态日志 JSONL 路径")
    ap.add_argument("--protocol", required=True, help="预注册协议 JSON 路径")
    ap.add_argument("--protocol-sha", default=None, help="协议 .sha256 侧车路径")
    args = ap.parse_args()
    sm = BlindEvalStateMachine(Path(args.log), Path(args.protocol),
                               Path(args.protocol_sha) if args.protocol_sha else None)
    ok, detail = sm.verify_chain()
    print(f"chain: {detail}")
    print(f"state: {sm.current_state() if ok else 'UNKNOWN（链被篡改）'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
