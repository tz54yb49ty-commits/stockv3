from pathlib import Path
import unittest

from ashare_v3.market.hint_1m_projection_persistence import (
    HINT_1M_PROOF_KIND,
    HINT_1M_MIDDAY_BRIDGE_PROOF_KIND,
    HintProjectionPersistenceError,
    build_hint_projection_rollback_sql,
    build_hint_projection_run_id,
    build_hint_projection_write_plan,
    ensure_clean_hint_projection_target,
    parse_hint_projection_run_id,
)


PROPOSED_RUN_ID = (
    "realtime_hint_projection_metric_20260629_until_1500__asset_index_board__"
    "index_board_1m_hint_projection_v1__"
    "market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1"
)
MIDDAY_BRIDGE_RUN_ID = (
    "realtime_hint_projection_metric_20260630_until_1300__asset_index_board__"
    "index_board_1m_hint_projection_v1_midday_bridge_v1__"
    "market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1"
)
SUBSCRIPTION_RUN_ID = "market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1"
MIDDAY_BRIDGE_SUBSCRIPTION_RUN_ID = (
    "market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1"
)
SOURCE_ARTIFACT_PATH = "docs/intraday_live_current/20260629/N3_hint_index_board_1m_1500_frequency8_payload.json"
SOURCE_ARTIFACT_PAYLOAD_HASH = "48fd16429adb2de11521106881c63d16bcbc9677415578c8e9a156a1ee4279be"
SOURCE_ARTIFACT_SHA256 = SOURCE_ARTIFACT_PAYLOAD_HASH
SOURCE_ARTIFACT_FILE_SHA256 = "804edb09f3691b60825b1e47e02e647d0d60f11d63a1363953b70b399df19225"
HASH_POLICY = "payload_hash_canonical_file_sha256_trace"
SOURCE_PREVIOUS_DAY_RUN_ID = (
    "previous_day_minute_preload_20260626_for_20260629__"
    "market_data_subscription_20260629_condition_layer_20260626_source_20260626_for_20260629_v1"
)
SOURCE_CONTEXT_RUN_ID = "trigger_context_snapshot_20260629_condition_layer_20260626_source_20260626_for_20260629_v1__atomic_rule_v1"


class N3HintIndexBoard1mProjectionPersistenceTest(unittest.TestCase):
    def test_schema_artifacts_are_additive_and_index_board_only(self) -> None:
        migration = Path("sql/N3_hint_index_board_1m_projection_schema.sql").read_text()
        rollback = Path("sql/N3_hint_index_board_1m_projection_schema_rollback.sql").read_text()

        self.assertIn("CREATE TABLE IF NOT EXISTS index_realtime_hint_projection_metric", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS board_realtime_hint_projection_metric", migration)
        self.assertNotIn("stock_realtime_hint_projection_metric", migration)
        self.assertIn("proof_kind = 'index_board_1m_hint_projection_v1'", migration)
        self.assertIn("not_n5_final_proof = true", migration)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS", migration)
        for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "TRUNCATE ", "ALTER TABLE DROP", "DROP TABLE "):
            self.assertNotIn(forbidden, migration.upper())

        self.assertIn("DROP TABLE IF EXISTS index_realtime_hint_projection_metric", rollback)
        self.assertIn("DROP TABLE IF EXISTS board_realtime_hint_projection_metric", rollback)
        self.assertNotIn("stock_realtime_hint_projection_metric", rollback)
        self.assertNotIn("DELETE FROM", rollback.upper())

    def test_run_id_build_parse_exact_and_unsafe_suffixes_fail_closed(self) -> None:
        built = build_hint_projection_run_id(
            trade_date="20260629",
            until_hhmm="1500",
            source_subscription_run_id=SUBSCRIPTION_RUN_ID,
        )
        self.assertEqual(built, PROPOSED_RUN_ID)

        parsed = parse_hint_projection_run_id(PROPOSED_RUN_ID)
        self.assertEqual(parsed["trade_date"], "20260629")
        self.assertEqual(parsed["until_hhmm"], "1500")
        self.assertEqual(parsed["asset_scope"], "index_board")
        self.assertEqual(parsed["proof_kind"], HINT_1M_PROOF_KIND)
        self.assertEqual(parsed["source_subscription_run_id"], SUBSCRIPTION_RUN_ID)

        unsafe = [
            PROPOSED_RUN_ID.replace("__asset_index_board__", "__asset_all__"),
            PROPOSED_RUN_ID.replace("__asset_index_board__", "__asset_stock__"),
            PROPOSED_RUN_ID.replace("index_board_1m_hint_projection_v1", "index_board_1m_hint_projection_v2"),
            PROPOSED_RUN_ID.replace("__" + SUBSCRIPTION_RUN_ID, ""),
            PROPOSED_RUN_ID.replace("_until_1500__", "_until_2460__"),
        ]
        for run_id in unsafe:
            with self.subTest(run_id=run_id):
                with self.assertRaises(HintProjectionPersistenceError):
                    parse_hint_projection_run_id(run_id)

    def test_midday_bridge_run_id_build_parse_write_plan_and_rollback(self) -> None:
        built = build_hint_projection_run_id(
            trade_date="20260630",
            until_hhmm="1300",
            source_subscription_run_id=MIDDAY_BRIDGE_SUBSCRIPTION_RUN_ID,
            proof_kind=HINT_1M_MIDDAY_BRIDGE_PROOF_KIND,
        )
        self.assertEqual(built, MIDDAY_BRIDGE_RUN_ID)

        parsed = parse_hint_projection_run_id(MIDDAY_BRIDGE_RUN_ID)
        self.assertEqual(parsed["trade_date"], "20260630")
        self.assertEqual(parsed["until_hhmm"], "1300")
        self.assertEqual(parsed["asset_scope"], "index_board")
        self.assertEqual(parsed["proof_kind"], HINT_1M_MIDDAY_BRIDGE_PROOF_KIND)
        self.assertEqual(parsed["source_subscription_run_id"], MIDDAY_BRIDGE_SUBSCRIPTION_RUN_ID)

        bridge_proof = sample_proof("board", "board:TDX:881442", "SELL_HINT", 1300)
        bridge_proof.update(
            {
                "midday_bridge_policy": "hint_1300_as_1130_close_v1",
                "raw_minute_label": "13:00",
                "logical_minute_label": "11:30",
                "current_window_start": "11:01",
                "current_window_end": "11:30",
                "previous_completed_window_start": "10:31",
                "previous_completed_window_end": "11:00",
                "current_window_elapsed_count": 30,
                "proof_input_minute_label": "13:00",
            }
        )
        plan = build_hint_projection_write_plan(
            projection_run_id=MIDDAY_BRIDGE_RUN_ID,
            proof_rows=[bridge_proof],
            source_condition_run_id="condition_layer_20260629_source_20260629_for_20260630_v1",
            source_subscription_run_id=MIDDAY_BRIDGE_SUBSCRIPTION_RUN_ID,
            source_artifact_path="docs/intraday_live_current/20260630/N3_hint_index_board_1m_1300_midday_bridge_frequency8_payload.json",
            source_artifact_sha256="payload-hash",
            source_artifact_payload_hash="payload-hash",
            source_artifact_file_sha256="file-hash",
            source_previous_day_minute_run_id=(
                "previous_day_minute_preload_20260629_for_20260630__"
                "market_data_subscription_20260630_condition_layer_20260629_source_20260629_for_20260630_v1"
            ),
            source_context_run_id="trigger_context_snapshot_20260630_condition_layer_20260629_source_20260629_for_20260630_v1__atomic_rule_v1",
        )
        self.assertEqual(plan["proof_kind"], HINT_1M_MIDDAY_BRIDGE_PROOF_KIND)
        self.assertEqual(plan["common_market_data_run"]["raw_json"]["proof_kind"], HINT_1M_MIDDAY_BRIDGE_PROOF_KIND)
        self.assertEqual(plan["metric_rows"]["board"][0]["proof_kind"], HINT_1M_PROOF_KIND)
        self.assertEqual(
            plan["metric_rows"]["board"][0]["raw_json"]["projection_run_proof_kind"],
            HINT_1M_MIDDAY_BRIDGE_PROOF_KIND,
        )
        self.assertEqual(
            plan["metric_rows"]["board"][0]["trace_json"]["projection_run_proof_kind"],
            HINT_1M_MIDDAY_BRIDGE_PROOF_KIND,
        )
        self.assertEqual(
            plan["metric_rows"]["board"][0]["trace_json"]["midday_bridge_policy"],
            "hint_1300_as_1130_close_v1",
        )

        rollback = build_hint_projection_rollback_sql(MIDDAY_BRIDGE_RUN_ID)
        self.assertIn(MIDDAY_BRIDGE_RUN_ID, rollback)
        self.assertIn("DELETE FROM board_realtime_hint_projection_metric", rollback)
        self.assertNotIn("stock_realtime_hint_projection_metric", rollback)

        unsafe = [
            MIDDAY_BRIDGE_RUN_ID.replace("midday_bridge_v1", "midday_bridge_v2"),
            MIDDAY_BRIDGE_RUN_ID.replace("index_board_1m_hint_projection_v1_midday_bridge_v1", "index_board_1m_hint_projection_v1_unknown"),
            MIDDAY_BRIDGE_RUN_ID.replace("__asset_index_board__", "__asset_all__"),
            MIDDAY_BRIDGE_RUN_ID.replace("__asset_index_board__", "__asset_stock__"),
        ]
        for run_id in unsafe:
            with self.subTest(run_id=run_id):
                with self.assertRaises(HintProjectionPersistenceError):
                    parse_hint_projection_run_id(run_id)

    def test_write_plan_accepts_index_board_rows_and_rejects_stock(self) -> None:
        rows = [
            sample_proof("index", "index:SH:000001", "BUY_HINT", 101),
            sample_proof("index", "index:SH:000905", "BUY_HINT", 102),
            sample_proof("board", "board:TDX:881019", "BUY_HINT", 201),
            sample_proof("board", "board:TDX:881034", "BUY_HINT", 202),
            sample_proof("board", "board:TDX:881289", "SELL_HINT", 203, projection_30m_type="volume_up"),
            sample_proof("board", "board:TDX:881336", "BUY_HINT", 204),
            sample_proof("board", "board:TDX:881394", "BUY_HINT", 205),
            sample_proof("board", "board:TDX:881416", "BUY_HINT", 206),
        ]

        plan = build_hint_projection_write_plan(
            projection_run_id=PROPOSED_RUN_ID,
            proof_rows=rows,
            source_condition_run_id="condition_layer_20260626_source_20260626_for_20260629_v1",
            source_subscription_run_id=SUBSCRIPTION_RUN_ID,
            source_artifact_path=SOURCE_ARTIFACT_PATH,
            source_artifact_sha256=SOURCE_ARTIFACT_SHA256,
            source_artifact_payload_hash=SOURCE_ARTIFACT_PAYLOAD_HASH,
            source_artifact_file_sha256=SOURCE_ARTIFACT_FILE_SHA256,
            source_previous_day_minute_run_id=SOURCE_PREVIOUS_DAY_RUN_ID,
            source_context_run_id=SOURCE_CONTEXT_RUN_ID,
        )

        self.assertEqual(plan["allowed_write_tables"], [
            "common_market_data_run",
            "common_market_data_quality_item",
            "index_realtime_hint_projection_metric",
            "board_realtime_hint_projection_metric",
        ])
        self.assertFalse(plan["writes_outbox"])
        self.assertEqual(plan["rows_by_asset"], {"index": 2, "board": 6})
        self.assertEqual(plan["metric_ready"], {"ready": 8, "not_ready": 0})
        self.assertEqual(len(plan["metric_rows"]["index"]), 2)
        self.assertEqual(len(plan["metric_rows"]["board"]), 6)
        self.assertNotIn("stock", plan["metric_rows"])
        self.assertEqual(plan["metric_rows"]["index"][0]["source_artifact_sha256"], SOURCE_ARTIFACT_SHA256)
        index_row = plan["metric_rows"]["index"][0]
        self.assertEqual(index_row["source_artifact_sha256"], SOURCE_ARTIFACT_PAYLOAD_HASH)
        self.assertEqual(index_row["raw_json"]["source_artifact_payload_hash"], SOURCE_ARTIFACT_PAYLOAD_HASH)
        self.assertEqual(index_row["raw_json"]["source_artifact_file_sha256"], SOURCE_ARTIFACT_FILE_SHA256)
        self.assertEqual(index_row["raw_json"]["source_artifact_hash_policy"], HASH_POLICY)
        self.assertEqual(index_row["trace_json"]["source_artifact_payload_hash"], SOURCE_ARTIFACT_PAYLOAD_HASH)
        self.assertEqual(index_row["trace_json"]["source_artifact_file_sha256"], SOURCE_ARTIFACT_FILE_SHA256)
        self.assertEqual(index_row["trace_json"]["source_artifact_hash_policy"], HASH_POLICY)
        self.assertEqual(plan["common_market_data_run"]["raw_json"]["source_artifact_payload_hash"], SOURCE_ARTIFACT_PAYLOAD_HASH)
        self.assertEqual(plan["common_market_data_run"]["raw_json"]["source_artifact_file_sha256"], SOURCE_ARTIFACT_FILE_SHA256)
        self.assertEqual(plan["common_market_data_run"]["raw_json"]["source_artifact_hash_policy"], HASH_POLICY)
        self.assertTrue(all(row["not_n5_final_proof"] is True for rows in plan["metric_rows"].values() for row in rows))

        with self.assertRaisesRegex(HintProjectionPersistenceError, "stock"):
            build_hint_projection_write_plan(
                projection_run_id=PROPOSED_RUN_ID,
                proof_rows=[sample_proof("stock", "stock:SH:600000", "BUY_HINT", 1)],
                source_condition_run_id="condition_layer_20260626_source_20260626_for_20260629_v1",
                source_subscription_run_id=SUBSCRIPTION_RUN_ID,
                source_artifact_path=SOURCE_ARTIFACT_PATH,
                source_artifact_sha256=SOURCE_ARTIFACT_SHA256,
                source_previous_day_minute_run_id=SOURCE_PREVIOUS_DAY_RUN_ID,
                source_context_run_id=SOURCE_CONTEXT_RUN_ID,
            )

        # File SHA is trace-only: a different file wrapper hash does not block
        # when the canonical payload hash matches.
        trace_only_file_hash_plan = build_hint_projection_write_plan(
            projection_run_id=PROPOSED_RUN_ID,
            proof_rows=[sample_proof("index", "index:SH:000001", "BUY_HINT", 101)],
            source_condition_run_id="condition_layer_20260626_source_20260626_for_20260629_v1",
            source_subscription_run_id=SUBSCRIPTION_RUN_ID,
            source_artifact_path=SOURCE_ARTIFACT_PATH,
            source_artifact_sha256=SOURCE_ARTIFACT_PAYLOAD_HASH,
            source_artifact_payload_hash=SOURCE_ARTIFACT_PAYLOAD_HASH,
            source_artifact_file_sha256="file-wrapper-hash-drift",
            source_previous_day_minute_run_id=SOURCE_PREVIOUS_DAY_RUN_ID,
            source_context_run_id=SOURCE_CONTEXT_RUN_ID,
        )
        self.assertEqual(
            trace_only_file_hash_plan["metric_rows"]["index"][0]["trace_json"]["source_artifact_file_sha256"],
            "file-wrapper-hash-drift",
        )

        with self.assertRaisesRegex(HintProjectionPersistenceError, "payload hash"):
            build_hint_projection_write_plan(
                projection_run_id=PROPOSED_RUN_ID,
                proof_rows=[sample_proof("index", "index:SH:000001", "BUY_HINT", 101)],
                source_condition_run_id="condition_layer_20260626_source_20260626_for_20260629_v1",
                source_subscription_run_id=SUBSCRIPTION_RUN_ID,
                source_artifact_path=SOURCE_ARTIFACT_PATH,
                source_artifact_sha256=SOURCE_ARTIFACT_PAYLOAD_HASH,
                source_artifact_payload_hash="different-payload-hash",
                source_artifact_file_sha256=SOURCE_ARTIFACT_FILE_SHA256,
                source_previous_day_minute_run_id=SOURCE_PREVIOUS_DAY_RUN_ID,
                source_context_run_id=SOURCE_CONTEXT_RUN_ID,
            )

    def test_dirty_target_and_rollback_contract_fail_closed(self) -> None:
        clean = {
            "run_exists": 0,
            "quality_rows": 0,
            "index_rows": 0,
            "board_rows": 0,
            "outbox_refs": 0,
            "inbox_refs": 0,
            "checkpoint_refs": 0,
            "n4_refs": 0,
            "n5_refs": 0,
            "n6_refs": 0,
        }
        ensure_clean_hint_projection_target(clean, PROPOSED_RUN_ID)
        dirty = dict(clean)
        dirty["board_rows"] = 1
        with self.assertRaisesRegex(HintProjectionPersistenceError, "dirty"):
            ensure_clean_hint_projection_target(dirty, PROPOSED_RUN_ID)

        rollback = build_hint_projection_rollback_sql(PROPOSED_RUN_ID)
        self.assertIn(PROPOSED_RUN_ID, rollback)
        self.assertIn("common_event_outbox", rollback)
        self.assertIn("common_event_inbox", rollback)
        self.assertIn("common_event_consumer_checkpoint", rollback)
        self.assertIn("common_trigger_state", rollback)
        self.assertIn("common_trigger_match", rollback)
        self.assertIn("common_action", rollback)
        self.assertIn("user_signal", rollback)
        self.assertIn("DELETE FROM index_realtime_hint_projection_metric", rollback)
        self.assertIn("DELETE FROM board_realtime_hint_projection_metric", rollback)
        self.assertNotIn("stock_realtime_hint_projection_metric", rollback)
        self.assertNotIn("DELETE FROM common_event_outbox", rollback)

    def test_missing_first_30m_previous_trade_date_reference_quality_item_uses_schema_allowed_status(self) -> None:
        invalid_first_window_proof = sample_proof("board", "board:TDX:881442", "SELL_HINT", 1300)
        invalid_first_window_proof.update(
            {
                "valid": False,
                "blocked_reasons": ["missing_previous_trade_date_last_30m_open_close"],
                "current_window_start": "09:31",
                "current_window_end": "10:00",
                "previous_completed_window_start": "14:31",
                "previous_completed_window_end": "15:00",
                "previous_completed_window_source": "previous_trade_date_last_30m",
            }
        )

        plan = build_hint_projection_write_plan(
            projection_run_id=PROPOSED_RUN_ID,
            proof_rows=[invalid_first_window_proof],
            source_condition_run_id="condition_layer_20260626_source_20260626_for_20260629_v1",
            source_subscription_run_id=SUBSCRIPTION_RUN_ID,
            source_artifact_path=SOURCE_ARTIFACT_PATH,
            source_artifact_sha256="payload-hash",
            source_artifact_payload_hash="payload-hash",
            source_artifact_file_sha256="file-hash",
            source_previous_day_minute_run_id=SOURCE_PREVIOUS_DAY_RUN_ID,
            source_context_run_id=SOURCE_CONTEXT_RUN_ID,
        )

        self.assertEqual(plan["rows_by_asset"], {"board": 1})
        self.assertEqual(plan["metric_ready"], {"ready": 0, "not_ready": 1})
        self.assertEqual(plan["metric_fact_exclusion_count"], 0)
        self.assertEqual(plan["metric_fact_exclusion_reason_counts"], {})

        board_row = plan["metric_rows"]["board"][0]
        self.assertFalse(board_row["metric_ready"])
        self.assertEqual(board_row["blocked_reasons"], ["missing_previous_trade_date_last_30m_open_close"])
        self.assertEqual(board_row["previous_completed_window_start"], "14:31")
        self.assertEqual(board_row["previous_completed_window_end"], "15:00")
        self.assertEqual(board_row["trace_json"]["previous_completed_window_source"], "previous_trade_date_last_30m")


def sample_proof(
    asset_kind: str,
    identity_key: str,
    condition_key: str,
    context_id: int,
    *,
    projection_30m_type: str = "none",
) -> dict[str, object]:
    code = identity_key.split(":")[-1]
    return {
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "code": code,
        "name": code,
        "direction": "sell" if condition_key == "SELL_HINT" else "buy",
        "condition_key": condition_key,
        "original_condition_key": condition_key,
        "source_condition_pool_id": context_id + 1000,
        "source_minute_target_scope_id": context_id + 2000,
        "proof_kind": HINT_1M_PROOF_KIND,
        "source_mode": "index_board_frequency8_1m",
        "metric_role": "hint_trigger_proof",
        "proof_owner": "N3",
        "proof_consumer": "N4",
        "not_n5_final_proof": True,
        "proof_input_minute_label": "15:00",
        "current_window_start": "14:31",
        "current_window_end": "15:00",
        "previous_completed_window_start": "14:01",
        "previous_completed_window_end": "14:30",
        "previous_completed_window_source": "current_trade_date_adjacent_previous_30m",
        "current_window_elapsed_count": 30,
        "full_window_count": 30,
        "current_30m_price": 100.0,
        "current_30m_elapsed_amount": 1000.0,
        "previous_day_same_elapsed_30m_amount": 900.0,
        "previous_day_full_30m_amount": 900.0,
        "current_30m_virtual_amount": 1000.0,
        "reference_30m_amount": 900.0,
        "reference_30m_entity_high": 99.0,
        "reference_30m_entity_low": 98.0,
        "projection_30m_type": projection_30m_type,
        "projection_30m_flag": projection_30m_type in {"volume_up", "shrink_down"},
        "valid": True,
        "blocked_reasons": [],
        "trigger_context_id": context_id,
    }


if __name__ == "__main__":
    unittest.main()
