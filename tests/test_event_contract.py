import unittest
from datetime import datetime, timezone
from pathlib import Path

from psycopg.types.json import Jsonb

from ashare_v3.events.ids import build_n3_dedup_key, build_stable_event_id
from ashare_v3.events.models import EventContractError
from ashare_v3.events.outbox import insert_outbox_event
from ashare_v3.market.event_factory import build_n3_market_event
from scripts.check_event_contract import run_check


class EventContractTest(unittest.TestCase):
    def test_event_id_is_stable_for_same_source_and_dedup_key(self) -> None:
        kwargs = {
            "source_layer": "N3_market_data",
            "event_type": "MarketSnapshotUpdated",
            "source_run_id": "market_data_run_20260525_093000",
            "dedup_key": "N3_market_data|MarketSnapshotUpdated|stock|stock:SH:600000|20260525|snapshot_time|2026-05-25T09:31:03+08:00|source_adapter|mootdx",
            "event_schema_version": "v1",
        }

        self.assertEqual(build_stable_event_id(**kwargs), build_stable_event_id(**kwargs))

    def test_dedup_key_is_stable_for_same_n3_market_event(self) -> None:
        kwargs = {
            "event_type": "MinuteBarClosed",
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "trade_date": "20260525",
            "minute_bar_time": "2026-05-25T09:31:00+08:00",
            "source_adapter": "mootdx",
        }

        self.assertEqual(build_n3_dedup_key(**kwargs), build_n3_dedup_key(**kwargs))

    def test_minute_bar_closed_v1_keeps_minute_bar_trace_contract(self) -> None:
        event = build_n3_market_event(
            event_type="MinuteBarClosed",
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260525",
            minute_bar_time="2026-05-25T09:31:00+08:00",
            event_time=datetime(2026, 5, 25, 1, 32, 0, tzinfo=timezone.utc),
            source_run_id="today_minute_bar_1m_20260525_until_0931",
            source_adapter="mootdx.std.bars",
            payload=valid_minute_bar_closed_v1_payload(),
        )

        self.assertEqual(event.event_schema_version, "v1")
        self.assertEqual(event.payload_json["minute_bar_id"], 202)

    def test_minute_bar_closed_v2_allows_closed_30m_summary_trace_without_minute_bar_id(self) -> None:
        payload = valid_minute_bar_closed_v2_payload()

        event = build_n3_market_event(
            event_type="MinuteBarClosed",
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260525",
            event_time=datetime(2026, 5, 25, 2, 0, 0, tzinfo=timezone.utc),
            source_run_id="minute_bar_closed_outbox_20260525__closed_minute_30m_replay_x",
            source_adapter="N3Closed30mSummaryAdapter",
            payload=payload,
            event_schema_version="v2",
            c2_run_id=payload["c2_run_id"],
            summary_id=payload["summary_id"],
            bucket_id=payload["bucket_id"],
        )

        self.assertEqual(event.event_schema_version, "v2")
        self.assertEqual(event.payload_json["closed_30m_summary_id"], 73)
        self.assertNotIn("minute_bar_id", event.payload_json)
        self.assertIn("c2_run_id", event.dedup_key)
        self.assertIn("summary_id|73", event.dedup_key)
        self.assertIn("bucket_id|0931_1000", event.dedup_key)

    def test_minute_bar_closed_v2_requires_pull_plan_id_and_source_minute_refs(self) -> None:
        payload = valid_minute_bar_closed_v2_payload()
        payload["pull_plan_id"] = None

        with self.assertRaises(EventContractError):
            build_n3_market_event(
                event_type="MinuteBarClosed",
                asset_kind="stock",
                identity_key="stock:SH:600000",
                trade_date="20260525",
                event_time=datetime(2026, 5, 25, 2, 0, 0, tzinfo=timezone.utc),
                source_run_id="minute_bar_closed_outbox_20260525__closed_minute_30m_replay_x",
                source_adapter="N3Closed30mSummaryAdapter",
                payload=payload,
                event_schema_version="v2",
                c2_run_id=payload["c2_run_id"],
                summary_id=payload["summary_id"],
                bucket_id=payload["bucket_id"],
            )

        payload = valid_minute_bar_closed_v2_payload()
        payload["source_minute_refs"] = []
        with self.assertRaises(EventContractError):
            build_n3_market_event(
                event_type="MinuteBarClosed",
                asset_kind="stock",
                identity_key="stock:SH:600000",
                trade_date="20260525",
                event_time=datetime(2026, 5, 25, 2, 0, 0, tzinfo=timezone.utc),
                source_run_id="minute_bar_closed_outbox_20260525__closed_minute_30m_replay_x",
                source_adapter="N3Closed30mSummaryAdapter",
                payload=payload,
                event_schema_version="v2",
                c2_run_id=payload["c2_run_id"],
                summary_id=payload["summary_id"],
                bucket_id=payload["bucket_id"],
            )

    def test_minute_bar_closed_v2_dedup_key_is_stable_and_distinct_from_v1(self) -> None:
        v1 = build_n3_dedup_key(
            event_type="MinuteBarClosed",
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260525",
            source_adapter="mootdx.std.bars",
            minute_bar_time="2026-05-25T09:31:00+08:00",
        )
        v2_kwargs = {
            "event_type": "MinuteBarClosed",
            "asset_kind": "stock",
            "identity_key": "stock:SH:600000",
            "trade_date": "20260525",
            "source_adapter": "N3Closed30mSummaryAdapter",
            "event_schema_version": "v2",
            "c2_run_id": "closed_minute_30m_replay_20260525_until_1500__subscription_x",
            "summary_id": 73,
            "bucket_id": "0931_1000",
        }

        self.assertEqual(build_n3_dedup_key(**v2_kwargs), build_n3_dedup_key(**v2_kwargs))
        self.assertNotEqual(v1, build_n3_dedup_key(**v2_kwargs))

    def test_n3_event_payload_requires_trace_fields(self) -> None:
        with self.assertRaises(EventContractError):
            build_n3_market_event(
                event_type="MarketSnapshotUpdated",
                asset_kind="stock",
                identity_key="stock:SH:600000",
                trade_date="20260525",
                snapshot_time="2026-05-25T09:31:03+08:00",
                event_time=datetime(2026, 5, 25, 1, 31, 3, tzinfo=timezone.utc),
                source_run_id="market_data_run_20260525_093000",
                source_adapter="mootdx",
                payload={
                    "subscription_id": 1,
                    "pull_plan_id": 2,
                    "run_id": "market_data_run_20260525_093000",
                    "source_adapter": "mootdx",
                    "data_quality_status": "passed",
                    # snapshot_id intentionally omitted
                },
            )

    def test_n3_event_names_must_not_use_user_prefix(self) -> None:
        with self.assertRaises(EventContractError):
            build_n3_market_event(
                event_type="UserMarketProjectionUpdated",
                asset_kind="stock",
                identity_key="stock:SH:600000",
                trade_date="20260525",
                snapshot_time="2026-05-25T09:31:03+08:00",
                event_time=datetime(2026, 5, 25, 1, 31, 3, tzinfo=timezone.utc),
                source_run_id="market_data_run_20260525_093000",
                source_adapter="mootdx",
                payload=valid_snapshot_payload(),
            )

    def test_valid_n3_event_envelope_contains_required_trace_fields(self) -> None:
        event = build_n3_market_event(
            event_type="MarketSnapshotUpdated",
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260525",
            snapshot_time="2026-05-25T09:31:03+08:00",
            event_time=datetime(2026, 5, 25, 1, 31, 3, tzinfo=timezone.utc),
            source_run_id="market_data_run_20260525_093000",
            source_adapter="mootdx",
            payload=valid_snapshot_payload(),
        )

        self.assertEqual(event.source_layer, "N3_market_data")
        self.assertEqual(event.partition_key, "stock:SH:600000")
        self.assertIn("snapshot_id", event.payload_json)
        self.assertEqual(event.payload_json["data_quality_status"], "passed")

    def test_schema_static_scan_forbidden_runtime_table_names(self) -> None:
        schema_text = Path("sql/008_common_event_infra_schema.sql").read_text(encoding="utf-8")
        forbidden = (
            "stock_minute_bar_1m_runtime",
            "index_minute_bar_1m_runtime",
            "board_minute_bar_1m_runtime",
            "UserMarketProjectionUpdated",
        )
        for token in forbidden:
            self.assertNotIn(token, schema_text)

    def test_check_event_contract_passes(self) -> None:
        result = run_check()
        self.assertTrue(result["passed"], result["findings"])

    def test_outbox_insert_is_transaction_contract_draft_without_commit(self) -> None:
        event = build_n3_market_event(
            event_type="MarketSnapshotUpdated",
            asset_kind="stock",
            identity_key="stock:SH:600000",
            trade_date="20260525",
            snapshot_time="2026-05-25T09:31:03+08:00",
            event_time=datetime(2026, 5, 25, 1, 31, 3, tzinfo=timezone.utc),
            source_run_id="market_data_run_20260525_093000",
            source_adapter="mootdx",
            payload=valid_snapshot_payload(),
        )
        cursor = FakeCursor()

        returned_event_id = insert_outbox_event(cursor, event)

        self.assertEqual(returned_event_id, event.event_id)
        self.assertEqual(cursor.execute_count, 1)
        self.assertIn("INSERT INTO common_event_outbox", cursor.sql)
        self.assertIsInstance(cursor.params[11], Jsonb)
        self.assertNotIn("COMMIT", cursor.sql.upper())
        self.assertNotIn("ROLLBACK", cursor.sql.upper())


def valid_snapshot_payload() -> dict[str, object]:
    return {
        "subscription_id": 1,
        "pull_plan_id": 2,
        "run_id": "market_data_run_20260525_093000",
        "source_adapter": "mootdx",
        "data_quality_status": "passed",
        "snapshot_id": 3,
    }


def valid_minute_bar_closed_v1_payload() -> dict[str, object]:
    return {
        "subscription_id": 11,
        "pull_plan_id": 22,
        "run_id": "today_minute_bar_1m_20260525_until_0931",
        "source_adapter": "mootdx.std.bars",
        "data_quality_status": "passed",
        "minute_bar_id": 202,
    }


def valid_minute_bar_closed_v2_payload() -> dict[str, object]:
    return {
        "subscription_id": 20128,
        "pull_plan_id": 9,
        "run_id": "minute_bar_closed_outbox_20260525__closed_minute_30m_replay_x",
        "source_adapter": "N3Closed30mSummaryAdapter",
        "data_quality_status": "passed",
        "closed_30m_summary_id": 73,
        "summary_id": 73,
        "source_minute_bar_ids": [101, 102],
        "source_minute_refs": [
            {
                "source_kind": "C1",
                "run_id": "today_minute_bar_1m_20260525_until_1411__subscription_x",
                "bar_id": 101,
                "identity_key": "stock:SH:600000",
                "trade_date": "20260525",
                "bar_time": "2026-05-25T09:31:00+08:00",
                "minute_label": "09:31",
            }
        ],
        "c2_run_id": "closed_minute_30m_replay_20260525_until_1500__subscription_x",
        "source_condition_run_id": "condition_layer_20260522_to_20260525_20260525102249_execute",
        "source_subscription_run_id": "market_data_subscription_20260525_condition_layer_x",
        "source_today_minute_run_ids": ["today_minute_bar_1m_20260525_until_1411__subscription_x"],
        "bucket_id": "0931_1000",
        "bucket_start": "2026-05-25T09:31:00+08:00",
        "bucket_end": "2026-05-25T10:00:00+08:00",
        "closed_status": "closed",
        "replay_diff_json": {"source_minute_refs": []},
        "quality_status": "passed",
    }


class FakeCursor:
    def __init__(self) -> None:
        self.sql = ""
        self.params = []
        self.execute_count = 0

    def execute(self, sql: str, params: list[object]) -> None:
        self.sql = sql
        self.params = params
        self.execute_count += 1

    def fetchone(self) -> tuple[str]:
        return (str(self.params[0]),)
