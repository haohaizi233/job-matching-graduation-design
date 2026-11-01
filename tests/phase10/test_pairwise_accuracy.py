"""P0: Pairwise Accuracy 顺序置换不变性测试。"""
import unittest
import numpy as np


class TestPairwiseAccuracyPermutation(unittest.TestCase):
    """验证Pairwise Accuracy的顺序置换不变性。"""

    def setUp(self):
        from src.job_matching.evaluation.metrics import pairwise_accuracy
        self.func = pairwise_accuracy

    def test_original_order(self):
        g = np.array([1, 1, 1, 1])
        p = np.array([0.3, 0.1, 0.4, 0.2])
        r = np.array([1.0, 3.0, 2.0, 0.5])
        result = self.func(g, p, r)
        self.assertIsNotNone(result["pairwise_accuracy"])

    def test_reversed_order(self):
        g = np.array([1, 1, 1, 1])
        p = np.array([0.3, 0.1, 0.4, 0.2])
        r = np.array([1.0, 3.0, 2.0, 0.5])
        # 反转顺序
        g_rev = g[::-1]
        p_rev = p[::-1]
        r_rev = r[::-1]
        result_orig = self.func(g, p, r)
        result_rev = self.func(g_rev, p_rev, r_rev)
        self.assertAlmostEqual(
            result_orig["pairwise_accuracy"],
            result_rev["pairwise_accuracy"],
            places=6
        )

    def test_random_permutation(self):
        g = np.array([1, 1, 1, 1])
        p = np.array([0.3, 0.1, 0.4, 0.2])
        r = np.array([1.0, 3.0, 2.0, 0.5])
        result_orig = self.func(g, p, r)
        
        # 随机置换
        np.random.seed(42)
        perm = np.random.permutation(4)
        result_perm = self.func(g[perm], p[perm], r[perm])
        
        self.assertAlmostEqual(
            result_orig["pairwise_accuracy"],
            result_perm["pairwise_accuracy"],
            places=6
        )

    def test_all_predictions_equal(self):
        g = np.array([1, 1, 1, 1])
        p = np.array([0.5, 0.5, 0.5, 0.5])  # 所有预测相等
        r = np.array([1.0, 3.0, 2.0, 0.5])
        result = self.func(g, p, r)
        # 同分预测计0.5
        self.assertAlmostEqual(result["pairwise_accuracy"], 0.5, places=6)

    def test_all_labels_equal(self):
        g = np.array([1, 1, 1, 1])
        p = np.array([0.3, 0.1, 0.4, 0.2])
        r = np.array([2.0, 2.0, 2.0, 2.0])  # 所有标签相等
        result = self.func(g, p, r)
        # 全同分组不计入
        self.assertIsNone(result["pairwise_accuracy"])

    def test_single_sample(self):
        g = np.array([1])
        p = np.array([0.5])
        r = np.array([1.0])
        result = self.func(g, p, r)
        # 单样本组不计入
        self.assertIsNone(result["pairwise_accuracy"])

    def test_multiple_queries(self):
        g = np.array([1, 1, 2, 2, 2])
        p = np.array([0.3, 0.1, 0.4, 0.2, 0.5])
        r = np.array([1.0, 3.0, 2.0, 0.5, 1.5])
        result = self.func(g, p, r)
        self.assertIsNotNone(result["pairwise_accuracy"])


if __name__ == "__main__":
    unittest.main()
