# -*- coding: utf-8 -*-
"""Phase5-3 / M5 推理契约与降级可追溯性探针（真实执行，逐项登记）。

任务书第七节要求验证：
  MS01 模型注册表能力登记与声明一致（不存在的模型不冒充已完成）
  MS02 baseline 模式真实链路（启发式分、无降级快照、评分语义警示）
  MS03 显式模型缺失 + allow_fallback=True -> 显式降级（reason_code/model_id 可追溯）
  MS04 显式模型缺失 + allow_fallback=False -> 显式 MODEL_MISSING（不落运行记录）
  MS05 降级快照持久化与回读一致（未降级运行保持 NULL，不乐观回填）
  MS06 future_verified 槽位不冒充（FUTURE_MODEL_UNAVAILABLE 显式失败）
  MS07 正式模式门禁（formal + 未过中文验证的模型 -> MODEL_FORMAL_USE_FORBIDDEN）
  MS08 历史 checkpoint 在当前环境的真实加载状态（实测登记，不重训不冒充）
  MS09 评分口径（分数为排序参考分，formal_evaluation=False，非录用概率）
  MS10 版本可追踪（profile_version / model_version / scoring_config_version /
       job_set_snapshot / request_fingerprint 齐备）

纪律：
  * 全程使用临时隔离 sqlite + 私有存储（tests/phase5_2.BusinessHarness），
    不触碰开发库 data/private/dev.db 与任何生产库；
  * 测试数据全部为合成夹具（is_synthetic / 合成简历文本）；
  * 任一项真实执行失败 -> 状态 FAIL，进程退出码 1；
  * 历史权重仅做"加载实测"，绝不修改、转换或重训。

用法（项目根目录）：
  set PYTHONPATH=src
  python scripts/phase5_3/model_serving_probe.py --out reports/phase5-3/model-serving-probe.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT / "src"), str(ROOT / "tests" / "phase5_2")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

STATUSES = ("PASS", "FAIL", "NOT_RUN", "BLOCKED", "ENV_INCOMPATIBLE")


def _run_id() -> str:
    return os.environ.get("JM_RUN_ID") or f"local-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


class Registry:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, item_id: str, title: str, status: str, detail: str) -> None:
        assert status in STATUSES
        self.items.append({"id": item_id, "title": title, "status": status, "detail": detail})
        print(f"[{status:6s}] {item_id} {title} :: {detail}", flush=True)

    @property
    def failed(self) -> bool:
        return any(i["status"] == "FAIL" for i in self.items)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "reports" / "phase5-3" / "model-serving-probe.json"))
    args = ap.parse_args()

    from _util import SYNTHETIC_JOB_TEXT, BusinessHarness  # noqa: E402
    from job_matching.service.errors import ServiceError  # noqa: E402

    reg = Registry()
    h = BusinessHarness()
    try:
        admin = h.make_admin("admin_m5_probe")
        admin_token = h.login("admin_m5_probe", "Adm1n!2026pass")[1]

        # ---- 合成岗位 + 合成学生（真实业务链路） ----
        r = h.client.post("/api/v1/jobs", headers=h.auth(admin_token),
                          json={"title": "M5-推理契约合成岗",
                                "job_description": SYNTHETIC_JOB_TEXT,
                                "source": "synthetic",
                                "source_license": "CC0-synthetic"})
        assert r.status_code == 200, r.text
        job_id = r.json()["data"]["job"]["id"]
        h.client.post(f"/api/v1/jobs/{job_id}/parse", headers=h.auth(admin_token))

        h.register("stu_m5_probe", "Stu!2026pass")
        _u, token = h.login("stu_m5_probe", "Stu!2026pass")
        h.upload_resume(token)
        r = h.client.put("/api/v1/students/me/profile", headers=h.auth(token),
                         json={"confirm": True})
        assert r.status_code == 200, r.text

        # ============================================================ MS01
        # 真实业务 API 使用的同一注册表（h.biz.core.registry），不另建旁路
        mreg = h.biz.core.registry
        expect = {
            "baseline_skill_text_v1": ("not_a_trained_model", True),
            "legacy_match_proxy_v1": ("research_only_proxy_labels", False),
            "education_normalizer_v1": ("research_only_zh", False),
            "chinese_match_future_v1": ("pending_phase4_3b", False),
        }
        detail_parts, ms01_ok = [], True
        for mid, (eval_status, formal_ok) in expect.items():
            reg_row = mreg.get_optional(mid)
            if reg_row is None:
                # 注册为条件登记（依赖模型目录挂载）；缺失时如实登记，不算冒充
                detail_parts.append(f"{mid}=未登记(产物未挂载)")
                if mid in ("baseline_skill_text_v1", "chinese_match_future_v1"):
                    ms01_ok = False   # 这两个槽位必须始终存在
                continue
            got_eval, got_formal = reg_row.evaluation_status, reg_row.formal_use_allowed
            if got_eval != eval_status or got_formal != formal_ok:
                ms01_ok = False
            detail_parts.append(f"{mid}={got_eval}/formal:{got_formal}")
        try:
            mreg.get("no_such_model")
            ms01_ok = False
            detail_parts.append("no_such_model=竟然可查到")
        except ServiceError as e:
            if e.code != "MODEL_MISSING":
                ms01_ok = False
            detail_parts.append(f"no_such_model={e.code}")
        reg.add("MS01", "模型注册表能力登记与声明一致（不存在的模型不冒充）",
                "PASS" if ms01_ok else "FAIL", "; ".join(detail_parts))

        # ============================================================ MS02
        r = h.client.post("/api/v1/recommendations", headers=h.auth(token),
                          json={"mode": "baseline", "job_ids": [job_id]})
        if r.status_code == 200:
            d = r.json()["data"]
            rs = d["result_summary"]
            run_id_base = d["run"]["id"]
            ok = (rs["score_type"] == "heuristic_score"
                  and rs.get("degradation") is None
                  and any("score_semantics" in w for w in rs.get("warnings", []))
                  and d["run"].get("degradation_info") is None)
            reg.add("MS02", "baseline 真实链路（启发式分/无降级快照/语义警示）",
                    "PASS" if ok else "FAIL",
                    f"score_type={rs['score_type']}, degradation={rs.get('degradation')}, "
                    f"warnings={len(rs.get('warnings', []))} 条含 score_semantics="
                    f"{any('score_semantics' in w for w in rs.get('warnings', []))}")
        else:
            run_id_base = None
            reg.add("MS02", "baseline 真实链路（启发式分/无降级快照/语义警示）",
                    "FAIL", f"HTTP {r.status_code}: {r.text[:200]}")

        # ============================================================ MS03
        r = h.client.post("/api/v1/recommendations", headers=h.auth(token),
                          json={"mode": "experimental_model", "model_id": "no_such_model",
                                "allow_fallback": True, "job_ids": [job_id]})
        deg_run_id = None
        if r.status_code == 200:
            d = r.json()["data"]
            deg = (d["result_summary"].get("degradation") or {})
            ok = (deg.get("degraded") is True and deg.get("reason_code") == "MODEL_MISSING"
                  and deg.get("requested_model_id") == "no_such_model"
                  and d["result_summary"]["score_type"] == "heuristic_score")
            deg_run_id = d["run"]["id"]
            reg.add("MS03", "显式模型缺失 + allow_fallback=True -> 显式降级可追溯",
                    "PASS" if ok else "FAIL",
                    f"degradation={json.dumps(deg, ensure_ascii=False)[:180]}")
        else:
            reg.add("MS03", "显式模型缺失 + allow_fallback=True -> 显式降级可追溯",
                    "FAIL", f"HTTP {r.status_code}: {r.text[:200]}")

        # ============================================================ MS04
        from job_matching.service.reco_store import RecommendationRun  # noqa: E402
        from job_matching.infra.persistence import get_session  # noqa: E402

        def _count_runs() -> int:
            s = get_session()
            try:
                return s.query(RecommendationRun).count()
            finally:
                s.close()

        before = _count_runs()
        r = h.client.post("/api/v1/recommendations", headers=h.auth(token),
                          json={"mode": "experimental_model", "model_id": "no_such_model",
                                "allow_fallback": False, "job_ids": [job_id]})
        ok = (r.status_code == 503 and r.json()["error"]["code"] == "MODEL_MISSING"
              and _count_runs() == before)
        reg.add("MS04", "allow_fallback=False -> 显式 MODEL_MISSING 且不落运行记录",
                "PASS" if ok else "FAIL",
                f"HTTP {r.status_code}, code={r.json().get('error', {}).get('code')}, "
                f"runs {before} -> {_count_runs()}")

        # ============================================================ MS05
        if deg_run_id and run_id_base:
            r1 = h.client.get(f"/api/v1/recommendations/{deg_run_id}", headers=h.auth(token))
            r2 = h.client.get(f"/api/v1/recommendations/{run_id_base}", headers=h.auth(token))
            p1 = (r1.json()["data"]["run"].get("degradation_info") or {}) if r1.status_code == 200 else {}
            p2 = (r2.json()["data"]["run"].get("degradation_info") or None) if r2.status_code == 200 else "ERR"
            ok = (p1.get("degraded") is True and p1.get("reason_code") == "MODEL_MISSING"
                  and p2 is None)
            reg.add("MS05", "降级快照持久化回读一致（未降级保持 NULL 不回填）",
                    "PASS" if ok else "FAIL",
                    f"degraded_run.degradation_info={json.dumps(p1, ensure_ascii=False)[:150]}; "
                    f"baseline_run.degradation_info={p2}")
        else:
            reg.add("MS05", "降级快照持久化回读一致（未降级保持 NULL 不回填）",
                    "FAIL", "前置运行未成功（MS02/MS03）")

        # ============================================================ MS06
        r = h.client.post("/api/v1/recommendations", headers=h.auth(token),
                          json={"mode": "future_verified", "job_ids": [job_id]})
        ok = (r.status_code == 503
              and r.json()["error"]["code"] == "FUTURE_MODEL_UNAVAILABLE")
        reg.add("MS06", "future_verified 槽位不冒充（显式不可用）",
                "PASS" if ok else "FAIL",
                f"HTTP {r.status_code}, code={r.json().get('error', {}).get('code')}")

        # ============================================================ MS07
        if mreg.get_optional("legacy_match_proxy_v1") is None:
            reg.add("MS07", "正式模式门禁（formal + 未验证模型拒绝）", "NOT_RUN",
                    "legacy_match_proxy_v1 未登记（模型目录未挂载）")
        else:
            try:
                from job_matching.service.contracts import StudentProfile as StudentProfileContract

                user = h.biz.accounts.authenticate(username="stu_m5_probe", password="Stu!2026pass")
                prof = h.biz.students.latest_profile(user)
                student = StudentProfileContract.from_dict(
                    (prof.get("profile_data") or {}).get("profile") or {})
                pairs = h.biz.jobs.matchable_jobs([job_id])
                h.biz.core.matching.rank(
                    student, [p for _j, p in pairs] or [{"id": job_id}],
                    {"mode": "experimental_model", "model_id": "legacy_match_proxy_v1",
                     "formal": True, "allow_fallback": False})
                reg.add("MS07", "正式模式门禁（formal + 未验证模型拒绝）", "FAIL",
                        "formal=True 竟然未拒绝")
            except ServiceError as e:
                ok = e.code == "MODEL_FORMAL_USE_FORBIDDEN"
                reg.add("MS07", "正式模式门禁（formal + 未验证模型拒绝）",
                        "PASS" if ok else "FAIL", f"code={e.code}")

        # ============================================================ MS08
        if mreg.get_optional("legacy_match_proxy_v1") is None:
            reg.add("MS08", "历史 checkpoint 当前环境真实加载状态", "NOT_RUN",
                    "legacy_match_proxy_v1 未登记（模型目录未挂载），不冒充已验证")
        else:
            try:
                obj = mreg.load("legacy_match_proxy_v1")
                info = obj.info() if hasattr(obj, "info") else {}
                reg.add("MS08", "历史 checkpoint 当前环境真实加载状态",
                        "PASS", f"loaded, run_id={info.get('run_id', '?')}（未修改未重训）")
            except ServiceError as e:
                reg.add("MS08", "历史 checkpoint 当前环境真实加载状态",
                        "ENV_INCOMPATIBLE" if e.code == "MODEL_ENV_INCOMPATIBLE" else "FAIL",
                        f"code={e.code}（显式登记，不重训不冒充）")

        # ============================================================ MS09
        r = h.client.post("/api/v1/recommendations", headers=h.auth(token),
                          json={"mode": "baseline", "job_ids": [job_id]})
        d = r.json()["data"]
        rs = d["result_summary"]
        ok = (rs.get("formal_evaluation") is False
              and rs["score_type"] in ("heuristic_score", "model_raw_score")
              and any("不是录用概率" in w for w in rs.get("warnings", []))
              and "不是录用概率" in json.dumps(d, ensure_ascii=False))
        reg.add("MS09", "评分口径（排序参考分/非录用概率/formal_evaluation=False）",
                "PASS" if ok else "FAIL",
                f"score_type={rs['score_type']}, formal_evaluation={rs.get('formal_evaluation')}")

        # ============================================================ MS10
        run = d["run"]
        keys = ("profile_version", "model_version", "scoring_config_version",
                "job_set_snapshot", "request_fingerprint")
        missing = [k for k in keys if run.get(k) in (None, "", [])]
        reg.add("MS10", "版本可追踪（画像/模型/评分配置/岗位快照/请求指纹）",
                "PASS" if not missing else "FAIL",
                f"缺失={missing or '无'}; profile_version={run.get('profile_version')}, "
                f"model_version={run.get('model_version')}, "
                f"scoring_config_version={run.get('scoring_config_version')}")

    finally:
        h.close()

    out = {
        "generated_by": "scripts/phase5_3/model_serving_probe.py",
        "run_id": _run_id(),
        "commit": _commit(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": sys.version.split()[0],
            "models_root_exists": (ROOT / "models").exists(),
            "note": "隔离临时 sqlite + 合成夹具；历史权重只做加载实测",
        },
        "items": reg.items,
        "summary": {
            "total": len(reg.items),
            "pass": sum(1 for i in reg.items if i["status"] == "PASS"),
            "fail": sum(1 for i in reg.items if i["status"] == "FAIL"),
            "env_incompatible": sum(1 for i in reg.items if i["status"] == "ENV_INCOMPATIBLE"),
        },
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n登记表 -> {out_path} | PASS={out['summary']['pass']} "
          f"FAIL={out['summary']['fail']} ENV_INCOMPATIBLE={out['summary']['env_incompatible']}")
    return 1 if reg.failed else 0


if __name__ == "__main__":
    sys.exit(main())
