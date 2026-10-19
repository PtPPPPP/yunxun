"""Current release acceptance against populated, genuinely pre-v10 schemas."""
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.core import database
from backend.app.core.config import get_settings
from backend.app.core.security import hash_password


class CurrentMigrationAcceptanceTestCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "populated-v9.db"
        environment = patch.dict(os.environ, {
            "YUNXUN_DB_PATH": str(self.path), "YUNXUN_ENV": "test",
            "YUNXUN_JWT_SECRET": "acceptance-only-test-key", "YUNXUN_COOKIE_SECURE": "false",
            "YUNXUN_AUTH_REQUESTS_PER_MINUTE": "2000", "YUNXUN_REQUESTS_PER_MINUTE": "600",
        })
        environment.start(); self.addCleanup(environment.stop)
        get_settings.cache_clear(); self.addCleanup(get_settings.cache_clear)
        self.password = "acceptance-old-password"
        self.columns = {}
        # Build the historical layout, rather than relabelling a v12 database as v9.
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("PRAGMA foreign_keys=ON")
            for version in range(1, 10):
                getattr(database, f"_apply_schema_v{version}")(conn)
            conn.execute("PRAGMA user_version=9")
            for owner in ("a", "b"):
                conn.execute("INSERT INTO users(id,username,password_hash,display_name,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (owner, f"guest_historical_{owner}", hash_password(self.password), f"历史农户{owner}", "2025-01-01", "2025-01-01"))
                conn.execute("INSERT INTO auth_tokens VALUES(?,?,?,?)", (f"historical-digest-{owner}", owner, "2030-01-01T00:00:00+00:00", "2025-01-01"))
                conn.execute("INSERT INTO plots VALUES(?,?,?,?,?,?,?,?,?)", (f"p{owner}", owner, f"历史田{owner}", 2, "壤土", "井灌", "保留备注", "2025-01-01", "2025-01-01"))
                conn.execute("INSERT INTO plot_seasons VALUES(?,?,?,?,?,?,?,?,?)",
                    (f"s{owner}", owner, f"p{owner}", "玉米", "2025-10-01", "2026-05-31" if owner == "a" else None, "保留茬次", "2025-10-01", "2025-10-01"))
                conn.execute("INSERT INTO farm_tasks VALUES(?,?,?,?,?,?,?,?)",
                    (f"t{owner}", owner, f"p{owner}", "历史已完成", "2026-04-30", "2026-04-30T00:00:00+00:00", "保留完成状态", "2026-04-01"))
                conn.execute("INSERT INTO tool_records VALUES(?,?,?,?,?,?,?,?)",
                    (f"d{owner}", owner, "decision", "玉米", "{}", "历史本机规则建议", "local", "2026-04-01"))
            conn.execute("INSERT INTO plot_seasons VALUES(?,?,?,?,?,?,?,?,?)",
                ("a-new", "a", "pa", "大豆", "2026-10-01", None, "新茬", "2026-10-01", "2026-10-01"))
            for record_id, owner, happened, kind, cost, quantity, price in (
                ("r-cost", "a", "2026-04-30", "施肥", 80, None, None),
                ("r-income", "a", "2026-05-20", "采收", 0, 100, 3),
                ("r-incomplete", "a", "2026-05-21", "采收", None, 10, None),
                ("r-other", "b", "2026-04-30", "施肥", 999, None, None),
            ):
                conn.execute("""INSERT INTO farm_records(id,user_id,plot_id,kind,happened_on,crop,quantity,cost,detail,
                    created_at,material,safe_days,yield_kg,unit_price,season_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (record_id, owner, f"p{owner}", kind, happened, "玉米", "", cost, "历史台账", "2026-04-01", "", None, quantity, price, f"s{owner}"))
            for table in ("users", "auth_tokens", "plots", "plot_seasons", "farm_records", "farm_tasks", "tool_records"):
                self.columns[table] = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
        self.original = self.snapshot()

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return {table: conn.execute(f"SELECT {','.join(columns)} FROM {table} ORDER BY 1").fetchall()
                for table, columns in self.columns.items()}

    def login(self, app, owner):
        client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(client.close)
        response = client.post("/api/auth/login", json={"username": f"guest_historical_{owner}", "password": self.password})
        self.assertEqual(response.status_code, 200, response.text)
        client.headers["X-CSRF-Token"] = client.cookies["yunxun_csrf"]
        self.assertFalse(response.json()["user"]["is_guest"])
        return client

    def test_v9_to_v12_preserves_all_columns_links_isolation_and_recovery_accounting(self):
        database.init_db()
        self.assertEqual(self.snapshot(), self.original)
        with database.get_connection() as conn:
            self.assertEqual(database.migrate_schema(conn), (12, []))
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertIsNotNone(conn.execute("SELECT 1 FROM sqlite_master WHERE name='idx_plot_seasons_one_active'").fetchone())
            self.assertNotIn("crop", [row[1] for row in conn.execute("PRAGMA table_info(plots)")])
            for table in ("plots", "farm_records"):
                self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE deleted_at IS NOT NULL").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users WHERE is_guest<>0 OR recovery_code_hash IS NOT NULL").fetchone()[0], 0)
        from backend.app.main import create_app
        app = create_app()
        owner, other = self.login(app, "a"), self.login(app, "b")

        def economics(client, season):
            return client.get("/api/farm-records/economics", params={"season_id": season, "year": "2026"}).json()["plots"][0]

        before = economics(owner, "sa")
        self.assertEqual((before["record_count"], before["total_cost"], before["total_revenue"], before["net_revenue"], before["total_yield_kg"]), (3, 80, 300, 220, 110))
        self.assertEqual((before["missing_cost_count"], before["incomplete_harvest_count"]), (1, 1))
        self.assertEqual(economics(other, "sb")["total_cost"], 999)
        first = owner.get("/api/farm-records", params={"limit": 2}).json()
        second = owner.get("/api/farm-records", params={"limit": 2, "cursor": first["pagination"]["next_cursor"]}).json()
        self.assertEqual({row["id"] for row in first["records"] + second["records"]}, {"r-cost", "r-income", "r-incomplete"})
        self.assertEqual(owner.patch("/api/farm-records/r-other", json={"plot_id": "pb", "kind": "施肥", "happened_on": "2026-04-30"}).status_code, 404)
        self.assertEqual(other.post("/api/trash/plots/pa/restore").status_code, 404)
        self.assertEqual(owner.post("/api/auth/upgrade-guest", json={"username": "must_not_upgrade", "password": "new-password", "display_name": "拒绝"}).status_code, 403)
        self.assertEqual(owner.delete("/api/farm-records/r-cost").status_code, 200)
        impact = owner.get("/api/plots/pa/delete-impact").json()["impact"]
        self.assertEqual((impact["season_count"], impact["record_count"], impact["task_count"]), (2, 3, 1))
        self.assertEqual(owner.delete("/api/plots/pa", params={"expected_revision": impact["revision"]}).status_code, 200)
        self.assertEqual(owner.get("/api/farm-records/stats").json()["record_count"], 0)
        self.assertEqual(owner.get("/api/farm-tasks").json()["recent_done"], [])
        self.assertEqual(economics(other, "sb")["total_cost"], 999)
        self.assertEqual(owner.post("/api/trash/plots/pa/restore").status_code, 200)
        self.assertEqual(economics(owner, "sa")["net_revenue"], 300)
        self.assertEqual(owner.post("/api/trash/records/r-cost/restore").status_code, 200)
        self.assertEqual(economics(owner, "sa"), before)
        self.assertEqual(owner.get("/api/farm-tasks").json()["recent_done"][0]["id"], "ta")
        # Authentication added new sessions; every original business column is still exact.
        after = self.snapshot()
        for table in ("users", "plots", "plot_seasons", "farm_records", "farm_tasks", "tool_records"):
            self.assertEqual(after[table], self.original[table])

    def test_v12_ddl_failure_rolls_back_its_whole_step_and_retry_preserves_data(self):
        with closing(sqlite3.connect(self.path)) as conn:
            database._apply_schema_v10(conn)
            conn.execute("ALTER TABLE users ADD COLUMN recovery_code_hash TEXT")
            conn.execute("PRAGMA user_version=11")
            conn.commit()
            def deny_record_alter(action, arg1, arg2, _database, _trigger):
                return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_ALTER_TABLE and arg2 == "farm_records" else sqlite3.SQLITE_OK
            conn.set_authorizer(deny_record_alter)
            with self.assertRaises(sqlite3.DatabaseError):
                database.migrate_schema(conn)
            conn.set_authorizer(None)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 11)
            for table in ("plots", "farm_records"):
                self.assertNotIn("deleted_at", [row[1] for row in conn.execute(f"PRAGMA table_info({table})")])
        self.assertEqual(self.snapshot(), self.original)
        database.init_db()
        self.assertEqual(self.snapshot(), self.original)
        with database.get_connection() as conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 12)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
