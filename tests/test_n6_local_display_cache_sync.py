import json
import tempfile
import unittest
from pathlib import Path

from ashare_v3.user.local_display_cache_sync import (
    EXPECTED_ROWS,
    LocalDisplayCachePreflightSnapshot,
    build_parser,
    run_local_display_cache_sync,
    validate_contract_artifact,
)


class FakeLocalDisplayCacheSyncRepository:
    def __init__(self, snapshot: LocalDisplayCachePreflightSnapshot) -> None:
        self.snapshot = snapshot
        self.fetch_calls = 0
        self.commit_calls = 0
        self.committed_args: dict[str, object] | None = None

    def fetch_preflight_snapshot(
        self,
        *,
        cache_run_id: str,
        cache_version: str,
        source_condition_run_id: str,
        source_trade_date: str,
        mapping_strategy: str,
    ) -> LocalDisplayCachePreflightSnapshot:
        self.fetch_calls += 1
        self.snapshot.cache_run_id = cache_run_id
        self.snapshot.cache_version = cache_version
        self.snapshot.source_condition_run_id = source_condition_run_id
        self.snapshot.source_trade_date = source_trade_date
        self.snapshot.mapping_strategy = mapping_strategy
        return self.snapshot

    def commit_sync(
        self,
        *,
        cache_run_id: str,
        cache_version: str,
        source_condition_run_id: str,
        source_trade_date: str,
        mapping_strategy: str,
        expected_rows: dict[str, int],
    ) -> dict[str, object]:
        self.commit_calls += 1
        self.committed_args = {
            "cache_run_id": cache_run_id,
            "cache_version": cache_version,
            "source_condition_run_id": source_condition_run_id,
            "source_trade_date": source_trade_date,
            "mapping_strategy": mapping_strategy,
            "expected_rows": expected_rows,
        }
        return {
            "committed": True,
            "inserted_rows": expected_rows,
            "activated": True,
        }


class N6LocalDisplayCacheSyncTest(unittest.TestCase):
    def test_parser_exposes_double_gate_and_required_inputs(self) -> None:
        parser = build_parser()
        option_strings = {option for action in parser._actions for option in action.option_strings}

        for option in (
            "--cache-run-id",
            "--cache-version",
            "--source-condition-run-id",
            "--source-trade-date",
            "--mapping-strategy",
            "--contract-path",
            "--preflight-path",
            "--rollback-sql-path",
            "--execute",
            "--user-confirmed",
        ):
            self.assertIn(option, option_strings)

    def test_missing_execute_blocks_before_repository_read_or_write(self) -> None:
        repo = FakeLocalDisplayCacheSyncRepository(passing_snapshot())

        report = run_local_display_cache_sync(
            repository=repo,
            cache_run_id=cache_run_id(),
            cache_version="n6_display_cache_v1",
            source_condition_run_id="condition_layer_20260604_source_20260604_v1",
            source_trade_date="20260604",
            mapping_strategy="cartesian_fanout_v1",
            execute=False,
            user_confirmed=True,
            contract_path=contract_path(),
            preflight_path=preflight_path(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_execute_flag", report["blockers"])
        self.assertFalse(report["database_written"])
        self.assertEqual(repo.fetch_calls, 0)
        self.assertEqual(repo.commit_calls, 0)

    def test_missing_user_confirmed_blocks_before_repository_read_or_write(self) -> None:
        repo = FakeLocalDisplayCacheSyncRepository(passing_snapshot())

        report = run_local_display_cache_sync(
            repository=repo,
            cache_run_id=cache_run_id(),
            cache_version="n6_display_cache_v1",
            source_condition_run_id="condition_layer_20260604_source_20260604_v1",
            source_trade_date="20260604",
            mapping_strategy="cartesian_fanout_v1",
            execute=True,
            user_confirmed=False,
            contract_path=contract_path(),
            preflight_path=preflight_path(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_user_confirmed_flag", report["blockers"])
        self.assertFalse(report["database_written"])
        self.assertEqual(repo.fetch_calls, 0)
        self.assertEqual(repo.commit_calls, 0)

    def test_contract_requires_exact_expected_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "contract.json"
            path.write_text(
                json.dumps(
                    {
                        "result": "CONTRACT_PASS",
                        "cache_run_id": cache_run_id(),
                        "cache_version": "n6_display_cache_v1",
                        "source_condition_run_id": "condition_layer_20260604_source_20260604_v1",
                        "source_trade_date": "20260604",
                        "mapping_strategy": "cartesian_fanout_v1",
                        "expected_rows": {**EXPECTED_ROWS, "n6_stock_display_cache": 1},
                    }
                ),
                encoding="utf-8",
            )

            blockers = validate_contract_artifact(str(path), cache_run_id())

        self.assertIn("contract_expected_rows_mismatch", blockers)

    def test_preflight_blocks_existing_cache_run_id(self) -> None:
        snapshot = passing_snapshot()
        snapshot.cache_run_id_rows = 1
        repo = FakeLocalDisplayCacheSyncRepository(snapshot)

        report = run_local_display_cache_sync(
            repository=repo,
            cache_run_id=cache_run_id(),
            cache_version="n6_display_cache_v1",
            source_condition_run_id="condition_layer_20260604_source_20260604_v1",
            source_trade_date="20260604",
            mapping_strategy="cartesian_fanout_v1",
            execute=True,
            user_confirmed=True,
            contract_path=contract_path(),
            preflight_path=preflight_path(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("cache_run_id_already_exists", report["blockers"])
        self.assertEqual(repo.commit_calls, 0)

    def test_preflight_blocks_duplicate_or_missing_preview_rows(self) -> None:
        snapshot = passing_snapshot()
        snapshot.duplicate_row_hash = 1
        repo = FakeLocalDisplayCacheSyncRepository(snapshot)

        report = run_local_display_cache_sync(
            repository=repo,
            cache_run_id=cache_run_id(),
            cache_version="n6_display_cache_v1",
            source_condition_run_id="condition_layer_20260604_source_20260604_v1",
            source_trade_date="20260604",
            mapping_strategy="cartesian_fanout_v1",
            execute=True,
            user_confirmed=True,
            contract_path=contract_path(),
            preflight_path=preflight_path(),
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("preview_validation_failed", report["blockers"])
        self.assertEqual(repo.commit_calls, 0)

    def test_execute_commits_only_cache_rows_after_passing_preflight(self) -> None:
        repo = FakeLocalDisplayCacheSyncRepository(passing_snapshot())

        report = run_local_display_cache_sync(
            repository=repo,
            cache_run_id=cache_run_id(),
            cache_version="n6_display_cache_v1",
            source_condition_run_id="condition_layer_20260604_source_20260604_v1",
            source_trade_date="20260604",
            mapping_strategy="cartesian_fanout_v1",
            execute=True,
            user_confirmed=True,
            contract_path=contract_path(),
            preflight_path=preflight_path(),
        )

        self.assertEqual(report["result"], "EXECUTED")
        self.assertTrue(report["database_written"])
        self.assertEqual(repo.commit_calls, 1)
        self.assertEqual(report["planned_rows"], EXPECTED_ROWS)
        self.assertEqual(report["write_result"]["inserted_rows"], EXPECTED_ROWS)
        self.assertTrue(report["write_result"]["activated"])
        self.assertFalse(report["outbox_consumed_or_updated"])
        self.assertFalse(report["worker_started"])
        self.assertFalse(report["proposal_order_trade_position_pnl_real_trade"])

    def test_rollback_sql_hard_fails_before_first_update_or_delete(self) -> None:
        sql = Path("sql/N6_local_display_cache_sync_20260604_rollback.sql").read_text(encoding="utf-8")
        upper = sql.upper()
        first_raise = upper.find("RAISE EXCEPTION")
        first_update = upper.find("UPDATE N6_DISPLAY_CACHE_RUN")
        first_delete = upper.find("DELETE FROM")

        self.assertGreaterEqual(first_raise, 0)
        self.assertGreaterEqual(first_update, 0)
        self.assertGreaterEqual(first_delete, 0)
        self.assertLess(first_raise, first_update)
        self.assertLess(first_raise, first_delete)
        self.assertNotIn("DROP TABLE", upper)
        self.assertNotIn("CASCADE", upper)
        self.assertNotIn("TRUNCATE", upper)
        for table in (
            "n6_stock_display_cache",
            "n6_index_display_cache",
            "n6_board_display_cache",
            "n6_index_membership_display_cache",
            "n6_board_membership_display_cache",
            "n6_display_cache_run",
        ):
            self.assertIn(table, sql)


def cache_run_id() -> str:
    return "n6_display_cache_sync_20260604_condition_layer_20260604_source_20260604_v1"


def contract_path() -> str:
    tmp = Path(tempfile.mkdtemp()) / "contract.json"
    tmp.write_text(
        json.dumps(
            {
                "result": "CONTRACT_PASS",
                "cache_run_id": cache_run_id(),
                "cache_version": "n6_display_cache_v1",
                "source_condition_run_id": "condition_layer_20260604_source_20260604_v1",
                "source_trade_date": "20260604",
                "mapping_strategy": "cartesian_fanout_v1",
                "expected_rows": EXPECTED_ROWS,
            }
        ),
        encoding="utf-8",
    )
    return str(tmp)


def preflight_path() -> str:
    tmp = Path(tempfile.mkdtemp()) / "preflight.json"
    tmp.write_text(
        json.dumps(
            {
                "result": "PREFLIGHT_PASS",
                "cache_run_id": cache_run_id(),
                "cache_version": "n6_display_cache_v1",
                "source_condition_run_id": "condition_layer_20260604_source_20260604_v1",
                "source_trade_date": "20260604",
                "mapping_strategy": "cartesian_fanout_v1",
                "preview_row_counts": EXPECTED_ROWS,
                "validation_summary": {
                    "duplicate_fanout_key": 0,
                    "duplicate_row_hash": 0,
                    "missing_required": 0,
                    "invalid_board_type": 0,
                    "invalid_direction": 0,
                    "null_identity_key": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    return str(tmp)


def passing_snapshot() -> LocalDisplayCachePreflightSnapshot:
    return LocalDisplayCachePreflightSnapshot(
        cache_run_id=cache_run_id(),
        cache_version="n6_display_cache_v1",
        source_condition_run_id="condition_layer_20260604_source_20260604_v1",
        source_trade_date="20260604",
        mapping_strategy="cartesian_fanout_v1",
        latest_active_n2_run_id="condition_layer_20260604_source_20260604_v1",
        latest_active_n2_status="passed_active",
        source_counts={
            "stock_display_source": 1952,
            "index_display_source": 9,
            "board_display_source": 428,
            "index_membership_source": 12841,
            "board_membership_source": 56960,
        },
        target_table_exists={
            "n6_display_cache_run": True,
            "n6_stock_display_cache": True,
            "n6_index_display_cache": True,
            "n6_board_display_cache": True,
            "n6_index_membership_display_cache": True,
            "n6_board_membership_display_cache": True,
        },
        target_row_counts={
            "n6_display_cache_run": 0,
            "n6_stock_display_cache": 0,
            "n6_index_display_cache": 0,
            "n6_board_display_cache": 0,
            "n6_index_membership_display_cache": 0,
            "n6_board_membership_display_cache": 0,
        },
        preview_row_counts=EXPECTED_ROWS.copy(),
        cache_run_id_rows=0,
        active_cache_same_version_rows=0,
        active_cache_same_source_version_rows=0,
        scoped_target_rows=0,
        duplicate_fanout_key=0,
        duplicate_row_hash=0,
        missing_required=0,
        invalid_board_type=0,
        invalid_direction=0,
        null_identity_key=0,
    )
