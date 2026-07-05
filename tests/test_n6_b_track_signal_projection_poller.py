import unittest
from datetime import datetime, timezone, timedelta


class FakeBTrackProjectionRepository:
    def __init__(self, *, events=None, open_trade_date=True, existing_event_ids=None):
        self.events = list(events or [])
        self.open_trade_date = open_trade_date
        self.existing_event_ids = set(existing_event_ids or [])
        self.fetch_calls = []
        self.commit_calls = []
        self.committed_events = []

    def is_open_trade_date(self, trade_date):
        return self.open_trade_date

    def fetch_unconsumed_n5_action_events(self, *, trade_date, consumer_name, limit):
        self.fetch_calls.append((trade_date, consumer_name, limit))
        return [
            event
            for event in self.events
            if event["event_id"] not in self.existing_event_ids
            and event["source_layer"] == "N5_action"
            and event["trade_date"] == trade_date
            and event["event_type"] in {"ActionEligible", "ActionExecuted", "ActionBlocked", "ActionSkipped"}
        ][:limit]

    def commit_projection_events(self, *, events, projection_run_id, consumer_name):
        self.commit_calls.append((projection_run_id, consumer_name))
        self.committed_events.extend(events)
        self.existing_event_ids.update(event["event_id"] for event in events)
        return {
            "committed": True,
            "user_projection_run": 1 if events else 0,
            "user_signal_projection": len(events),
            "user_signal_card": len(events),
            "common_event_inbox": len(events),
            "common_event_consumer_checkpoint": 1 if events else 0,
        }


class N6BTrackSignalProjectionPollerTest(unittest.TestCase):
    def test_outside_trading_window_noops_before_fetch(self):
        from run_n6_b_track_signal_projection_poller_once import run_b_track_signal_projection_poller

        repo = FakeBTrackProjectionRepository(events=[n5_event()])

        report = run_b_track_signal_projection_poller(
            repository=repo,
            for_trade_date="20260706",
            now=datetime(2026, 7, 6, 8, 59, tzinfo=timezone(timedelta(hours=8))),
            execute=True,
            user_confirmed=True,
        )

        self.assertEqual(report["result"], "NOOP")
        self.assertEqual(report["reason"], "outside_trading_window")
        self.assertEqual(repo.fetch_calls, [])
        self.assertEqual(repo.commit_calls, [])
        self.assertFalse(report["side_effects"]["writes_database"])

    def test_non_trading_day_noops_before_fetch(self):
        from run_n6_b_track_signal_projection_poller_once import run_b_track_signal_projection_poller

        repo = FakeBTrackProjectionRepository(events=[n5_event()], open_trade_date=False)

        report = run_b_track_signal_projection_poller(
            repository=repo,
            for_trade_date="20260706",
            now=datetime(2026, 7, 6, 9, 30, tzinfo=timezone(timedelta(hours=8))),
            execute=True,
            user_confirmed=True,
        )

        self.assertEqual(report["result"], "NOOP")
        self.assertEqual(report["reason"], "trade_date_not_open")
        self.assertEqual(repo.fetch_calls, [])
        self.assertEqual(repo.commit_calls, [])

    def test_consumes_only_unconsumed_n5_canonical_action_events_for_trade_date(self):
        from run_n6_b_track_signal_projection_poller_once import run_b_track_signal_projection_poller

        repo = FakeBTrackProjectionRepository(
            events=[
                n5_event(event_id="evt_eligible", event_type="ActionEligible"),
                n5_event(event_id="evt_executed", event_type="ActionExecuted"),
                n5_event(event_id="evt_n4", event_type="TriggerMatched", source_layer="N4_trigger"),
                n5_event(event_id="evt_wrong_date", event_type="ActionEligible", trade_date="20260703"),
            ],
            existing_event_ids={"evt_executed"},
        )

        report = run_b_track_signal_projection_poller(
            repository=repo,
            for_trade_date="20260706",
            now=datetime(2026, 7, 6, 9, 30, tzinfo=timezone(timedelta(hours=8))),
            execute=True,
            user_confirmed=True,
            max_events=20,
        )

        self.assertEqual(report["result"], "EXECUTE_PASS")
        self.assertEqual(report["selected_event_count"], 1)
        self.assertEqual([event["event_id"] for event in repo.committed_events], ["evt_eligible"])
        self.assertEqual(repo.fetch_calls, [("20260706", "n6_b_track_signal_projection_poller_v1", 20)])
        self.assertFalse(report["side_effects"]["updates_n5_outbox_status"])
        self.assertFalse(report["side_effects"]["voice_mobile_push"])
        self.assertFalse(report["side_effects"]["real_trade"])

    def test_missing_required_payload_field_fails_closed_without_commit(self):
        from run_n6_b_track_signal_projection_poller_once import run_b_track_signal_projection_poller

        event = n5_event()
        event["payload_json"].pop("direction")
        repo = FakeBTrackProjectionRepository(events=[event])

        report = run_b_track_signal_projection_poller(
            repository=repo,
            for_trade_date="20260706",
            now=datetime(2026, 7, 6, 9, 30, tzinfo=timezone(timedelta(hours=8))),
            execute=True,
            user_confirmed=True,
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("required_payload_field_missing:direction", report["blockers"])
        self.assertEqual(repo.commit_calls, [])

    def test_historical_backfill_requires_explicit_confirm_token(self):
        from run_n6_b_track_signal_projection_poller_once import run_b_track_signal_historical_backfill

        repo = FakeBTrackProjectionRepository(events=[n5_event(trade_date="20260703")])

        report = run_b_track_signal_historical_backfill(
            repository=repo,
            trade_dates=["20260703"],
            execute=True,
            confirm_token="WRONG",
        )

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("invalid_historical_backfill_confirm_token", report["blockers"])
        self.assertEqual(repo.fetch_calls, [])
        self.assertEqual(repo.commit_calls, [])

    def test_historical_backfill_projects_old_trade_dates_without_trading_window_guard(self):
        from run_n6_b_track_signal_projection_poller_once import (
            HISTORICAL_BACKFILL_CONFIRM_TOKEN,
            run_b_track_signal_historical_backfill,
        )

        repo = FakeBTrackProjectionRepository(
            events=[
                n5_event(event_id="evt_20260702", trade_date="20260702"),
                n5_event(event_id="evt_20260703", trade_date="20260703"),
                n5_event(event_id="evt_20260706", trade_date="20260706"),
            ],
            existing_event_ids={"evt_20260702"},
        )

        report = run_b_track_signal_historical_backfill(
            repository=repo,
            trade_dates=["20260702", "20260703"],
            execute=True,
            confirm_token=HISTORICAL_BACKFILL_CONFIRM_TOKEN,
            max_events_per_date=10000,
        )

        self.assertEqual(report["result"], "EXECUTE_PASS")
        self.assertEqual(report["total_selected_event_count"], 1)
        self.assertEqual([event["event_id"] for event in repo.committed_events], ["evt_20260703"])
        self.assertEqual(
            repo.fetch_calls,
            [
                ("20260702", "n6_b_track_signal_projection_poller_v1", 10000),
                ("20260703", "n6_b_track_signal_projection_poller_v1", 10000),
            ],
        )
        self.assertFalse(report["side_effects"]["updates_n5_outbox_status"])
        self.assertFalse(report["side_effects"]["voice_mobile_push"])
        self.assertFalse(report["side_effects"]["real_trade"])
        self.assertTrue(report["side_effects"]["writes_database"])


def n5_event(
    *,
    event_id="evt_eligible",
    event_type="ActionEligible",
    source_layer="N5_action",
    trade_date="20260706",
):
    return {
        "outbox_id": 1,
        "event_id": event_id,
        "event_type": event_type,
        "event_schema_version": "n5_action_event_v1",
        "trade_date": trade_date,
        "asset_kind": "stock",
        "identity_key": "stock:SZ:300139",
        "event_time": "2026-07-06T09:30:00+08:00",
        "source_layer": source_layer,
        "source_run_id": "n5_live_tracking_20260706_0930",
        "dedup_key": f"dedup:{event_id}",
        "partition_key": "stock:SZ:300139",
        "status": "pending",
        "payload_json": {
            "run_id": "n5_live_tracking_20260706_0930",
            "asset_kind": "stock",
            "identity_key": "stock:SZ:300139",
            "direction": "buy",
            "signal_type": "B_BUY",
            "action_state": "eligible",
            "condition_key": "BUY:Q,M,W",
            "original_condition_key": "BUY:Q,M,W",
            "trace_json": {"source": "test"},
        },
    }
