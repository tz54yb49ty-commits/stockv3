import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from ashare_v3.web.n6_user_app import N6UserWebConfig, create_app
from tests.test_n6_user_app import FakeN6UserRepository, FixedPasswordHasher, FixedPasswordVerifier


def build_archive_status_client(
    *,
    docs_root: str,
    archive_root: str,
) -> tuple[TestClient, FakeN6UserRepository]:
    repo = FakeN6UserRepository()
    app = create_app(
        repository=repo,
        config=N6UserWebConfig(
            cookie_secure=False,
            session_ttl_seconds=3600,
            runtime_archive_docs_root=docs_root,
            runtime_archive_root=archive_root,
        ),
        password_verifier=FixedPasswordVerifier(True),
        password_hasher=FixedPasswordHasher(),
    )
    return TestClient(app, follow_redirects=False), repo


def write_archive_status_fixture(docs_root: Path, *, trade_date: str = "20260612") -> None:
    run_dir = docs_root / trade_date
    run_dir.mkdir(parents=True, exist_ok=True)
    (docs_root / "latest").symlink_to(trade_date)
    (run_dir / "archive_status.json").write_text(
        json.dumps(
            {
                "result": "ARCHIVE_PREFLIGHT_PASS",
                "trade_date": trade_date,
                "archive_root": "/Volumes/MacRaid/stock_db_archive/v3_runtime",
                "hot_retention_days": 5,
                "storage": {"mounted": True, "writable": True, "free_bytes": 987654321},
                "plan": {
                    "status": "ARCHIVE_PREFLIGHT_PASS",
                    "files": [
                        {
                            "layer": "n3",
                            "table": "stock_minute_bar_1m",
                            "row_count": 705120,
                            "path": "/Volumes/MacRaid/stock_db_archive/v3_runtime/trade_date=20260612/n3/stock_minute_bar_1m.parquet",
                        }
                    ],
                    "manifest_path": "/Volumes/MacRaid/stock_db_archive/v3_runtime/trade_date=20260612/manifests/archive_manifest.json",
                    "blockers": [],
                    "cleanup_eligible": False,
                    "cleanup_blockers": ["manual_cleanup_required"],
                },
                "side_effects": {
                    "writes_database": False,
                    "writes_archive_files": False,
                    "cleanup_local_runtime": False,
                    "voice_triggered": False,
                    "mobile_triggered": False,
                    "sim_written": False,
                    "real_trade_submitted": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def write_archive_status_storage_blocked_fixture(docs_root: Path, *, trade_date: str = "20260612") -> None:
    run_dir = docs_root / trade_date
    run_dir.mkdir(parents=True, exist_ok=True)
    (docs_root / "latest").symlink_to(trade_date)
    (run_dir / "archive_status.json").write_text(
        json.dumps(
            {
                "result": "BLOCKED",
                "trade_date": trade_date,
                "archive_root": "/Volumes/MacRaid/stock_db_archive/v3_runtime",
                "hot_retention_days": 5,
                "storage": {
                    "mounted": False,
                    "writable": False,
                    "free_bytes": 0,
                    "free_space_ok": False,
                },
                "plan": {
                    "status": "BLOCKED",
                    "files": [],
                    "blockers": ["macraid_not_mounted"],
                    "cleanup_eligible": False,
                    "cleanup_blockers": ["archive_preflight_not_passed", "manual_cleanup_required"],
                },
                "side_effects": {
                    "writes_database": False,
                    "writes_archive_files": False,
                    "cleanup_local_runtime": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def write_archive_status_without_plan_fixture(docs_root: Path, *, trade_date: str = "20260612") -> None:
    run_dir = docs_root / trade_date
    run_dir.mkdir(parents=True, exist_ok=True)
    (docs_root / "latest").symlink_to(trade_date)
    (run_dir / "archive_status.json").write_text(
        json.dumps(
            {
                "result": "EXECUTE_PASS",
                "trade_date": trade_date,
                "archive_root": "/Volumes/MacRaid/stock_db_archive/v3_runtime",
                "hot_retention_days": 5,
                "archive_result": "ARCHIVED_VERIFIED",
                "manifest_path": "/Volumes/MacRaid/stock_db_archive/v3_runtime/trade_date=20260612/manifests/archive_manifest.json",
                "side_effects": {
                    "writes_database": False,
                    "writes_archive_files": True,
                    "cleanup_local_runtime": False,
                    "voice_triggered": False,
                    "mobile_triggered": False,
                    "sim_written": False,
                    "real_trade_submitted": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def write_archive_status_after_cleanup_fixture(docs_root: Path, *, trade_date: str = "20260612") -> None:
    run_dir = docs_root / trade_date
    run_dir.mkdir(parents=True, exist_ok=True)
    (docs_root / "latest").symlink_to(trade_date)
    (run_dir / "archive_status.json").write_text(
        json.dumps(
            {
                "result": "ARCHIVED_VERIFIED",
                "trade_date": trade_date,
                "archive_result": "ARCHIVED_VERIFIED",
                "cleanup_executed": True,
                "local_cleanup_state": "LOCAL_CLEANED_METADATA_RETAINED",
                "cleanup_blockers": [],
                "post_cleanup": {
                    "live_total_archived_scope_rows": 2748,
                    "nonzero_tables": [
                        {"layer": "n3", "table": "common_market_data_subscription", "rows": 2676},
                        {"layer": "n3", "table": "common_market_data_run", "rows": 63},
                        {"layer": "n3", "table": "common_market_data_pull_plan", "rows": 9},
                    ],
                },
                "retained_metadata": {
                    "reason": "avoid_high_fanout_fk_set_null_and_preserve_lineage_audit",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def write_dirty_hot_cleanup_status_fixture(docs_root: Path) -> None:
    cleanup_dir = docs_root / "dirty_hot_cleanup"
    cleanup_dir.mkdir(parents=True, exist_ok=True)
    (cleanup_dir / "keep2_cleanup_status.json").write_text(
        json.dumps(
            {
                "result": "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS",
                "retention_trade_days": 2,
                "retained_trade_dates": ["20260701", "20260702"],
                "cleanup_trade_dates": ["20260612", "20260615"],
                "cleanup_executed": True,
                "deleted_total_rows": 12345,
                "side_effects": {
                    "writes_database": True,
                    "cleanup_local_runtime": False,
                    "cleanup_local_runtime_files": False,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def write_keep5_hot_cleanup_status_fixture(docs_root: Path) -> None:
    cleanup_dir = docs_root / "hot_keep5_cleanup"
    cleanup_dir.mkdir(parents=True, exist_ok=True)
    (cleanup_dir / "keep5_cleanup_status.json").write_text(
        json.dumps(
            {
                "result": "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS",
                "cleanup_success": True,
                "direct_delete_no_archive": True,
                "row_count_plan_skipped": True,
                "cleanup_executed": True,
                "cleanup_complete": True,
                "retention_trade_days": 5,
                "retained_trade_dates": ["20260630", "20260701", "20260702", "20260703", "20260706"],
                "cleanup_trade_dates": ["20260525", "20260526"],
                "deleted_total_rows": 6106464,
                "deleted_table_summary": [
                    {"layer": "n3", "table": "stock_minute_bar_1m", "trade_date_count": 2, "deleted_rows": 429120},
                    {"layer": "n4", "table": "common_trigger_state", "trade_date_count": 2, "deleted_rows": 750119},
                ],
                "deleted_rows": [
                    {"trade_date": "20260525", "layer": "n3", "table": "stock_minute_bar_1m", "deleted_rows": 100},
                ],
                "local_file_cleanup": {
                    "result": "LOCAL_FILE_KEEP5_EXECUTE_PASS",
                    "mode": "execute",
                    "started_at": "2026-07-16T01:00:04+08:00",
                    "finished_at": "2026-07-16T01:03:04+08:00",
                    "duration_ms": 180000,
                    "retention_trade_days": 5,
                    "retained_trade_dates": ["20260710", "20260713", "20260714", "20260715", "20260716"],
                    "cleanup_trade_dates": ["20260708", "20260709"],
                    "deleted_file_count": 97209,
                    "deleted_directory_count": 28,
                    "released_bytes": 33468592000,
                    "per_layer": {
                        "n3": {"deleted_file_count": 97170, "deleted_directory_count": 20, "released_bytes": 33460000000},
                        "n4": {"deleted_file_count": 20, "deleted_directory_count": 0, "released_bytes": 592000},
                        "n5": {"deleted_file_count": 19, "deleted_directory_count": 8, "released_bytes": 8000000},
                    },
                    "errors": [],
                    "blockers": [],
                },
                "blockers": [],
                "side_effects": {
                    "writes_database": True,
                    "writes_archive_files": False,
                    "cleanup_local_runtime": False,
                    "cleanup_local_runtime_files": True,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def write_archive_manifest_fixture(archive_root: Path, *, trade_date: str = "20260612") -> Path:
    manifest_path = archive_root / f"trade_date={trade_date}" / "manifests" / "archive_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "result": "ARCHIVED_VERIFIED",
                "trade_date": trade_date,
                "archive_root": str(archive_root),
                "manifest_path": str(manifest_path),
                "report_path": str(archive_root / f"trade_date={trade_date}" / "reports" / "archive_report.json"),
                "file_count": 2,
                "total_rows": 3,
                "row_count_match": True,
                "checksum_algorithm": "sha256",
                "cleanup_eligible": False,
                "cleanup_blockers": ["manual_cleanup_required"],
                "cleanup_executed": False,
                "files": [
                    {
                        "layer": "n3",
                        "table": "stock_minute_bar_1m",
                        "row_count": 2,
                        "verified_row_count": 2,
                        "path": str(archive_root / f"trade_date={trade_date}" / "n3" / "stock_minute_bar_1m.parquet"),
                        "checksum": "sha256:" + "1" * 64,
                    },
                    {
                        "layer": "n4",
                        "table": "common_trigger_match",
                        "row_count": 1,
                        "verified_row_count": 1,
                        "path": str(archive_root / f"trade_date={trade_date}" / "n4" / "common_trigger_match.parquet"),
                        "checksum": "sha256:" + "2" * 64,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return manifest_path


class N6ArchiveStatusPageTest(unittest.TestCase):
    def test_archive_status_reads_combined_local_file_cleanup_without_controls_or_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "runtime_archive"
            archive_root = Path(tmp) / "MacRaid/stock_db_archive/v3_runtime"
            archive_root.mkdir(parents=True)
            write_archive_status_fixture(docs_root)
            write_keep5_hot_cleanup_status_fixture(docs_root)
            status_path = docs_root / "hot_keep5_cleanup/keep5_cleanup_status.json"
            client, repo = build_archive_status_client(docs_root=str(docs_root), archive_root=str(archive_root))
            client.post("/api/n6/auth/login", json={"login_name": "admin", "password": "correct-password"})

            api_response = client.get("/api/n6/ui/v1/archive-status")
            page_response = client.get("/n6/archive-status")

        payload = api_response.json()["local_file_cleanup"]
        self.assertEqual(payload["result"], "LOCAL_FILE_KEEP5_EXECUTE_PASS")
        self.assertEqual(payload["retained_trade_dates"], ["20260710", "20260713", "20260714", "20260715", "20260716"])
        self.assertEqual(payload["cleanup_trade_dates"], ["20260708", "20260709"])
        self.assertEqual(payload["deleted_file_count"], 97209)
        self.assertEqual(payload["deleted_directory_count"], 28)
        self.assertEqual(payload["released_bytes"], 33468592000)
        self.assertEqual(payload["per_layer"]["n3"]["released_bytes"], 33460000000)
        self.assertEqual(payload["status_path"], str(status_path))
        self.assertIn("N3/N4/N5 Local File Cleanup", page_response.text)
        self.assertIn("33468592000", page_response.text)
        self.assertIn("20260708, 20260709", page_response.text)
        self.assertIn("duration_ms", page_response.text)
        self.assertNotIn("--execute", page_response.text)
        self.assertNotIn("launchctl", page_response.text)
        self.assertNotIn("<form", page_response.text.lower())
        self.assertEqual(repo.forbidden_writes["n5_outbox"], 0)
        self.assertEqual(repo.forbidden_writes["user_notification_queue"], 0)

    def test_archive_status_api_reads_artifact_without_database_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "runtime_archive"
            archive_root = Path(tmp) / "MacRaid" / "stock_db_archive" / "v3_runtime"
            archive_root.mkdir(parents=True)
            write_archive_status_fixture(docs_root)
            client, repo = build_archive_status_client(
                docs_root=str(docs_root),
                archive_root=str(archive_root),
            )
            client.post("/api/n6/auth/login", json={"login_name": "admin", "password": "correct-password"})

            response = client.get("/api/n6/ui/v1/archive-status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["component"], "Runtime Hot Cleanup Status")
        self.assertEqual(payload["result"], "ARCHIVE_PREFLIGHT_PASS")
        self.assertEqual(payload["selected_trade_date"], "20260612")
        self.assertTrue(payload["storage"]["mounted"])
        self.assertEqual(payload["plan"]["file_count"], 1)
        self.assertEqual(payload["plan"]["total_rows"], 705120)
        self.assertFalse(payload["plan"]["cleanup_eligible"])
        self.assertIn("manual_cleanup_required", payload["plan"]["cleanup_blockers"])
        self.assertFalse(payload["side_effects"]["writes_database"])
        self.assertFalse(payload["side_effects"]["writes_archive_files"])
        self.assertFalse(payload["side_effects"]["cleanup_local_runtime"])
        self.assertEqual(repo.forbidden_writes["n5_outbox"], 0)
        self.assertEqual(repo.forbidden_writes["user_notification_queue"], 0)

    def test_archive_status_page_is_read_only_hot_cleanup_status_without_execute_controls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "runtime_archive"
            archive_root = Path(tmp) / "MacRaid" / "stock_db_archive" / "v3_runtime"
            archive_root.mkdir(parents=True)
            write_archive_status_fixture(docs_root)
            write_keep5_hot_cleanup_status_fixture(docs_root)
            client, repo = build_archive_status_client(
                docs_root=str(docs_root),
                archive_root=str(archive_root),
            )
            client.post("/api/n6/auth/login", json={"login_name": "admin", "password": "correct-password"})

            response = client.get("/n6/archive-status")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Runtime Hot Cleanup Status", response.text)
        self.assertIn("DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS", response.text)
        self.assertIn("stock_minute_bar_1m", response.text)
        self.assertIn("common_trigger_state", response.text)
        self.assertIn("6106464", response.text)
        self.assertIn("20260630, 20260701, 20260702, 20260703, 20260706", response.text)
        self.assertIn("stock_minute_bar_1m", response.text)
        self.assertIn("archive_manifest.json", response.text)
        self.assertIn("READ ONLY", response.text)
        self.assertIn("不执行归档", response.text)
        self.assertIn("不执行清理", response.text)
        self.assertNotIn("--execute", response.text)
        self.assertNotIn("<form", response.text.lower())
        self.assertNotIn("一键归档预检", response.text)
        self.assertNotIn("确认归档并登记 job", response.text)
        self.assertNotIn("ARCHIVE_KEEP_5", response.text)
        self.assertNotIn("RUNTIME_HOT_KEEP5_DIRECT_DELETE_NO_ARCHIVE_CONFIRMED", response.text)
        self.assertNotIn("/api/n6/ui/v1/archive-execute", response.text)
        self.assertEqual(repo.forbidden_writes["n5_outbox"], 0)

    def test_archive_status_api_prefers_verified_manifest_when_status_has_no_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "runtime_archive"
            archive_root = Path(tmp) / "MacRaid" / "stock_db_archive" / "v3_runtime"
            write_archive_status_without_plan_fixture(docs_root)
            manifest_path = write_archive_manifest_fixture(archive_root)
            client, repo = build_archive_status_client(
                docs_root=str(docs_root),
                archive_root=str(archive_root),
            )
            client.post("/api/n6/auth/login", json={"login_name": "admin", "password": "correct-password"})

            response = client.get("/api/n6/ui/v1/archive-status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["archive_state"], "ARCHIVED_VERIFIED")
        self.assertEqual(payload["archive_execute_result"], "EXECUTE_PASS")
        self.assertEqual(payload["result"], "ARCHIVED_VERIFIED")
        self.assertEqual(payload["plan"]["file_count"], 2)
        self.assertEqual(payload["plan"]["total_rows"], 3)
        self.assertTrue(payload["plan"]["row_count_match"])
        self.assertEqual(payload["plan"]["manifest_path"], str(manifest_path))
        self.assertEqual(payload["plan"]["cleanup_blockers"], ["manual_cleanup_required"])
        self.assertFalse(payload["side_effects"]["writes_database"])
        self.assertFalse(payload["side_effects"]["writes_archive_files"])
        self.assertFalse(payload["side_effects"]["cleanup_local_runtime"])
        self.assertEqual(repo.forbidden_writes["n5_outbox"], 0)

    def test_archive_status_page_renders_verified_manifest_and_safe_archive_controls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "runtime_archive"
            archive_root = Path(tmp) / "MacRaid" / "stock_db_archive" / "v3_runtime"
            write_archive_status_without_plan_fixture(docs_root)
            manifest_path = write_archive_manifest_fixture(archive_root)
            client, repo = build_archive_status_client(
                docs_root=str(docs_root),
                archive_root=str(archive_root),
            )
            client.post("/api/n6/auth/login", json={"login_name": "admin", "password": "correct-password"})

            response = client.get("/n6/archive-status")

        self.assertEqual(response.status_code, 200)
        self.assertIn("ARCHIVED_VERIFIED", response.text)
        self.assertIn("EXECUTE_PASS", response.text)
        self.assertIn("row_count_match", response.text)
        self.assertIn("files 2", response.text)
        self.assertIn("rows 3", response.text)
        self.assertIn(str(manifest_path), response.text)
        self.assertIn("stock_minute_bar_1m", response.text)
        self.assertIn("common_trigger_match", response.text)
        self.assertIn("manual_cleanup_required", response.text)
        self.assertNotIn("No archive files planned", response.text)
        self.assertNotIn("--execute", response.text)
        self.assertNotIn("<form", response.text.lower())
        self.assertIn("Runtime Hot Cleanup Status", response.text)
        self.assertNotIn("一键归档预检", response.text)
        self.assertNotIn("ARCHIVE_KEEP_5", response.text)
        self.assertNotIn("/api/n6/ui/v1/archive-execute", response.text)

    def test_archive_status_page_has_no_execute_button_when_storage_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "runtime_archive"
            archive_root = Path(tmp) / "MacRaid" / "stock_db_archive" / "v3_runtime"
            write_archive_status_storage_blocked_fixture(docs_root)
            client, repo = build_archive_status_client(
                docs_root=str(docs_root),
                archive_root=str(archive_root),
            )
            client.post("/api/n6/auth/login", json={"login_name": "admin", "password": "correct-password"})

            response = client.get("/n6/archive-status")

        self.assertEqual(response.status_code, 200)
        self.assertIn("macraid_not_mounted", response.text)
        self.assertNotIn('id="archive-execute-button"', response.text)
        self.assertNotIn("ARCHIVE_KEEP_5", response.text)
        self.assertEqual(repo.forbidden_writes["n5_outbox"], 0)

    def test_archive_status_page_renders_local_cleanup_closeout_from_status_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "runtime_archive"
            archive_root = Path(tmp) / "MacRaid" / "stock_db_archive" / "v3_runtime"
            write_archive_status_after_cleanup_fixture(docs_root)
            write_archive_manifest_fixture(archive_root)
            client, repo = build_archive_status_client(
                docs_root=str(docs_root),
                archive_root=str(archive_root),
            )
            client.post("/api/n6/auth/login", json={"login_name": "admin", "password": "correct-password"})

            api_response = client.get("/api/n6/ui/v1/archive-status")
            page_response = client.get("/n6/archive-status")

        self.assertEqual(api_response.status_code, 200)
        payload = api_response.json()
        self.assertTrue(payload["cleanup_executed"])
        self.assertEqual(payload["local_cleanup_state"], "LOCAL_CLEANED_METADATA_RETAINED")
        self.assertEqual(payload["plan"]["cleanup_blockers"], [])
        self.assertEqual(payload["post_cleanup"]["live_total_archived_scope_rows"], 2748)
        self.assertEqual(page_response.status_code, 200)
        self.assertIn("LOCAL_CLEANED_METADATA_RETAINED", page_response.text)
        self.assertIn("common_market_data_subscription", page_response.text)
        self.assertNotIn("manual_cleanup_required", page_response.text)
        self.assertNotIn("一键归档预检", page_response.text)
        self.assertEqual(repo.forbidden_writes["n5_outbox"], 0)
        self.assertEqual(repo.forbidden_writes["n5_outbox"], 0)

    def test_archive_status_api_prefers_keep5_hot_cleanup_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            docs_root = Path(tmp) / "runtime_archive"
            archive_root = Path(tmp) / "MacRaid" / "stock_db_archive" / "v3_runtime"
            write_archive_status_fixture(docs_root)
            write_dirty_hot_cleanup_status_fixture(docs_root)
            write_keep5_hot_cleanup_status_fixture(docs_root)
            client, repo = build_archive_status_client(
                docs_root=str(docs_root),
                archive_root=str(archive_root),
            )
            client.post("/api/n6/auth/login", json={"login_name": "admin", "password": "correct-password"})

            api_response = client.get("/api/n6/ui/v1/archive-status")
            page_response = client.get("/n6/archive-status")

        self.assertEqual(api_response.status_code, 200)
        payload = api_response.json()
        self.assertEqual(payload["hot_cleanup"]["result"], "DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS")
        self.assertEqual(payload["hot_cleanup"]["retained_trade_dates"], ["20260630", "20260701", "20260702", "20260703", "20260706"])
        self.assertEqual(payload["hot_cleanup"]["cleanup_trade_dates"], ["20260525", "20260526"])
        self.assertEqual(payload["hot_cleanup"]["deleted_total_rows"], 6106464)
        self.assertTrue(payload["hot_cleanup_summary"]["cleanup_success"])
        self.assertEqual(payload["hot_cleanup_summary"]["deleted_table_summary"][0]["table"], "stock_minute_bar_1m")
        self.assertEqual(page_response.status_code, 200)
        self.assertIn("Runtime Hot Cleanup Status", page_response.text)
        self.assertIn("DIRTY_HOT_KEEP2_CLEANUP_EXECUTE_PASS", page_response.text)
        self.assertIn("20260630, 20260701, 20260702, 20260703, 20260706", page_response.text)
        self.assertIn("20260525, 20260526", page_response.text)
        self.assertIn("6106464", page_response.text)
        self.assertIn("stock_minute_bar_1m", page_response.text)
        self.assertIn("common_trigger_state", page_response.text)
        self.assertNotIn("DIRTY_HOT_KEEP_2_CLEANUP_CONFIRMED", page_response.text)
        self.assertNotIn("RUNTIME_HOT_KEEP5_DIRECT_DELETE_NO_ARCHIVE_CONFIRMED", page_response.text)
        self.assertNotIn("<form", page_response.text.lower())
        self.assertEqual(repo.forbidden_writes["n5_outbox"], 0)


if __name__ == "__main__":
    unittest.main()
