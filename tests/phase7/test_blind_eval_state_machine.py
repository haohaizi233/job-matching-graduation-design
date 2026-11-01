# -*- coding: utf-8 -*-
"""Phase7-B / B2：盲测状态机测试（隔离合成夹具演练）。

纪律：本模块所有迁移都在 tempfile 合成夹具中演练（synthetic_drill=True），
**不构成真实 H2 成功**，也不触碰真实 Gold / data/private。

覆盖（任务书 B2.5）：
  未冻结 Gold → 拒绝解锁
  无模型锁定 → 拒绝解锁
  模型版本不符 → 拒绝解锁
  数据哈希不符 → 拒绝解锁
  预注册哈希不符 → 拒绝解锁
  提前输出盲测指标 → 拒绝
  重复盲测 → 拒绝
  合法完整状态 → 允许一次盲测
  BLOCKED 状态文件 → 不误判为正式实验结果
  真实 Gold 缺失 → 不伪造解锁成功
  另：哈希链篡改检测 / 伪造 MODEL_LOCKED 记录拒绝
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from _util import ROOT  # noqa: F401

from blind_eval_state_machine import (  # noqa: E402
    BlindEvalStateMachine, StateMachineError, is_blocked_marker,
)


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class _Fixture:
    """合成夹具：协议 / Gold 清单 / 开发评估 / 模型清单 / 状态日志。"""

    def __init__(self, root: Path):
        self.root = root
        self.protocol = root / "protocol.json"
        self.protocol.write_text(json.dumps(
            {"protocol_id": "phase7-eval-protocol-v1", "synthetic": True},
            ensure_ascii=False, indent=2), encoding="utf-8")
        self.protocol_sha = root / "protocol.json.sha256"
        self.protocol_sha.write_text(_sha256_file(self.protocol) + "\n", encoding="utf-8")

        self.intake = root / "intake-evidence.json"
        self.intake.write_text(json.dumps({"consent_verified": 3, "synthetic": True}),
                               encoding="utf-8")

        self.gold = root / "gold-manifest.json"
        self.gold.write_text(json.dumps(
            {"data_version": "gold-v1", "n_pairs": 42, "synthetic": True},
            ensure_ascii=False, indent=2), encoding="utf-8")

        self.dev = root / "dev-eval.json"
        self.dev.write_text(json.dumps(
            {"status": "DONE", "results": [{"model": "E02", "ndcg_at_10": 0.42}]},
            ensure_ascii=False), encoding="utf-8")

        self.model_manifest = root / "model-manifest.json"
        self.model_manifest.write_text(json.dumps(
            {"model_id": "E02", "model_version": "v1.0.0"},
            ensure_ascii=False), encoding="utf-8")

        self.log = root / "state-log.jsonl"

    def machine(self) -> BlindEvalStateMachine:
        return BlindEvalStateMachine(self.log, self.protocol, self.protocol_sha)

    def lock_fields(self, **over) -> dict:
        f = {
            "selected_model_id": "E02",
            "model_version": "v1.0.0",
            "scoring_config_version": "scoring-v1",
            "feature_version": "feature-v1",
            "data_version": "gold-v1",
            "hyperparameters": {"lr": 0.01},
            "selection_reason": "dev 集 NDCG@10 最高",
            "selection_timestamp": "2026-11-01T00:00:00",
            "protocol_sha256": _sha256_file(self.protocol),
        }
        f.update(over)
        return f

    def drive_to_model_locked(self, sm: BlindEvalStateMachine):
        sm.mark_registered(synthetic_drill=True)
        sm.mark_data_ready(intake_evidence_path=self.intake,
                           consent_verified=3, intake_accepted=3,
                           synthetic_drill=True)
        sm.freeze_gold(gold_manifest_path=self.gold, synthetic_drill=True)
        sm.mark_dev_evaluated(dev_report_path=self.dev, synthetic_drill=True)
        sm.lock_model(model_manifest_path=self.model_manifest,
                      synthetic_drill=True, **self.lock_fields())


class TestBlindEvalStateMachine(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.fx = _Fixture(Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    # ---------------------------------------------------------- 解锁门禁
    def test_unlock_rejected_without_gold_frozen(self):
        """未冻结 Gold → 拒绝解锁（跳步直接拒绝）。"""
        sm = self.fx.machine()
        sm.mark_registered(synthetic_drill=True)
        with self.assertRaises(StateMachineError) as cm:
            sm.unlock_blind(unlock_id="U1", evaluator_id="eval-1",
                            evaluation_run_id="R1", synthetic_drill=True)
        self.assertIn("ILLEGAL_TRANSITION", str(cm.exception))

    def test_unlock_rejected_without_model_lock(self):
        """无模型锁定 → 拒绝解锁。"""
        sm = self.fx.machine()
        sm.mark_registered(synthetic_drill=True)
        sm.mark_data_ready(intake_evidence_path=self.fx.intake,
                           consent_verified=2, intake_accepted=2,
                           synthetic_drill=True)
        sm.freeze_gold(gold_manifest_path=self.fx.gold, synthetic_drill=True)
        sm.mark_dev_evaluated(dev_report_path=self.fx.dev, synthetic_drill=True)
        with self.assertRaises(StateMachineError) as cm:
            sm.unlock_blind(unlock_id="U1", evaluator_id="eval-1",
                            evaluation_run_id="R1", synthetic_drill=True)
        self.assertIn("ILLEGAL_TRANSITION", str(cm.exception))

    def test_model_version_mismatch_rejected(self):
        """模型版本不符 → 拒绝锁定/解锁。"""
        sm = self.fx.machine()
        sm.mark_registered(synthetic_drill=True)
        sm.mark_data_ready(intake_evidence_path=self.fx.intake,
                           consent_verified=2, intake_accepted=2,
                           synthetic_drill=True)
        sm.freeze_gold(gold_manifest_path=self.fx.gold, synthetic_drill=True)
        sm.mark_dev_evaluated(dev_report_path=self.fx.dev, synthetic_drill=True)
        with self.assertRaises(StateMachineError) as cm:
            sm.lock_model(model_manifest_path=self.fx.model_manifest,
                          synthetic_drill=True,
                          **self.fx.lock_fields(model_version="v9.9.9"))
        self.assertIn("MODEL_VERSION_MISMATCH", str(cm.exception))

    def test_dataset_hash_mismatch_rejected(self):
        """数据哈希不符（冻结后 Gold 清单被改动）→ 拒绝锁定/解锁。"""
        sm = self.fx.machine()
        sm.mark_registered(synthetic_drill=True)
        sm.mark_data_ready(intake_evidence_path=self.fx.intake,
                           consent_verified=2, intake_accepted=2,
                           synthetic_drill=True)
        sm.freeze_gold(gold_manifest_path=self.fx.gold, synthetic_drill=True)
        sm.mark_dev_evaluated(dev_report_path=self.fx.dev, synthetic_drill=True)
        # 冻结后篡改 Gold 清单
        self.fx.gold.write_text(json.dumps({"data_version": "gold-v1", "n_pairs": 999}),
                                encoding="utf-8")
        with self.assertRaises(StateMachineError) as cm:
            sm.lock_model(model_manifest_path=self.fx.model_manifest,
                          synthetic_drill=True, **self.fx.lock_fields())
        self.assertIn("DATASET_HASH_MISMATCH", str(cm.exception))

    def test_protocol_hash_mismatch_rejected(self):
        """预注册哈希不符 → 拒绝锁定（协议文件被改动 / 侧车对账失败）。"""
        sm = self.fx.machine()
        sm.mark_registered(synthetic_drill=True)
        sm.mark_data_ready(intake_evidence_path=self.fx.intake,
                           consent_verified=2, intake_accepted=2,
                           synthetic_drill=True)
        sm.freeze_gold(gold_manifest_path=self.fx.gold, synthetic_drill=True)
        sm.mark_dev_evaluated(dev_report_path=self.fx.dev, synthetic_drill=True)
        # 场景 A：lock 字段携带的协议哈希与真实文件不符
        with self.assertRaises(StateMachineError) as cm:
            sm.lock_model(model_manifest_path=self.fx.model_manifest,
                          synthetic_drill=True,
                          **self.fx.lock_fields(protocol_sha256="0" * 64))
        self.assertIn("PROTOCOL_HASH_MISMATCH", str(cm.exception))
        # 场景 B：协议文件本身被改动（侧车对账暴露）
        self.fx.protocol.write_text(json.dumps({"protocol_id": "phase7-eval-protocol-v1",
                                                "tampered": True}), encoding="utf-8")
        with self.assertRaises(StateMachineError) as cm:
            sm.lock_model(model_manifest_path=self.fx.model_manifest,
                          synthetic_drill=True, **self.fx.lock_fields())
        self.assertIn("PROTOCOL_HASH_MISMATCH", str(cm.exception))

    # ---------------------------------------------------------- 盲测纪律
    def test_premature_blind_metrics_rejected(self):
        """解锁前输出盲测指标 → 拒绝。"""
        sm = self.fx.machine()
        self.fx.drive_to_model_locked(sm)
        with self.assertRaises(StateMachineError) as cm:
            sm.record_blind_results(evaluation_run_id="R1",
                                    results=[{"ndcg": 0.5}], synthetic_drill=True)
        self.assertIn("ILLEGAL_TRANSITION", str(cm.exception))
        # 真实盲测产物提前存在也会被显式拒绝
        early = Path(self._td.name) / "blind-results.json"
        early.write_text(json.dumps({"status": "DONE",
                                     "results": [{"ndcg_at_10": 0.5}]}),
                         encoding="utf-8")
        with self.assertRaises(StateMachineError) as cm:
            sm.assert_no_premature_blind_outputs([early])
        self.assertIn("PREMATURE_BLIND_OUTPUT", str(cm.exception))

    def test_duplicate_blind_rejected(self):
        """重复盲测 / 重复解锁 → 拒绝。"""
        sm = self.fx.machine()
        self.fx.drive_to_model_locked(sm)
        sm.unlock_blind(unlock_id="U1", evaluator_id="eval-1",
                        evaluation_run_id="R1", synthetic_drill=True)
        with self.assertRaises(StateMachineError) as cm:
            sm.unlock_blind(unlock_id="U2", evaluator_id="eval-1",
                            evaluation_run_id="R2", synthetic_drill=True)
        self.assertIn("BLIND_ALREADY_UNLOCKED", str(cm.exception))
        sm.record_blind_results(evaluation_run_id="R1",
                                results=[{"ndcg": 0.5}], synthetic_drill=True)
        with self.assertRaises(StateMachineError) as cm:
            sm.record_blind_results(evaluation_run_id="R1",
                                    results=[{"ndcg": 0.6}], synthetic_drill=True)
        self.assertIn("BLIND_ALREADY_EVALUATED", str(cm.exception))
        # run_id 不一致的盲测结果也被拒绝（先于重复检查构造另一台机器验证）
        sm2_log = Path(self._td.name) / "log2.jsonl"
        sm2 = BlindEvalStateMachine(sm2_log, self.fx.protocol, self.fx.protocol_sha)
        self.fx.drive_to_model_locked(sm2)
        sm2.unlock_blind(unlock_id="U1", evaluator_id="eval-1",
                         evaluation_run_id="R1", synthetic_drill=True)
        with self.assertRaises(StateMachineError) as cm:
            sm2.record_blind_results(evaluation_run_id="R-OTHER",
                                     results=[{"ndcg": 0.5}], synthetic_drill=True)
        self.assertIn("EVAL_RUN_MISMATCH", str(cm.exception))

    def test_full_legal_flow_single_blind(self):
        """合法完整状态 → 允许一次盲测并进入终态（合成演练，非真实 H2）。"""
        sm = self.fx.machine()
        self.fx.drive_to_model_locked(sm)
        rec = sm.unlock_blind(unlock_id="U-DRILL-001", evaluator_id="evaluator-A",
                              evaluation_run_id="run-001", synthetic_drill=True)
        for key in ("unlock_id", "protocol_hash", "model_lock_hash", "dataset_hash",
                    "unlock_timestamp", "evaluator_id", "evaluation_run_id"):
            self.assertIn(key, rec)
        self.assertTrue(rec["synthetic_drill"], "演练记录必须标记 synthetic_drill")
        sm.record_blind_results(evaluation_run_id="run-001",
                                results=[{"ndcg_at_10": 0.42}], synthetic_drill=True)
        fin = sm.finalize(accepted=True, note="演练", synthetic_drill=True)
        self.assertEqual("FINAL_ACCEPTED", fin["state"])
        ok, detail = sm.verify_chain()
        self.assertTrue(ok, detail)
        self.assertEqual("FINAL_ACCEPTED", sm.current_state())

    def test_blocked_marker_not_misread(self):
        """BLOCKED 状态文件 → 不误判为正式实验结果；不得据此进入 DEV_EVALUATED。"""
        blocked = Path(self._td.name) / "04-real-model-evaluation.json"
        blocked.write_text(json.dumps(
            {"status": "BLOCKED", "not_an_experiment_result": True, "results": []},
            ensure_ascii=False), encoding="utf-8")
        self.assertTrue(is_blocked_marker(blocked))
        sm = self.fx.machine()
        sm.mark_registered(synthetic_drill=True)
        sm.mark_data_ready(intake_evidence_path=self.fx.intake,
                           consent_verified=2, intake_accepted=2,
                           synthetic_drill=True)
        sm.freeze_gold(gold_manifest_path=self.fx.gold, synthetic_drill=True)
        with self.assertRaises(StateMachineError) as cm:
            sm.mark_dev_evaluated(dev_report_path=blocked, synthetic_drill=True)
        self.assertIn("DEV_EVAL_NOT_DONE", str(cm.exception))
        # 含真实 results 的文件不豁免
        real = Path(self._td.name) / "blind.json"
        real.write_text(json.dumps({"status": "DONE", "results": [{"x": 1}]}),
                        encoding="utf-8")
        self.assertFalse(is_blocked_marker(real))

    def test_real_gold_missing_no_fake_unlock(self):
        """真实 Gold 缺失（清单不存在）→ 不伪造冻结/解锁成功。"""
        sm = self.fx.machine()
        sm.mark_registered(synthetic_drill=True)
        sm.mark_data_ready(intake_evidence_path=self.fx.intake,
                           consent_verified=2, intake_accepted=2,
                           synthetic_drill=True)
        with self.assertRaises(StateMachineError) as cm:
            sm.freeze_gold(gold_manifest_path=self.fx.root / "nope.json",
                           synthetic_drill=True)
        self.assertIn("GOLD_MISSING", str(cm.exception))

    # ---------------------------------------------------------- 防篡改
    def test_chain_tamper_detected(self):
        """改写/删除状态日志记录 → 链校验失败。"""
        sm = self.fx.machine()
        self.fx.drive_to_model_locked(sm)
        lines = self.fx.log.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[1])
        rec["consent_verified"] = 999  # 篡改证据字段
        lines[1] = json.dumps(rec, ensure_ascii=False)
        self.fx.log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok, detail = BlindEvalStateMachine(
            self.fx.log, self.fx.protocol, self.fx.protocol_sha).verify_chain()
        self.assertFalse(ok)
        self.assertIn("第 2 条", detail)

    def test_forged_lock_record_rejected(self):
        """手工拼接「字段齐全 + 自算哈希」的伪造 MODEL_LOCKED → 解锁时被拒绝。"""
        sm = self.fx.machine()
        sm.mark_registered(synthetic_drill=True)
        sm.mark_data_ready(intake_evidence_path=self.fx.intake,
                           consent_verified=2, intake_accepted=2,
                           synthetic_drill=True)
        sm.freeze_gold(gold_manifest_path=self.fx.gold, synthetic_drill=True)
        sm.mark_dev_evaluated(dev_report_path=self.fx.dev, synthetic_drill=True)
        # 攻击者绕过 lock_model，直接拼接一条 record_hash 自洽的 MODEL_LOCKED
        import hashlib as _h
        import time as _t
        records = [json.loads(x) for x in
                   self.fx.log.read_text(encoding="utf-8").splitlines() if x.strip()]
        forged = {
            "state": "MODEL_LOCKED", "event": "lock_model",
            **self.fx.lock_fields(protocol_sha256="f" * 64),  # 伪造协议哈希
            "dataset_hash": "e" * 64,                        # 伪造数据哈希
            "synthetic_drill": True,
            "seq": len(records) + 1,
            "timestamp": _t.strftime("%Y-%m-%dT%H:%M:%S"),
            "prev_hash": records[-1]["record_hash"],
        }
        canonical = json.dumps({k: v for k, v in forged.items() if k != "record_hash"},
                               sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        forged["record_hash"] = _h.sha256(canonical.encode("utf-8")).hexdigest()
        with self.fx.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(forged, ensure_ascii=False) + "\n")

        sm2 = BlindEvalStateMachine(self.fx.log, self.fx.protocol, self.fx.protocol_sha)
        ok, _ = sm2.verify_chain()
        self.assertTrue(ok, "哈希链自洽不代表证据可信——必须由证据锚定拒绝")
        with self.assertRaises(StateMachineError) as cm:
            sm2.unlock_blind(unlock_id="U1", evaluator_id="eval-1",
                             evaluation_run_id="R1", synthetic_drill=True)
        self.assertIn("PROTOCOL_HASH_MISMATCH", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
