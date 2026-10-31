# -*- coding: utf-8 -*-
"""Phase5-3 / M4 PostgreSQL 十项验收检查（真实执行，逐项登记）。

任务书第六节要求验证：
  1. alembic upgrade head          2. 初始 Schema 与约束
  3. 外键与唯一索引                4. JSON/JSONB 行为
  5. 数据库事务回滚                6. 多用户隔离
  7. 并发推荐幂等                  8. 简历文件与数据库记录一致性
  9. 迁移前后数据兼容             10. PostgreSQL 与 SQLite 行为差异

纪律：
  * 只连接 JM_TEST_DATABASE_URL_POSTGRES 指向的**隔离临时测试库**，
    绝不触碰开发/生产业务库；密码只从环境读取，不写入任何文件；
  * 未提供 PG 环境时全部登记 NOT_RUN（退出码 0），绝不冒充 PASS；
  * 任一项真实执行失败 -> 状态 FAIL，进程退出码 1；
  * 输出带运行身份（run_id / commit / 时间戳）的 JSON 登记表。

用法：
  set JM_TEST_DATABASE_URL_POSTGRES=postgresql+psycopg2://user:pass@host:port/db
  python scripts/phase5_3/pg_acceptance_checks.py --out reports/phase5-3/pg-acceptance.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
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


def _require_pg(reg: Registry) -> str | None:
    url = (os.environ.get("JM_TEST_DATABASE_URL_POSTGRES") or "").strip()
    if not url:
        for i in range(1, 11):
            reg.add(f"PG{i:02d}", "-", "NOT_RUN",
                    "未提供 JM_TEST_DATABASE_URL_POSTGRES（隔离测试库），SQLite 通过不代表 PG 兼容")
        return None
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        for i in range(1, 11):
            reg.add(f"PG{i:02d}", "-", "ENV_INCOMPATIBLE", "缺少 psycopg2，无法连接 PostgreSQL")
        return None
    return url


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "reports/phase5-3/pg-acceptance.json"))
    args = ap.parse_args()

    reg = Registry()
    t0 = time.time()
    url = _require_pg(reg)
    if url:
        _run_all(reg, url)

    payload = {
        "run_id": _run_id(),
        "commit": _commit(),
        "generated_by": "scripts/phase5_3/pg_acceptance_checks.py",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seconds": round(time.time() - t0, 2),
        "database": "isolated test PostgreSQL (credentials not recorded)",
        "totals": {
            s: sum(1 for it in reg.items if it["status"] == s) for s in STATUSES
        },
        "items": reg.items,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"== PG 验收登记 {payload['totals']} -> {out}")
    return 1 if payload["totals"]["FAIL"] else 0


def _run_all(reg: Registry, url: str) -> None:
    from _util import run_downgrade, run_migrations  # noqa: E402
    from sqlalchemy import create_engine, inspect, select, text
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import sessionmaker

    from job_matching.infra.persistence import (Job, RecommendationRun, Resume,
                                                StudentProfile, User)
    from job_matching.service.accounts import hash_password

    # ---- PG01 alembic upgrade head ----
    try:
        run_migrations(url)
        eng = create_engine(url, future=True)
        insp = inspect(eng)
        tables = set(insp.get_table_names())
        eng.dispose()
        missing = [t for t in ("users", "student_profiles", "resumes", "jobs",
                               "recommendation_runs", "recommendation_items") if t not in tables]
        if missing:
            reg.add("PG01", "alembic upgrade head", "FAIL", f"迁移后缺表 {missing}")
            return
        reg.add("PG01", "alembic upgrade head", "PASS", f"head 迁移完成，{len(tables)} 张业务表")
    except Exception as e:  # noqa: BLE001
        reg.add("PG01", "alembic upgrade head", "FAIL", f"{type(e).__name__}: {e}")
        return

    # ---- PG02 Schema 与约束（唯一 / 外键，pg_catalog 实查）----
    try:
        eng = create_engine(url, future=True)
        with eng.connect() as conn:
            uniq = conn.execute(text(
                "SELECT conname FROM pg_constraint WHERE contype='u'")).scalars().all()
            fkeys = conn.execute(text(
                "SELECT conname FROM pg_constraint WHERE contype='f'")).scalars().all()
        eng.dispose()
        need_u = ("uq_reco_runs_user_fingerprint",)
        miss_u = [c for c in need_u if c not in uniq]
        if miss_u or not fkeys:
            reg.add("PG02", "初始 Schema 与约束", "FAIL",
                    f"缺唯一约束 {miss_u}；外键数 {len(fkeys)}")
        else:
            reg.add("PG02", "初始 Schema 与约束", "PASS",
                    f"唯一约束 {len(uniq)} 个（含 {need_u[0]}）、外键 {len(fkeys)} 个")
    except Exception as e:  # noqa: BLE001
        reg.add("PG02", "初始 Schema 与约束", "FAIL", f"{type(e).__name__}: {e}")

    # ---- PG03 外键强制 ----
    fac = None
    try:
        eng = create_engine(url, future=True)
        fac = sessionmaker(bind=eng, future=True)
        s = fac()
        try:
            s.add(StudentProfile(user_id=999999, profile_version=1, profile_data={}))
            try:
                s.flush()
                reg.add("PG03", "外键与唯一索引", "FAIL", "孤儿行未被外键拦截")
            except IntegrityError:
                s.rollback()
                reg.add("PG03", "外键与唯一索引", "PASS", "孤儿 student_profiles 被外键拒绝；唯一索引见 PG02")
        finally:
            s.close()
    except Exception as e:  # noqa: BLE001
        reg.add("PG03", "外键与唯一索引", "FAIL", f"{type(e).__name__}: {e}")

    # ---- PG04 JSON/JSONB ----
    try:
        s = fac()
        try:
            u = User(username=f"pg_acc_{os.getpid()}", password_hash=hash_password("Pg!2026pass"),
                     role="student", status="active")
            s.add(u)
            s.flush()
            s.add(StudentProfile(user_id=u.id, profile_version=1, confirmed=1,
                                 profile_data={"profile": {"major": {"value": "软件工程"}}}))
            s.commit()
            hit = s.execute(text(
                "SELECT id FROM student_profiles "
                "WHERE profile_data->'profile'->'major'->>'value' = :v"), {"v": "软件工程"}).fetchall()
            s2 = s.execute(select(StudentProfile).where(
                StudentProfile.profile_data["profile"]["major"]["value"].as_string() == "软件工程"
            )).scalars().first()
            ok = len(hit) == 1 and s2 is not None
            reg.add("PG04", "JSON/JSONB 行为", "PASS" if ok else "FAIL",
                    f"原生 ->> 路径查询命中 {len(hit)} 行；ORM as_string() 命中 {s2 is not None}")
        finally:
            s.close()
    except Exception as e:  # noqa: BLE001
        reg.add("PG04", "JSON/JSONB 行为", "FAIL", f"{type(e).__name__}: {e}")

    # ---- PG05 事务回滚 ----
    try:
        s = fac()
        try:
            u = s.execute(select(User).where(User.username == f"pg_acc_{os.getpid()}")).scalars().first()
            before = s.query(StudentProfile).count()
            try:
                s.add(StudentProfile(user_id=u.id, profile_version=77, profile_data={}))
                s.flush()
                raise RuntimeError("模拟失败事务")
            except RuntimeError:
                s.rollback()
            after = s.query(StudentProfile).count()
            reg.add("PG05", "数据库事务回滚", "PASS" if after == before else "FAIL",
                    f"回滚前后行数 {before} -> {after}（应相等）")
        finally:
            s.close()
    except Exception as e:  # noqa: BLE001
        reg.add("PG05", "数据库事务回滚", "FAIL", f"{type(e).__name__}: {e}")

    # ---- PG06 多用户隔离 ----
    try:
        s = fac()
        try:
            ub = User(username=f"pg_acc_b_{os.getpid()}", password_hash=hash_password("Pg!2026pass"),
                      role="student", status="active")
            s.add(ub)
            s.flush()
            s.add(StudentProfile(user_id=ub.id, profile_version=1,
                                 profile_data={"profile": {"major": {"value": "隔离探针"}}}))
            s.commit()
            ua = s.execute(select(User).where(User.username == f"pg_acc_{os.getpid()}")).scalars().first()
            a_rows = s.execute(select(StudentProfile).where(
                StudentProfile.user_id == ua.id)).scalars().all()
            b_rows = s.execute(select(StudentProfile).where(
                StudentProfile.user_id == ub.id)).scalars().all()
            cross = [r for r in a_rows if r.profile_data.get("profile", {}).get("major", {}).get("value") == "隔离探针"]
            ok = (not cross) and len(b_rows) == 1
            reg.add("PG06", "多用户隔离", "PASS" if ok else "FAIL",
                    f"用户A 命中 {len(a_rows)} 行、用户B 命中 {len(b_rows)} 行、跨用户泄漏 {len(cross)} 行")
        finally:
            s.close()
    except Exception as e:  # noqa: BLE001
        reg.add("PG06", "多用户隔离", "FAIL", f"{type(e).__name__}: {e}")

    # ---- PG07 并发推荐幂等（唯一约束只放行一条）----
    try:
        errors: list = []
        ok_count = [0]
        barrier = threading.Barrier(4)

        def _insert() -> None:
            ss = fac()
            try:
                barrier.wait(timeout=30)
                uu = ss.execute(select(User).where(
                    User.username == f"pg_acc_{os.getpid()}")).scalars().first()
                ss.add(RecommendationRun(
                    user_id=uu.id, profile_version=1,
                    scoring_method="baseline_skill_text_v1",
                    scoring_config_version="scoring_config_v1",
                    job_set_snapshot=[],
                    request_fingerprint="a" * 64, request_semantic_hash="b" * 64,
                    status="completed"))
                ss.commit()
                ok_count[0] += 1
            except IntegrityError:
                errors.append(1)
                ss.rollback()
            finally:
                ss.close()

        ts = [threading.Thread(target=_insert) for _ in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=60)
        ok = ok_count[0] == 1 and len(errors) == 3
        reg.add("PG07", "并发推荐幂等", "PASS" if ok else "FAIL",
                f"4 并发相同指纹：落库 {ok_count[0]} 条、被唯一约束拦截 {len(errors)} 条（期望 1/3）")
    except Exception as e:  # noqa: BLE001
        reg.add("PG07", "并发推荐幂等", "FAIL", f"{type(e).__name__}: {e}")

    # ---- PG08 简历文件与数据库记录一致性 ----
    try:
        import hashlib
        with tempfile.TemporaryDirectory(prefix="jm_pg_acc_") as td:
            tdp = Path(td)
            f1 = tdp / "resume_a.txt"
            f1.write_text("synthetic resume A", encoding="utf-8")
            sha1 = hashlib.sha256(f1.read_bytes()).hexdigest()
            s = fac()
            try:
                u = s.execute(select(User).where(User.username == f"pg_acc_{os.getpid()}")).scalars().first()
                s.add(Resume(user_id=u.id, original_filename="resume_a.txt",
                             storage_key=f"resumes/{u.id}/resume_a.txt",
                             file_sha256=sha1, file_size=f1.stat().st_size,
                             parse_status="ok", data_source="synthetic", source_audit=[]))
                s.commit()
                # 同 sha256 重复登记必须被唯一约束拒绝
                s.add(Resume(user_id=u.id, original_filename="resume_a_dup.txt",
                             storage_key=f"resumes/{u.id}/dup.txt",
                             file_sha256=sha1, file_size=1,
                             parse_status="ok", data_source="synthetic", source_audit=[]))
                dup_blocked = False
                try:
                    s.flush()
                except IntegrityError:
                    dup_blocked = True
                    s.rollback()
                # 记录-文件一致性扫描：行的 storage_key 语义与 sha256 可核对
                rows = s.execute(select(Resume).where(Resume.user_id == u.id)).scalars().all()
                rec_ok = len(rows) == 1 and rows[0].file_sha256 == sha1
                ok = dup_blocked and rec_ok
                reg.add("PG08", "简历文件与数据库记录一致性", "PASS" if ok else "FAIL",
                        f"重复 sha256 拦截={dup_blocked}；登记行 {len(rows)} 条且 sha256 一致={rec_ok}")
            finally:
                s.close()
    except Exception as e:  # noqa: BLE001
        reg.add("PG08", "简历文件与数据库记录一致性", "FAIL", f"{type(e).__name__}: {e}")

    # ---- PG09 迁移前后数据兼容（旧版本号下播种 -> 升级 head 数据保留）----
    try:
        run_downgrade(url, "99510af3982b")
        eng = create_engine(url, future=True)
        fac_old = sessionmaker(bind=eng, future=True)
        s = fac_old()
        try:
            u = User(username=f"pg_compat_{os.getpid()}", password_hash=hash_password("Pg!2026pass"),
                     role="student", status="active")
            s.add(u)
            s.flush()
            s.add(StudentProfile(user_id=u.id, profile_version=1,
                                 profile_data={"profile": {"major": {"value": "旧版迁移"}}}))
            s.commit()
        finally:
            s.close()
            eng.dispose()
        run_migrations(url)   # b7d21c4a5f13 -> c3a1f5d27e44 全链升级
        eng = create_engine(url, future=True)
        fac_new = sessionmaker(bind=eng, future=True)
        s = fac_new()
        try:
            kept = s.execute(select(StudentProfile).where(
                StudentProfile.profile_data["profile"]["major"]["value"].as_string() == "旧版迁移"
            )).scalars().first()
            reg.add("PG09", "迁移前后数据兼容", "PASS" if kept is not None else "FAIL",
                    f"99510af3982b 播种数据经 b7d21c4a5f13/c3a1f5d27e44 升级后保留={kept is not None}")
        finally:
            s.close()
            eng.dispose()
    except Exception as e:  # noqa: BLE001
        reg.add("PG09", "迁移前后数据兼容", "FAIL", f"{type(e).__name__}: {e}")

    # ---- PG10 PostgreSQL 与 SQLite 行为差异（双库语义探针）----
    try:
        import sqlite3
        with tempfile.TemporaryDirectory(prefix="jm_pg_diff_") as td:
            sdb = Path(td) / "probe.db"
            con = sqlite3.connect(str(sdb))
            try:
                con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, doc JSON)")
                con.execute("INSERT INTO t (doc) VALUES ('{\"profile\":{\"major\":{\"value\":\"软件工程\"}}}')")
                row = con.execute(
                    "SELECT id FROM t WHERE json_extract(doc,'$.profile.major.value') = ?",
                    ("软件工程",)).fetchone()
                sqlite_json_ok = row is not None
            finally:
                con.close()
        eng = create_engine(url, future=True)
        with eng.connect() as conn:
            conn.execute(text("CREATE TEMP TABLE tp (id SERIAL PRIMARY KEY, doc JSONB)"))
            conn.execute(text("INSERT INTO tp (doc) VALUES (:d)"),
                         {"d": json.dumps({"profile": {"major": {"value": "软件工程"}}})})
            pg_row = conn.execute(text(
                "SELECT id FROM tp WHERE doc->'profile'->'major'->>'value' = :v"),
                {"v": "软件工程"}).fetchone()
            coltype = conn.execute(text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='student_profiles' AND column_name='profile_data'")).scalar()
        eng.dispose()
        ok = sqlite_json_ok and pg_row is not None
        reg.add("PG10", "PostgreSQL 与 SQLite 行为差异", "PASS" if ok else "FAIL",
                f"JSON 路径查询 SQLite(json_extract)={sqlite_json_ok} "
                f"PG(->>){pg_row is not None}；PG profile_data 类型={coltype}（SQLite 侧为 JSON 文本+json_extract）")
    except Exception as e:  # noqa: BLE001
        reg.add("PG10", "PostgreSQL 与 SQLite 行为差异", "FAIL", f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    sys.exit(main())
