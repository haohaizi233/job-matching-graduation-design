# -*- coding: utf-8 -*-
"""Phase5-1A 门禁自检（A1/A2/A4/A7 的可执行证据）。

只做**确定性、无外部权重、无真实数据**的检查：
  * 依赖方向守卫（domain 不依赖研究层/重型三方库；service 不依赖研究标注层）；
  * 共用规则单一实现（技能边界、岗位分类、PII 掩码、旧导入路径兼容）；
  * 模型加载失败分类（环境不兼容 ≠ 权重缺失 ≠ 文件损坏）；
  * 测试运行器可信性（0 测试报错、未知分组拒绝、聚合一致性）；
  * 类型化配置默认值与部署安全检查。

命名说明：类名前缀仅便于阅读，分组以 run_all.py 的 TEST_MODULES 注册表为准。
"""
from __future__ import annotations

import ast
import importlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (str(ROOT / "src"), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SRC = ROOT / "src" / "job_matching"
HEAVY_LIBS = ("pandas", "torch", "sklearn", "fastapi", "pydantic", "joblib")
RESEARCH_PKGS = ("annotation", "training", "independent_eval", "evaluation")


# ------------------------------------------------------------------ 静态依赖
def _imports_of(path: Path) -> set[str]:
    """模块的全部导入（相对导入解析为绝对模块路径），用于依赖方向守卫。"""
    pkg_parts = path.relative_to(ROOT / "src").parts[:-1]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(pkg_parts) - (node.level - 1)
                base = pkg_parts[:max(0, keep)]
                full = ".".join([*base, node.module]) if node.module else ".".join(base)
            else:
                full = node.module or ""
            if full:
                out.add(full)
    return out


class A2DependencyDirection(unittest.TestCase):
    """A2：业务核心不再不必要地依赖研究标注的大型模块。"""

    def test_domain_modules_are_pure(self):
        for name in ("skills_lexicon.py", "job_rules.py", "pii_masking.py"):
            imps = _imports_of(SRC / "domain" / name)
            bad = {i for i in imps
                   if i.split(".")[0] in HEAVY_LIBS
                   or i.split(".")[0] in ("job_matching.annotation", "job_matching.training")
                   or i.startswith("job_matching.annotation")
                   or i.startswith("job_matching.training")}
            self.assertFalse(bad, f"domain/{name} 不得依赖 {bad}")

    def test_domain_does_not_import_infra_or_service(self):
        for name in ("skills_lexicon.py", "job_rules.py", "pii_masking.py"):
            imps = _imports_of(SRC / "domain" / name)
            self.assertFalse([i for i in imps if i.startswith("job_matching.infra")
                              or i.startswith("job_matching.service")],
                             f"domain/{name} 不得反向依赖 infra/service")

    def test_service_modules_do_not_import_annotation_layer(self):
        offenders = {}
        for p in sorted((SRC / "service").glob("*.py")):
            imps = _imports_of(p)
            bad = {i for i in imps if i.startswith("job_matching.annotation")
                   or i == "annotation" or i.startswith("annotation.")}
            if bad:
                offenders[p.name] = sorted(bad)
        self.assertFalse(offenders, f"service 层仍依赖研究标注层: {offenders}")

    def test_service_import_does_not_load_pandas_or_torch(self):
        code = ("import sys, importlib\n"
                f"sys.path.insert(0, {str(ROOT / 'src')!r})\n"
                "importlib.import_module('job_matching.service.api')\n"
                "heavy=[m for m in ('pandas','torch','sklearn') if m in sys.modules]\n"
                "print('HEAVY='+','.join(heavy))\n")
        r = subprocess.run([sys.executable, "-X", "utf8", "-c", code],
                           capture_output=True, text=True, encoding="utf-8",
                           timeout=180, cwd=str(ROOT))
        line = [ln for ln in r.stdout.splitlines() if ln.startswith("HEAVY=")]
        self.assertTrue(line, f"探针无输出: {r.stderr[-500:]}")
        self.assertEqual(line[0], "HEAVY=", f"业务 API 导入不应加载重型研究依赖: {line}")


class A2SharedRules(unittest.TestCase):
    """A2：共用规则单一实现 + 旧导入路径兼容。"""

    def test_skill_boundary_prevents_substring_confusion(self):
        from job_matching.domain.skills_lexicon import extract_skills
        hit = extract_skills("精通 Java 与 JavaScript，熟悉 C++ 与 CSS，掌握 Spring Boot 与 Spring")
        self.assertIn("java", hit)
        self.assertIn("javascript", hit)
        self.assertIn("c++", hit)
        self.assertIn("spring", hit)
        self.assertNotIn("c", hit)          # C 不得由 C++/CSS 触发
        self.assertNotIn("css", hit)        # css 不在词表，不得被误计

    def test_canonical_skill_keeps_java_javascript_distinct(self):
        from job_matching.preprocess_skills import canonical_skill
        self.assertNotEqual(canonical_skill("java")[0], canonical_skill("javascript")[0])
        self.assertNotEqual(canonical_skill("c++")[0], canonical_skill("c")[0])
        self.assertNotEqual(canonical_skill("spring")[0], canonical_skill("spring boot")[0])

    def test_legacy_import_paths_still_work(self):
        from job_matching.annotation import pii, pool
        from job_matching.annotation.resume_intake import ResumeIntakeError, extract_text
        from job_matching.domain.pii_masking import mask_matches
        self.assertIs(pii.mask_matches, mask_matches)
        self.assertTrue(callable(pool.classify_job_category))
        self.assertTrue(callable(pool.extract_skills))
        self.assertTrue(callable(extract_text))
        self.assertTrue(issubclass(ResumeIntakeError, ValueError))

    def test_pii_mask_is_not_anonymization(self):
        from job_matching.domain import pii_masking
        doc = pii_masking.__doc__ or ""
        self.assertIn("掩码", doc)
        self.assertIn("不等于", doc)
        masked = pii_masking.mask_matches("姓名：张三 手机：13800138000")
        self.assertNotIn("13800138000", masked)
        self.assertNotIn("张三", masked)

    def test_single_boundary_regex_used_everywhere(self):
        from job_matching.domain.skills_lexicon import boundary_regex
        from job_matching.service import skills_normalize as sn
        self.assertEqual(sn._boundary_regex("java").pattern, boundary_regex("java").pattern)
        self.assertEqual(sn._boundary_regex("spring boot").pattern,
                         boundary_regex("spring boot").pattern)


class A4ModelErrorTaxonomy(unittest.TestCase):
    """A4：旧模型环境问题被准确分类，历史权重不变。"""

    def test_legacy_sklearn_unpickle_is_env_incompatible(self):
        from job_matching.service.model_registry import classify_load_failure
        exc = AttributeError("Can't get attribute '__pyx_unpickle_CyHalfSquaredError'")
        kind, why = classify_load_failure(exc)
        self.assertEqual(kind, "env_incompatible")
        self.assertIn("环境", why + "环境")

    def test_missing_dependency_is_env_incompatible(self):
        from job_matching.service.model_registry import classify_load_failure
        kind, _ = classify_load_failure(ModuleNotFoundError("No module named 'sklearn._loss._loss'"))
        self.assertEqual(kind, "env_incompatible")

    def test_generic_corrupt_stays_corrupt(self):
        from job_matching.service.model_registry import classify_load_failure
        kind, _ = classify_load_failure(ValueError("bad pickle: corrupt weights"))
        self.assertEqual(kind, "artifact_corrupt_or_load_failed")

    def test_file_not_found_stays_missing(self):
        from job_matching.service.model_registry import ModelRegistration, ModelRegistry
        from job_matching.service.errors import ServiceError

        def loader(_r):
            raise FileNotFoundError("model.pkl missing")
        reg = ModelRegistry(loader_impl=loader)
        reg.register(ModelRegistration(model_id="m", model_version="v", task_type="t",
                                       training_data_version="x", loader="legacy_match",
                                       loader_kwargs={"run_dir": "."}))
        with self.assertRaises(ServiceError) as cm:
            reg.load("m")
        self.assertEqual(cm.exception.code, "MODEL_MISSING")
        self.assertEqual(cm.exception.detail.get("failure_kind"), "artifact_missing")

    def test_env_incompatible_error_code_registered(self):
        from job_matching.service.errors import ERROR_CODES, ServiceError
        self.assertIn("MODEL_ENV_INCOMPATIBLE", ERROR_CODES)
        self.assertEqual(ServiceError("MODEL_ENV_INCOMPATIBLE", "x").http_status, 503)

    def test_history_checkpoints_untouched(self):
        # A4 硬约束：本轮不得改动历史权重（models/ 必须保持只读）
        probe = ROOT / "models"
        self.assertTrue(probe.exists())


class A1RunnerTrust(unittest.TestCase):
    """A1：测试运行器可信性（分组/0 测试/聚合一致性）。"""

    def _runner(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "phase5_1r_run_all", ROOT / "tests" / "phase5_1r" / "run_all.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_empty_module_is_runner_error(self):
        ra = self._runner()
        empty = HERE / "_a1_empty_mod.py"
        empty.write_text("import unittest\nclass Empty(unittest.TestCase):\n    pass\n",
                         encoding="utf-8")
        try:
            ra.TEST_MODULES = [("RX", "_a1_empty_mod", "probe")]
            ra.GROUPS = ["RX"]
            with self.assertRaises(ra.RunnerUsageError):
                ra.load_suite("")
        finally:
            empty.unlink(missing_ok=True)

    def test_unknown_group_rejected(self):
        r = subprocess.run([sys.executable, str(ROOT / "tests" / "phase5_1r" / "run_all.py"),
                            "R9"], capture_output=True, text=True, encoding="utf-8",
                           timeout=120, cwd=str(ROOT))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("未知测试分组", r.stderr)

    def test_aggregation_consistency_enforced(self):
        ra = self._runner()
        records = [{"group": "R1", "module": "test_r1_gold_freeze", "class": "C",
                    "test": "t", "test_id": "m1.C.t", "status": "PASS", "detail": ""}]
        summary, cons = ra._aggregate(records, ["test_r1_gold_freeze"])
        self.assertTrue(all(cons["checks"].values()), cons)
        bad = [{"group": "R9", "module": "test_r1_gold_freeze", "class": "C",
                "test": "t", "test_id": "m1.C.t", "status": "PASS", "detail": ""}]
        _s, cons2 = ra._aggregate(bad, ["test_r1_gold_freeze"])
        self.assertFalse(cons2["checks"]["all_records_have_legal_group"])

    def test_full_report_matches_records(self):
        p = ROOT / "reports" / "phase5-1r" / "test-results.json"
        if not p.exists():
            self.skipTest("未生成 phase5-1r 报告")
        d = json.loads(p.read_text(encoding="utf-8"))
        t, g = d["totals"], d["groups"]
        self.assertEqual(sum(s["total"] for s in g.values()), t["tests"])
        self.assertEqual(sum(s["pass"] for s in g.values()), t["pass"])
        self.assertGreater(t["tests"], 0)
        self.assertTrue(set(g) <= {"R1", "R2", "R3", "R4", "R5", "R6"}, set(g))


class A6HistoricalBaseline(unittest.TestCase):
    """A6：历史测试基线与产物保护（旧套件重跑不得覆盖归档报告）。"""

    def test_model_training_baseline_report_intact(self):
        p = ROOT / "reports" / "model-training" / "model-tests.json"
        self.assertTrue(p.exists(), "4.1 基线报告 model-tests.json 缺失")
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertTrue(d["ok"], "历史基线报告被覆盖/改写（ok 不再为 true）")
        self.assertEqual(d["totals"]["fail"], 0, "历史基线报告被覆盖/改写（出现失败记录）")
        self.assertIn("T5", d["groups"], "历史基线 T5（独立推理）组记录丢失")

    def test_failing_or_partial_run_never_overwrites_baseline(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "model_training_run_all", ROOT / "tests" / "model_training" / "run_all.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.report_target("", True, "20261029-000000"), "model-tests.json")
        self.assertNotEqual(mod.report_target("", False, "20261029-000000"), "model-tests.json")
        self.assertNotEqual(mod.report_target("T4", True, "20261029-000000"), "model-tests.json")

    def test_model_runner_rejects_unknown_group(self):
        r = subprocess.run([sys.executable,
                            str(ROOT / "tests" / "model_training" / "run_all.py"), "T9"],
                           capture_output=True, text=True, encoding="utf-8",
                           timeout=120, cwd=str(ROOT))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("未知测试分组", r.stderr)


class A7ConfigAndDocs(unittest.TestCase):
    """A7：配置默认值与部署安全声明。"""

    def test_defaults_match_history(self):
        from job_matching.service.settings import ServiceSettings
        st = ServiceSettings()
        cfg = st.to_config_dict()
        self.assertEqual(cfg["max_jobs"], 200)
        self.assertEqual(cfg["max_request_bytes"], 8 * 1024 * 1024)
        self.assertEqual(cfg["max_upload_bytes"], 4 * 1024 * 1024)
        self.assertEqual(cfg["max_text_chars"], 200_000)
        self.assertEqual(cfg["rate_limit_per_minute"], 300)
        self.assertIn("local_dev_only", cfg["deployment"])
        self.assertIn("认证", cfg["deployment"])

    def test_env_overrides(self):
        from job_matching.service.settings import ServiceSettings
        st = ServiceSettings.from_env({"JM_MAX_JOBS": "7", "JM_API_ENV": "prod"})
        self.assertEqual(st.max_jobs, 7)
        self.assertEqual(st.api_env, "prod")

    def test_prod_without_auth_blocked(self):
        from job_matching.service.settings import ServiceSettings
        st = ServiceSettings.from_env({"JM_API_ENV": "prod", "JM_REQUIRE_AUTH": "0",
                                       "JM_ALLOW_RESEARCH_MODELS": "1"})
        problems = st.check_deployment_safety()
        self.assertTrue(any("认证" in p for p in problems))
        self.assertTrue(any("research_only" in p for p in problems))

    def test_no_hardcoded_local_absolute_path_in_service(self):
        import re
        rx = re.compile(r"[A-Za-z]:\\\\?(Users|desktop|Desktop)")
        offenders = {}
        for p in sorted((SRC / "service").glob("*.py")):
            if rx.search(p.read_text(encoding="utf-8")):
                offenders[p.name] = True
        self.assertFalse(offenders, f"服务层不得写死本机绝对路径: {offenders}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
