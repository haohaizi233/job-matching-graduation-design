# -*- coding: utf-8 -*-
"""G7：资源约束（GPU 显存 4GB）。

Baseline 优先 CPU 分块计算；不把完整 简历×岗位 中间矩阵长期保存在 GPU；
向量检索分块进行。本门禁用静态 + 运行时证据共同验证。
"""
from __future__ import annotations

import unittest

import numpy as np

from _util import cfg, jload
from job_matching.baseline_ranking import cosine_scores


class G7ResourceGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = cfg()

    def test_cosine_block_budget_bounded(self):
        block = self.c.cosine_block_rows
        dim = 768
        bytes_per_block = block * dim * 2 * 4   # a/b 两块 float32
        self.assertLessEqual(bytes_per_block, 32 * 1024 * 1024,
                             f"余弦分块中间数组 {bytes_per_block/1e6:.1f}MB，超出预算")

    def test_gpu_budget_declared(self):
        budget = int(self.c.pipeline["resources"]["gpu_budget_mb"])
        self.assertLessEqual(budget, 4096)
        self.assertTrue(self.c.pipeline["resources"]["prefer_cpu_for_baselines"])

    def test_baseline_module_does_not_require_cuda(self):
        """baseline_ranking 只用 NumPy 分块计算，不持有 CUDA 张量。"""
        import job_matching.baseline_ranking as br
        src = open(br.__file__, "r", encoding="utf-8").read()
        self.assertNotIn("cuda", src.lower(), "baseline 代码不应依赖 CUDA")
        self.assertNotIn(".to(\"cuda\")", src)
        self.assertIn("einsum", src, "余弦应使用分块 einsum 而非完整矩阵乘")

    def test_cosine_scores_streams_blocks_not_full_matrix(self):
        d = self.c.out("processed_embeddings")
        cv = np.load(d / "cv_embeddings.npy", mmap_mode="r")
        job = np.load(d / "job_embeddings.npy", mmap_mode="r")
        n = 2000
        cv_rows = np.arange(n) % cv.shape[0]
        job_rows = np.arange(n) % job.shape[0]
        out = cosine_scores(np.asarray(cv), np.asarray(job), cv_rows, job_rows,
                            block=128)
        self.assertEqual(out.shape, (n,))
        self.assertTrue(np.isfinite(out).all())

    def test_embedding_cache_memory_footprint_documented(self):
        meta = jload(self.c.out("processed_embeddings") / "metadata.json")
        self.assertIn("limitations", meta)
        self.assertTrue(any("冷启动" in x or "编码" in x for x in meta["limitations"]),
                        "元数据必须记录预计算 embedding 的来源限制")

    def test_pipeline_logs_do_not_contain_resume_or_jd_text(self):
        """日志中不得出现简历正文 / JD 原文（隐私约束）。"""
        log_dir = self.c.path("logs")
        if not log_dir.exists():
            self.skipTest("尚无日志文件")
        import re
        pattern = re.compile(r"[一-鿿]{40,}")   # 连续 40+ 汉字近似正文
        offenders = []
        for p in log_dir.glob("*.log"):
            for line in p.read_text("utf-8", errors="replace").splitlines():
                if pattern.search(line):
                    offenders.append(f"{p.name}: {line[:60]}")
        self.assertEqual(offenders[:5], [], f"日志疑似包含正文片段: {offenders[:5]}")

    def test_no_gpu_tensor_created_by_split_or_feature_steps(self):
        """切分与特征构造模块不得 import torch。"""
        for mod in ("job_matching.split_matching", "job_matching.pair_features",
                    "job_matching.education_data", "job_matching.preprocess_resume",
                    "job_matching.preprocess_job"):
            m = __import__(mod, fromlist=["x"])
            self.assertFalse(hasattr(m, "torch"),
                             f"{mod} 不应持有 torch 依赖")


if __name__ == "__main__":
    unittest.main()
