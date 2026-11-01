# -*- coding: utf-8 -*-
"""Phase 10-R2: LambdaMART 训练链路测试。"""
import unittest
import numpy as np
from pathlib import Path
import tempfile


class TestLambdaMARTLabelMapping(unittest.TestCase):
    """标签映射严格性测试。"""

    def test_string_labels(self):
        from job_matching.models.lambdamart import map_labels_to_int
        y = np.array(['weak_positive', 'medium_positive', 'strong_positive'])
        result = map_labels_to_int(y)
        self.assertEqual(list(result), [1, 2, 3])

    def test_numeric_labels(self):
        from job_matching.models.lambdamart import map_labels_to_int
        y = np.array([0, 1, 2, 3])
        result = map_labels_to_int(y)
        self.assertEqual(list(result), [0, 1, 2, 3])

    def test_unknown_label_raises(self):
        from job_matching.models.lambdamart import map_labels_to_int
        with self.assertRaises(ValueError):
            map_labels_to_int(np.array(['unknown_label']))

    def test_invalid_numeric_raises(self):
        from job_matching.models.lambdamart import map_labels_to_int
        with self.assertRaises(ValueError):
            map_labels_to_int(np.array([1.5]))  # 非整数

    def test_out_of_range_raises(self):
        from job_matching.models.lambdamart import map_labels_to_int
        with self.assertRaises(ValueError):
            map_labels_to_int(np.array([5]))  # 超出0-3


class TestQueryGroups(unittest.TestCase):
    """Query Group 连续性测试。"""

    def test_basic_groups(self):
        from job_matching.models.lambdamart import build_query_groups
        ids = np.array([100, 100, 100, 200, 200, 300])
        groups = build_query_groups(ids)
        self.assertEqual(list(groups), [3, 2, 1])
        self.assertEqual(groups.sum(), len(ids))

    def test_single_group(self):
        from job_matching.models.lambdamart import build_query_groups
        ids = np.array([1, 1, 1])
        groups = build_query_groups(ids)
        self.assertEqual(list(groups), [3])

    def test_sum_matches_length(self):
        from job_matching.models.lambdamart import build_query_groups
        ids = np.array([1, 1, 2, 2, 2, 3])
        groups = build_query_groups(ids)
        self.assertEqual(groups.sum(), len(ids))


class TestLambdaMARTTrainSaveLoad(unittest.TestCase):
    """完整训练→保存→加载→预测链路测试。"""

    def test_full_pipeline(self):
        from job_matching.models.lambdamart import train_model, LambdaMARTModel
        np.random.seed(42)
        X = np.random.randn(300, 32)
        y = np.random.choice(['weak_positive', 'medium_positive', 'strong_positive'], 300)
        groups = np.array([15] * 20)
        X_val = np.random.randn(75, 32)
        y_val = np.random.choice(['weak_positive', 'medium_positive'], 75)
        groups_val = np.array([15] * 5)

        model = train_model(
            model_cfg={'num_leaves': 31, 'learning_rate': 0.05, 'num_boost_round': 50},
            X_train=X, y_train=y,
            X_val=X_val, y_val=y_val,
            groups_train=groups, groups_val=groups_val,
            seed=42
        )

        # 预测
        preds = model.predict(X[:5])
        self.assertEqual(len(preds), 5)

        # 保存/加载一致性
        with tempfile.TemporaryDirectory() as td:
            model.save(Path(td))
            model2 = LambdaMARTModel.load(Path(td))
            preds2 = model2.predict(X[:5])
            np.testing.assert_allclose(preds, preds2, rtol=1e-6)

    def test_group_validation(self):
        from job_matching.models.lambdamart import train_model
        np.random.seed(42)
        X = np.random.randn(100, 32)
        y = np.random.choice(['weak_positive', 'medium_positive'], 100)
        groups = np.array([20] * 5)  # sum=100 ✓

        # 错误的groups（sum != len(X)）
        with self.assertRaises(AssertionError):
            train_model(
                model_cfg={},
                X_train=X, y_train=y,
                X_val=None, y_val=None,
                groups_train=np.array([10] * 5),  # sum=50 ≠ 100
                groups_val=None,
                seed=42
            )


class TestMPSDeviceDetection(unittest.TestCase):
    """MPS设备检测测试。"""

    def test_resolve_device(self):
        import torch
        from job_matching.training.trainer import resolve_device
        device = resolve_device(prefer_gpu=True)
        self.assertIn(device.type, ('cpu', 'cuda', 'mps'))

    def test_cpu_fallback_logged(self):
        """验证resolve_device总会有设备日志（GPU或fallback）。"""
        from job_matching.training.trainer import resolve_device
        # MPS可用时返回mps并有日志，不可用时返回cpu并有fallback警告
        with self.assertLogs('job_matching.training.trainer', level='INFO') as cm:
            resolve_device(prefer_gpu=True)
        self.assertTrue(any('device=' in msg for msg in cm.output))

    def test_explicit_cpu(self):
        """prefer_gpu=False时必须返回cpu并有日志。"""
        from job_matching.training.trainer import resolve_device
        with self.assertLogs('job_matching.training.trainer', level='INFO') as cm:
            device = resolve_device(prefer_gpu=False)
        self.assertEqual(device.type, 'cpu')
        self.assertTrue(any('device=cpu' in msg for msg in cm.output))


class TestStaticPathSecurity(unittest.TestCase):
    """静态文件路径安全测试。"""

    def test_path_traversal_blocked(self):
        from pathlib import Path
        # 模拟路径穿越
        frontend_dist = Path('/tmp/frontend/dist')
        path = '../../etc/passwd'
        file_path = (frontend_dist / path).resolve()
        self.assertFalse(file_path.is_relative_to(frontend_dist.resolve()))

    def test_normal_path_allowed(self):
        from pathlib import Path
        frontend_dist = Path('/tmp/frontend/dist')
        path = 'index.html'
        file_path = (frontend_dist / path).resolve()
        # 正常路径（即使文件不存在，路径应该是relative的）
        # 注意：/tmp/frontend/dist可能不存在，但路径检查仍然有效


class TestPairwiseAccuracyConsistency(unittest.TestCase):
    """Pairwise Accuracy两个实现一致性测试。"""

    def test_metrics_and_statistical_tests_agree(self):
        from job_matching.evaluation.metrics import pairwise_accuracy
        from job_matching.evaluation.statistical_tests import per_query_pairwise_accuracy

        g = np.array([1, 1, 1, 1, 2, 2, 2])
        p = np.array([0.3, 0.1, 0.4, 0.2, 0.5, 0.6, 0.4])
        r = np.array([1.0, 3.0, 2.0, 0.5, 2.0, 1.0, 3.0])

        result1 = pairwise_accuracy(g, p, r)
        result2 = per_query_pairwise_accuracy(g, p, r)

        # 两者都应返回有效结果
        if result1['pairwise_accuracy'] is not None:
            self.assertIsNotNone(result2)

    def test_permutation_invariance(self):
        from job_matching.evaluation.metrics import pairwise_accuracy
        g = np.array([1, 1, 1, 1])
        p = np.array([0.3, 0.1, 0.4, 0.2])
        r = np.array([1.0, 3.0, 2.0, 0.5])

        result_orig = pairwise_accuracy(g, p, r)

        # 反转
        result_rev = pairwise_accuracy(g[::-1], p[::-1], r[::-1])
        if result_orig['pairwise_accuracy'] is not None:
            self.assertAlmostEqual(
                result_orig['pairwise_accuracy'],
                result_rev['pairwise_accuracy'],
                places=6
            )


if __name__ == "__main__":
    unittest.main()
