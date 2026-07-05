import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import ashare_v3.market.previous_day_full_context_expansion_subscription_scope as previous_day_scope
from ashare_v3.market.previous_day_full_context_expansion_subscription_scope import (
    EXPANSION_SUBSCRIPTION_RUN_ID,
    build_previous_day_full_context_expansion_scope_from_plan_report,
    build_previous_day_expansion_pull_plan_rows,
    build_previous_day_expansion_rollback_sql,
    derive_previous_day_expansion_candidates,
    deduplicate_previous_day_expansion_candidates,
    run_previous_day_full_context_expansion_subscription_scope_execute,
)


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, object]] = []

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def execute(self, sql: str, values: object = None) -> None:
        self.executed.append((sql, values))


class _FakeTransaction:
    def __enter__(self) -> "_FakeTransaction":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor | None = None) -> None:
        self.cursor_obj = cursor or _FakeCursor()

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction()

    def cursor(self) -> _FakeCursor:
        return self.cursor_obj


class PreviousDayFullContextExpansionSubscriptionScopeTest(unittest.TestCase):
    def _zero_execute_baseline(self) -> dict[str, int]:
        return {
            "common_market_data_run": 0,
            "common_market_data_quality_item": 0,
            "common_market_data_subscription_candidate": 0,
            "common_market_data_subscription": 0,
            "common_market_data_pull_plan": 0,
            "common_event_outbox_refs": 0,
            "common_event_inbox_refs": 0,
            "common_event_consumer_checkpoint_refs": 0,
        }

    def _pr1_plan(self, *, rows: list[dict[str, object]] | None = None, blocked: bool = False) -> dict[str, object]:
        source_expansion_run_id = (
            "market_data_subscription_20260622_full_context_expansion_"
            "condition_layer_20260618_source_20260618_for_20260622_v1"
        )
        rows = rows if rows is not None else [
            {
                "subscription_ref": "dry_run:full_context_expansion_subscription:1",
                "run_id": source_expansion_run_id,
                "source_condition_run_id": "condition_layer_20260618_source_20260618_for_20260622_v1",
                "for_trade_date": "20260622",
                "source_trade_date": "20260618",
                "prev_trade_date": "20260618",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "exchange": "SH",
                "code": "600000",
                "display_code": "600000",
                "name": "sample stock",
                "required_data_kind": "minute_bar_1m",
                "data_trade_date": "20260622",
                "source_scope_tables": ["stock_minute_target_scope"],
                "source_scope_ids": [101],
                "source_scope_refs": ["stock_minute_target_scope:101"],
                "source_condition_pool_ids": [201],
                "condition_keys": ["BUY:M"],
                "directions": ["buy"],
                "allowed_signal_types": ["BUY"],
            },
            {
                "subscription_ref": "dry_run:full_context_expansion_subscription:2",
                "run_id": source_expansion_run_id,
                "source_condition_run_id": "condition_layer_20260618_source_20260618_for_20260622_v1",
                "for_trade_date": "20260622",
                "source_trade_date": "20260618",
                "prev_trade_date": "20260618",
                "asset_kind": "board",
                "identity_key": "board:TDX:880001",
                "exchange": "TDX",
                "code": "880001",
                "display_code": "880001",
                "name": "sample board",
                "required_data_kind": "minute_bar_1m",
                "data_trade_date": "20260622",
                "source_scope_tables": ["board_minute_target_scope"],
                "source_scope_ids": [301],
                "source_scope_refs": ["board_minute_target_scope:301"],
                "source_condition_pool_ids": [401],
                "condition_keys": ["SELL:M"],
                "directions": ["sell"],
                "allowed_signal_types": ["SELL"],
            },
        ]
        return {
            "stage": "N3_C1_FULL_CONTEXT_EXPANSION_SUBSCRIPTION_SCOPE",
            "passed": not blocked,
            "blocked": blocked,
            "market_data_run_id": source_expansion_run_id,
            "source_condition_run_id": "condition_layer_20260618_source_20260618_for_20260622_v1",
            "for_trade_date": "20260622",
            "source_trade_date": "20260618",
            "prev_trade_date": "20260618",
            "market_data_subscription_dedup": {
                "rows_included": True,
                "row_count": len(rows),
                "rows": rows,
            },
        }

    def _plan_report(self, **overrides: object) -> dict[str, object]:
        args = {
            "expansion_plan_report": self._pr1_plan(),
            "for_trade_date": "20260622",
            "source_trade_date": "20260618",
            "previous_trade_date": "20260618",
            "expansion_run_id": (
                "market_data_subscription_20260622_full_context_expansion_"
                "condition_layer_20260618_source_20260618_for_20260622_v1"
            ),
            "previous_day_expansion_run_id": (
                "previous_day_minute_preload_20260618_for_20260622_full_context_expansion__"
                "market_data_subscription_20260622_full_context_expansion_condition_layer_20260618_source_20260618_for_20260622_v1"
            ),
            "baseline": {
                "common_market_data_run": 0,
                "common_market_data_subscription_candidate": 0,
                "common_market_data_subscription": 0,
                "common_market_data_pull_plan": 0,
                "common_event_outbox_refs": 0,
                "common_event_inbox_refs": 0,
                "common_event_consumer_checkpoint_refs": 0,
            },
            "include_rows": True,
        }
        args.update(overrides)
        return build_previous_day_full_context_expansion_scope_from_plan_report(**args)

    def test_valid_pr1_plan_artifact_builds_previous_day_scope(self) -> None:
        report = self._plan_report()

        self.assertTrue(report["passed"])
        self.assertFalse(report["blocked"])
        self.assertEqual(report["source_expansion_run_id"], self._pr1_plan()["market_data_run_id"])
        self.assertEqual(report["previous_day_subscription_rows_planned"], 2)
        self.assertEqual(report["pull_plan_row_count"], 2)
        self.assertEqual(report["asset_count_by_asset_kind"], {"stock": 1, "index": 0, "board": 1})
        self.assertEqual({row["run_id"] for row in report["market_data_subscription_dedup"]["rows"]}, {report["market_data_run_id"]})
        self.assertEqual({row["required_data_kind"] for row in report["market_data_subscription_dedup"]["rows"]}, {"previous_day_minute_bar_1m"})
        self.assertEqual({row["data_trade_date"] for row in report["market_data_subscription_dedup"]["rows"]}, {"20260618"})

    def test_blocked_pr1_plan_artifact_blocks_previous_day_scope(self) -> None:
        report = self._plan_report(expansion_plan_report=self._pr1_plan(blocked=True))

        self.assertTrue(report["blocked"])
        self.assertIn("n3_previous_day_full_context_expansion_plan_passed", report["blockers"])

    def test_missing_pr1_plan_artifact_blocks_previous_day_scope(self) -> None:
        report = self._plan_report(expansion_plan_report=None)

        self.assertTrue(report["blocked"])
        self.assertIn("n3_previous_day_full_context_expansion_plan_loaded", report["blockers"])

    def test_empty_expansion_identities_block_previous_day_scope(self) -> None:
        report = self._plan_report(expansion_plan_report=self._pr1_plan(rows=[]))

        self.assertTrue(report["blocked"])
        self.assertIn("n3_previous_day_full_context_expansion_identities_nonempty", report["blockers"])

    def test_existing_previous_day_expansion_run_id_blocks_plan(self) -> None:
        report = self._plan_report(
            baseline={
                "common_market_data_run": 1,
                "common_market_data_subscription_candidate": 0,
                "common_market_data_subscription": 0,
                "common_market_data_pull_plan": 0,
                "common_event_outbox_refs": 0,
                "common_event_inbox_refs": 0,
                "common_event_consumer_checkpoint_refs": 0,
            }
        )

        self.assertTrue(report["blocked"])
        self.assertIn("n3_previous_day_full_context_previous_day_expansion_baseline_zero", report["blockers"])

    def test_date_mismatch_blocks_plan(self) -> None:
        report = self._plan_report(for_trade_date="20260623")

        self.assertTrue(report["blocked"])
        self.assertIn("n3_previous_day_full_context_for_trade_date_matches_plan", report["blockers"])

    def test_plan_report_path_is_read_only_and_does_not_mutate_n2_scope(self) -> None:
        report = self._plan_report()

        self.assertFalse(report["side_effects"]["business_data_written"])
        self.assertIn("stock/index/board_minute_target_scope", report["write_scope"]["forbidden"])

    def test_derives_previous_day_candidates_from_existing_minute_candidates(self) -> None:
        existing_rows = [
            {
                "run_id": EXPANSION_SUBSCRIPTION_RUN_ID,
                "source_condition_run_id": "condition_layer_20260602_source_20260602_v1",
                "for_trade_date": "20260603",
                "source_trade_date": "20260602",
                "prev_trade_date": "20260602",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "exchange": "SH",
                "code": "600000",
                "display_code": "600000",
                "name": "sample",
                "required_data_kind": "minute_bar_1m",
                "data_trade_date": "20260603",
                "source_scope_table": "stock_minute_target_scope",
                "source_scope_id": 101,
                "source_condition_pool_id": 201,
                "direction": "buy",
                "condition_key": "BUY:M",
                "allowed_signal_types": ["BUY"],
                "source_scope_required_flags": {"minute_required": True},
                "candidate_status": "planned",
            }
        ]

        candidates = derive_previous_day_expansion_candidates(
            expansion_run_id=EXPANSION_SUBSCRIPTION_RUN_ID,
            minute_candidate_rows=existing_rows,
            previous_day_minute_date="20260602",
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["required_data_kind"], "previous_day_minute_bar_1m")
        self.assertEqual(candidates[0]["data_trade_date"], "20260602")
        self.assertFalse(candidates[0]["source_scope_required_flags"]["minute_required"])
        self.assertTrue(candidates[0]["source_scope_required_flags"]["previous_day_minute_required"])
        self.assertTrue(candidates[0]["source_scope_required_flags"]["full_context_previous_day_expansion"])

    def test_dedup_previous_day_subscription_keeps_trace_rows(self) -> None:
        base = {
            "run_id": EXPANSION_SUBSCRIPTION_RUN_ID,
            "source_condition_run_id": "condition_layer_20260602_source_20260602_v1",
            "for_trade_date": "20260603",
            "source_trade_date": "20260602",
            "prev_trade_date": "20260602",
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "exchange": "SH",
            "code": "600000",
            "display_code": "600000",
            "name": "sample",
            "required_data_kind": "previous_day_minute_bar_1m",
            "data_trade_date": "20260602",
            "source_scope_table": "stock_minute_target_scope",
            "source_condition_pool_id": 201,
            "direction": "buy",
            "condition_key": "BUY:M",
            "allowed_signal_types": ["BUY"],
            "candidate_status": "planned",
        }
        candidates = [
            {**base, "candidate_ref": "c1", "source_scope_id": 101, "source_scope_ref": "stock_minute_target_scope:101"},
            {**base, "candidate_ref": "c2", "source_scope_id": 102, "source_scope_ref": "stock_minute_target_scope:102", "condition_key": "BUY_HINT"},
        ]

        subscriptions = deduplicate_previous_day_expansion_candidates(
            expansion_run_id=EXPANSION_SUBSCRIPTION_RUN_ID,
            candidates=candidates,
        )

        self.assertEqual(len(subscriptions), 1)
        self.assertEqual(subscriptions[0]["required_data_kind"], "previous_day_minute_bar_1m")
        self.assertEqual(subscriptions[0]["data_trade_date"], "20260602")
        self.assertEqual(subscriptions[0]["source_scope_row_count"], 2)
        self.assertEqual(subscriptions[0]["source_scope_ids"], [101, 102])
        self.assertEqual(subscriptions[0]["condition_keys"], ["BUY:M", "BUY_HINT"])

    def test_pull_plan_is_previous_day_and_asset_scoped(self) -> None:
        subscriptions = [
            {
                "subscription_ref": "s-stock",
                "asset_kind": "stock",
                "identity_key": "stock:SH:600000",
                "required_data_kind": "previous_day_minute_bar_1m",
                "data_trade_date": "20260602",
            },
            {
                "subscription_ref": "s-board",
                "asset_kind": "board",
                "identity_key": "board:TDX:880001",
                "required_data_kind": "previous_day_minute_bar_1m",
                "data_trade_date": "20260602",
            },
        ]

        rows = build_previous_day_expansion_pull_plan_rows(
            expansion_run_id=EXPANSION_SUBSCRIPTION_RUN_ID,
            subscriptions=subscriptions,
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual({row["required_data_kind"] for row in rows}, {"previous_day_minute_bar_1m"})
        self.assertEqual({row["data_trade_date"] for row in rows}, {"20260602"})
        self.assertEqual({row["execute_allowed"] for row in rows}, {False})

    def test_execute_runner_requires_double_confirmation_before_loading_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = str(Path(tmpdir) / "missing.json")
            with self.assertRaisesRegex(RuntimeError, "missing --execute"):
                run_previous_day_full_context_expansion_subscription_scope_execute(
                    dsn="postgresql://unused",
                    dry_run_path=missing_path,
                    execute=False,
                    user_confirmed=True,
                )
            with self.assertRaisesRegex(RuntimeError, "missing --user-confirmed"):
                run_previous_day_full_context_expansion_subscription_scope_execute(
                    dsn="postgresql://unused",
                    dry_run_path=missing_path,
                    execute=True,
                    user_confirmed=False,
                )

    def test_execute_persists_parent_run_and_quality_before_child_rows(self) -> None:
        report = self._plan_report()
        calls: list[str] = []

        def record(name: str, result: object):
            def _inner(*args: object, **kwargs: object) -> object:
                calls.append(name)
                return result

            return _inner

        with patch(
            "ashare_v3.market.previous_day_full_context_expansion_subscription_scope.audited_n3_market_execute_connect",
            return_value=_FakeConnection(),
        ), patch(
            "ashare_v3.market.previous_day_full_context_expansion_subscription_scope.fetch_previous_day_expansion_baseline",
            return_value=self._zero_execute_baseline(),
        ), patch(
            "ashare_v3.market.previous_day_full_context_expansion_subscription_scope.fetch_existing_previous_day_scope_counts",
            return_value={"candidate_rows": 0, "subscription_rows": 0, "pull_plan_rows": 0},
        ), patch(
            "ashare_v3.market.previous_day_full_context_expansion_subscription_scope.insert_previous_day_market_data_run",
            side_effect=record("run", None),
            create=True,
        ), patch(
            "ashare_v3.market.previous_day_full_context_expansion_subscription_scope.insert_quality_items",
            side_effect=record("quality", 10),
            create=True,
        ), patch(
            "ashare_v3.market.previous_day_full_context_expansion_subscription_scope.insert_subscription_candidates",
            side_effect=record("candidate", 2242),
        ), patch(
            "ashare_v3.market.previous_day_full_context_expansion_subscription_scope.insert_subscriptions",
            side_effect=record("subscription", {"s": 1}),
        ), patch(
            "ashare_v3.market.previous_day_full_context_expansion_subscription_scope.insert_pull_plans",
            side_effect=record("pull_plan", 3),
        ):
            result = previous_day_scope.persist_previous_day_scope_rows(
                dsn="postgresql://unused",
                report=report,
                expansion_run_id=report["market_data_run_id"],
            )

        self.assertEqual(calls, ["run", "quality", "candidate", "subscription", "pull_plan"])
        self.assertEqual(result["market_data_run_rows_written"], 1)
        self.assertEqual(result["quality_item_rows_written"], 10)
        self.assertEqual(result["candidate_rows_written"], 2242)
        self.assertEqual(result["subscription_rows_written"], 1)
        self.assertEqual(result["pull_plan_rows_written"], 3)
        self.assertEqual(result["event_outbox_rows_written"], 0)
        self.assertEqual(result["market_data_fact_rows_written"], 0)

    def test_execute_blocks_when_target_run_already_exists(self) -> None:
        report = self._plan_report()
        baseline = self._zero_execute_baseline()
        baseline["common_market_data_run"] = 1

        with patch(
            "ashare_v3.market.previous_day_full_context_expansion_subscription_scope.audited_n3_market_execute_connect",
            return_value=_FakeConnection(),
        ), patch(
            "ashare_v3.market.previous_day_full_context_expansion_subscription_scope.fetch_previous_day_expansion_baseline",
            return_value=baseline,
        ), patch(
            "ashare_v3.market.previous_day_full_context_expansion_subscription_scope.fetch_existing_previous_day_scope_counts",
            return_value={"candidate_rows": 0, "subscription_rows": 0, "pull_plan_rows": 0},
        ), patch(
            "ashare_v3.market.previous_day_full_context_expansion_subscription_scope.insert_subscription_candidates",
            return_value=0,
        ):
            with self.assertRaisesRegex(RuntimeError, "previous-day expansion scope already exists"):
                previous_day_scope.persist_previous_day_scope_rows(
                    dsn="postgresql://unused",
                    report=report,
                    expansion_run_id=report["market_data_run_id"],
                )

    def test_execute_blocks_when_child_rows_already_exist(self) -> None:
        report = self._plan_report()
        cases = [
            ("common_market_data_subscription_candidate", {"candidate_rows": 1, "subscription_rows": 0, "pull_plan_rows": 0}),
            ("common_market_data_subscription", {"candidate_rows": 0, "subscription_rows": 1, "pull_plan_rows": 0}),
            ("common_market_data_pull_plan", {"candidate_rows": 0, "subscription_rows": 0, "pull_plan_rows": 1}),
        ]

        for baseline_key, existing_counts in cases:
            with self.subTest(baseline_key=baseline_key):
                baseline = self._zero_execute_baseline()
                baseline[baseline_key] = 1
                with patch(
                    "ashare_v3.market.previous_day_full_context_expansion_subscription_scope.audited_n3_market_execute_connect",
                    return_value=_FakeConnection(),
                ), patch(
                    "ashare_v3.market.previous_day_full_context_expansion_subscription_scope.fetch_previous_day_expansion_baseline",
                    return_value=baseline,
                ), patch(
                    "ashare_v3.market.previous_day_full_context_expansion_subscription_scope.fetch_existing_previous_day_scope_counts",
                    return_value=existing_counts,
                ):
                    with self.assertRaisesRegex(RuntimeError, "previous-day expansion scope already exists"):
                        previous_day_scope.persist_previous_day_scope_rows(
                            dsn="postgresql://unused",
                            report=report,
                            expansion_run_id=report["market_data_run_id"],
                        )

    def test_previous_day_run_row_marks_generated_by_scope_execute(self) -> None:
        report = self._plan_report()
        cursor = _FakeCursor()

        previous_day_scope.insert_previous_day_market_data_run(
            cursor,
            report,
            report["market_data_run_id"],
        )

        self.assertEqual(len(cursor.executed), 1)
        _, values = cursor.executed[0]
        self.assertIn("previous_day_full_context_expansion_scope_execute", values)

    def test_rollback_hard_fails_before_delete_and_never_deletes_event_tables(self) -> None:
        sql = build_previous_day_expansion_rollback_sql(EXPANSION_SUBSCRIPTION_RUN_ID)
        first_raise = sql.upper().find("RAISE EXCEPTION")
        first_delete = sql.upper().find("DELETE FROM")
        self.assertNotEqual(first_raise, -1)
        self.assertLess(first_raise, first_delete)
        self.assertIn("common_event_outbox", sql)
        self.assertIn("common_event_inbox", sql)
        self.assertIn("common_event_consumer_checkpoint", sql)
        self.assertNotIn("DELETE FROM common_event_outbox", sql)
        self.assertNotIn("DELETE FROM common_event_inbox", sql)
        self.assertNotIn("DELETE FROM common_event_consumer_checkpoint", sql)
        self.assertIn("required_data_kind = 'previous_day_minute_bar_1m'", sql)


if __name__ == "__main__":
    unittest.main()
