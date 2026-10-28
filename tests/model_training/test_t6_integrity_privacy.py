# -*- coding: utf-8 -*-
"""T6 原始数据完整性与日志隐私（验收项 13、14）。

 13. data/raw 原始数据哈希与迁移清单一致（不得被训练流程改写）。
 14. 训练日志不含个人敏感信息（邮箱 / 手机号 / 身份证号 / 原始文本字段名）。
"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest

from _util import LOG_DIR, ROOT

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
CN_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
CN_ID = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
FORBIDDEN_TEXT_FIELDS = ["resume_text", "experience_text", "education_text",
                         "job_description", "job_text"]


class T6IntegrityPrivacy(unittest.TestCase):
    def test_raw_data_hashes_unchanged(self):
        proc = subprocess.run([sys.executable, "scripts/verify_data_integrity.py", "--quiet"],
                              cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        self.assertEqual(proc.returncode, 0,
                         f"原始数据哈希校验失败:\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")

    def test_training_logs_have_no_sensitive_info(self):
        if not LOG_DIR.exists():
            self.skipTest("尚无训练日志")
        logs = sorted(LOG_DIR.glob("*.log"))
        if not logs:
            self.skipTest("尚无训练日志")
        problems = []
        for log in logs:
            text = log.read_text(encoding="utf-8", errors="replace")
            for name, rx in (("email", EMAIL), ("phone", CN_PHONE), ("id_card", CN_ID)):
                hit = rx.search(text)
                if hit:
                    problems.append(f"{log.name}: 疑似 {name} -> {hit.group(0)[:6]}***")
            for field in FORBIDDEN_TEXT_FIELDS:
                if field in text:
                    problems.append(f"{log.name}: 出现原始文本字段 {field}")
        self.assertEqual(problems, [], "训练日志存在敏感信息风险: " + "; ".join(problems))


if __name__ == "__main__":
    unittest.main()
