# -*- coding: utf-8 -*-
"""T8（Phase5-3 / M2 任务书 4.3）：用户级设置持久化、密码修改、登录设备管理。

安全断言：
  * 设置按当前登录用户隔离（A 的设置绝不泄漏给 B）；
  * 输入严格校验：未知分区/未知字段/超长取值 422，不静默丢弃；
  * 修改密码必须验证原凭证；改密后**其他**会话立即失效、当前会话保留；
  * 设备下线是真实会话撤销（被撤销 Token 401），非本人会话一律 404（防枚举）；
  * 主题等纯客户端偏好不入库（payload 不含 theme）。
"""
from __future__ import annotations

import unittest

from _util import BusinessHarness  # noqa: E402


class T8UserSettingsAndSessions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = BusinessHarness()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    # ---------------------------------------------------------- 设置持久化
    def test_settings_default_then_persist_and_reload(self):
        h = self.h
        h.register("set_user_1", "SetUser1!2026")
        _, token = h.login("set_user_1", "SetUser1!2026")

        r = h.client.get("/api/v1/students/me/settings", headers=h.auth(token))
        self.assertEqual(r.status_code, 200, r.text)
        settings = r.json()["data"]["settings"]
        self.assertIn("notifications", settings)
        self.assertIn("job_intent", settings)
        self.assertNotIn("theme", settings)  # 主题是纯客户端偏好，不入库

        r = h.client.put("/api/v1/students/me/settings", headers=h.auth(token),
                         json={"settings": {
                             "notifications": {"siteMessage": False, "emailNotice": True,
                                               "matchAlert": False, "weeklyReport": False},
                             "job_intent": {"intentTags": ["数据分析", "杭州"]},
                             "basic": {"nickname": "合成用户一", "graduateYear": "2027"},
                         }})
        self.assertEqual(r.status_code, 200, r.text)
        saved = r.json()["data"]["settings"]
        self.assertFalse(saved["notifications"]["siteMessage"])
        self.assertEqual(saved["job_intent"]["intentTags"], ["数据分析", "杭州"])
        self.assertEqual(saved["basic"]["nickname"], "合成用户一")
        # 未给出的分区保持既有值（分区级合并）
        self.assertTrue(saved["resume_prefs"]["autoParse"])

        # 重新读取确认持久化（新请求 = 新会话级读取）
        r = h.client.get("/api/v1/students/me/settings", headers=h.auth(token))
        again = r.json()["data"]["settings"]
        self.assertEqual(again["job_intent"]["intentTags"], ["数据分析", "杭州"])
        self.assertEqual(again["basic"]["graduateYear"], "2027")

    def test_settings_strict_validation(self):
        h = self.h
        h.register("set_user_2", "SetUser2!2026")
        _, token = h.login("set_user_2", "SetUser2!2026")

        cases = [
            {"settings": {}},                                        # 空对象
            {"settings": {"unknown_section": {"a": 1}}},             # 未知分区
            {"settings": {"notifications": {"siteMessage": "yes"}}}, # 非布尔
            {"settings": {"notifications": {"evilKey": True}}},      # 未知字段
            {"settings": {"basic": {"nickname": "x" * 65}}},         # 超长
            {"settings": {"basic": {"graduateYear": "20x7"}}},       # 非法年份
            {"settings": {"job_intent": {"intentTags": ["x" * 25]}}},  # 标签超长
            {"settings": {"job_intent": {"intentTags": list(range(21))}}},  # 标签超量
        ]
        for body in cases:
            r = h.client.put("/api/v1/students/me/settings", headers=h.auth(token), json=body)
            self.assertEqual(r.status_code, 422, f"{body} 应被拒绝: {r.text}")
            self.assertEqual(r.json()["error"]["code"], "INVALID_REQUEST")

    def test_settings_user_isolation(self):
        h = self.h
        h.register("iso_a", "IsoUserA!2026")
        h.register("iso_b", "IsoUserB!2026")
        _, token_a = h.login("iso_a", "IsoUserA!2026")
        _, token_b = h.login("iso_b", "IsoUserB!2026")

        r = h.client.put("/api/v1/students/me/settings", headers=h.auth(token_a),
                         json={"settings": {"basic": {"nickname": "用户A专属昵称"}}})
        self.assertEqual(r.status_code, 200, r.text)

        r = h.client.get("/api/v1/students/me/settings", headers=h.auth(token_b))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotEqual(r.json()["data"]["settings"]["basic"]["nickname"],
                            "用户A专属昵称")

    # ---------------------------------------------------------- 密码修改
    def test_change_password_verifies_old_and_revokes_other_sessions(self):
        h = self.h
        h.register("pw_user", "PwUser1!2026")
        _, token_keep = h.login("pw_user", "PwUser1!2026")
        _, token_other = h.login("pw_user", "PwUser1!2026")

        # 原密码错误 -> 401，且不影响任何会话
        r = h.client.post("/api/v1/auth/change-password", headers=h.auth(token_keep),
                          json={"old_password": "WrongPass!2026",
                                "new_password": "NewPass1!2026"})
        self.assertEqual(r.status_code, 401, r.text)
        self.assertEqual(r.json()["error"]["code"], "AUTH_INVALID_CREDENTIALS")
        r = h.client.get("/api/v1/auth/me", headers=h.auth(token_other))
        self.assertEqual(r.status_code, 200, r.text)

        # 新密码强度不足 -> 422
        r = h.client.post("/api/v1/auth/change-password", headers=h.auth(token_keep),
                          json={"old_password": "PwUser1!2026", "new_password": "short"})
        self.assertEqual(r.status_code, 422, r.text)

        # 新密码与原密码相同 -> 422
        r = h.client.post("/api/v1/auth/change-password", headers=h.auth(token_keep),
                          json={"old_password": "PwUser1!2026",
                                "new_password": "PwUser1!2026"})
        self.assertEqual(r.status_code, 422, r.text)

        # 正确改密：当前会话保留，其他会话立即失效
        r = h.client.post("/api/v1/auth/change-password", headers=h.auth(token_keep),
                          json={"old_password": "PwUser1!2026",
                                "new_password": "PwUser2!2026"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertGreaterEqual(r.json()["data"]["revoked_sessions"], 1)

        r = h.client.get("/api/v1/auth/me", headers=h.auth(token_keep))
        self.assertEqual(r.status_code, 200, r.text)
        r = h.client.get("/api/v1/auth/me", headers=h.auth(token_other))
        self.assertEqual(r.status_code, 401, r.text)

        # 旧密码失效、新密码可登录
        r = h.client.post("/api/v1/auth/login",
                          json={"username": "pw_user", "password": "PwUser1!2026"})
        self.assertEqual(r.status_code, 401, r.text)
        r = h.client.post("/api/v1/auth/login",
                          json={"username": "pw_user", "password": "PwUser2!2026"})
        self.assertEqual(r.status_code, 200, r.text)

        # 响应不泄漏密码哈希
        self.assertNotIn("password_hash", r.text)

    # ---------------------------------------------------------- 设备管理
    def test_session_list_and_revoke_real_invalidation(self):
        h = self.h
        h.register("dev_user", "DevUser1!2026")
        _, token_keep = h.login("dev_user", "DevUser1!2026")
        _, token_drop = h.login("dev_user", "DevUser1!2026")

        r = h.client.get("/api/v1/auth/sessions", headers=h.auth(token_keep))
        self.assertEqual(r.status_code, 200, r.text)
        items = r.json()["data"]["items"]
        self.assertEqual(len(items), 2)
        current = [i for i in items if i["current"]]
        others = [i for i in items if not i["current"]]
        self.assertEqual(len(current), 1)
        self.assertEqual(len(others), 1)
        drop_id = others[0]["session_id"]

        # 下线其他设备 = 真实会话撤销
        r = h.client.delete(f"/api/v1/auth/sessions/{drop_id}", headers=h.auth(token_keep))
        self.assertEqual(r.status_code, 200, r.text)
        r = h.client.get("/api/v1/auth/me", headers=h.auth(token_drop))
        self.assertEqual(r.status_code, 401, r.text)

        # 重复撤销 / 不存在会话 -> 404（防枚举，不区分）
        r = h.client.delete(f"/api/v1/auth/sessions/{drop_id}", headers=h.auth(token_keep))
        self.assertEqual(r.status_code, 404, r.text)
        r = h.client.delete("/api/v1/auth/sessions/no-such-session",
                            headers=h.auth(token_keep))
        self.assertEqual(r.status_code, 404, r.text)

    def test_session_revoke_others_and_cross_user_404(self):
        h = self.h
        h.register("dev_user_2", "DevUser2!2026")
        h.register("dev_user_3", "DevUser3!2026")
        _, token_keep = h.login("dev_user_2", "DevUser2!2026")
        _, token_drop_1 = h.login("dev_user_2", "DevUser2!2026")
        _, token_drop_2 = h.login("dev_user_2", "DevUser2!2026")
        _, token_other_user = h.login("dev_user_3", "DevUser3!2026")

        r = h.client.get("/api/v1/auth/sessions", headers=h.auth(token_other_user))
        other_session_id = r.json()["data"]["items"][0]["session_id"]

        # 越权撤销他人会话 -> 404（不泄漏存在性）
        r = h.client.delete(f"/api/v1/auth/sessions/{other_session_id}",
                            headers=h.auth(token_keep))
        self.assertEqual(r.status_code, 404, r.text)
        r = h.client.get("/api/v1/auth/me", headers=h.auth(token_other_user))
        self.assertEqual(r.status_code, 200, r.text)

        # 一键下线其他设备：当前保留，其余全部失效
        r = h.client.post("/api/v1/auth/sessions/revoke-others", headers=h.auth(token_keep))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["data"]["revoked_sessions"], 2)
        r = h.client.get("/api/v1/auth/me", headers=h.auth(token_keep))
        self.assertEqual(r.status_code, 200, r.text)
        for t in (token_drop_1, token_drop_2):
            self.assertEqual(h.client.get("/api/v1/auth/me", headers=h.auth(t)).status_code,
                             401)


if __name__ == "__main__":
    unittest.main()
