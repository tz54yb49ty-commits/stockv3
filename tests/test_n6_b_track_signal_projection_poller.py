import unittest
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import inspect
import json
import copy
import multiprocessing
import os
from pathlib import Path
import tempfile
from unittest import mock

from ashare_v3.user.projection_plan import (
    N5_PCT_CONTRACT_VERSION,
    N5_PROJECTION_MESSAGE_CONTRACT_HASH,
    N5_PROJECTION_MESSAGE_CONTRACT_VERSION,
)


class FakeBTrackProjectionRepository:
    def __init__(
        self,
        *,
        events=None,
        open_trade_date=True,
        existing_event_ids=None,
        transaction_events=None,
        checkpoint=None,
        transaction_checkpoint=None,
        advisory_acquired=True,
        fail_after_write=False,
    ):
        self.events = list(events or [])
        self.transaction_events = transaction_events
        self.open_trade_date = open_trade_date
        self.existing_event_ids = set(existing_event_ids or [])
        self.checkpoint = checkpoint or absent_checkpoint()
        self.transaction_checkpoint = transaction_checkpoint
        self.advisory_acquired = advisory_acquired
        self.fail_after_write = fail_after_write
        self.fetch_calls = []
        self.commit_calls = []
        self.committed_events = []
        self.skipped_events = []
        self.rollback_count = 0
        self.sql_order = []
        self.table_residue = {
            "user_projection_run": 0,
            "user_signal_projection": 0,
            "user_signal_card": 0,
            "common_event_inbox": 0,
            "common_event_consumer_checkpoint": 0,
        }
        self.staged_table_residue = dict(self.table_residue)

    def is_open_trade_date(self, trade_date):
        return self.open_trade_date

    def fetch_unconsumed_n5_action_events(self, *, trade_date, consumer_name, limit):
        self.fetch_calls.append((trade_date, consumer_name, limit))
        return self._selected_events(trade_date=trade_date, limit=limit)

    def _selected_events(self, *, trade_date, limit):
        return [
            event
            for event in self.events
            if event["event_id"] not in self.existing_event_ids
            and event["source_layer"] == "N5_action"
            and event["trade_date"] == trade_date
            and event["event_type"] in {"ActionEligible", "ActionExecuted", "ActionBlocked", "ActionSkipped"}
        ][:limit]

    def capture_cas_snapshot(self, *, trade_date, consumer_name, limit):
        from run_n6_b_track_signal_projection_poller_once import _cas_snapshot

        events = self.fetch_unconsumed_n5_action_events(
            trade_date=trade_date,
            consumer_name=consumer_name,
            limit=limit,
        )
        return _cas_snapshot(copy.deepcopy(self.checkpoint), copy.deepcopy(events))

    def commit_projection_events(
        self,
        *,
        trade_date,
        max_events,
        projection_run_id,
        consumer_name,
        expected_checkpoint_cas_sha256,
        expected_selected_event_cas_sha256,
        expected_selected_event_count,
    ):
        from run_n6_b_track_signal_projection_poller_once import (
            PollerBlockedError,
            _cas_snapshot,
            _partition_projection_message_events,
        )

        self.commit_calls.append((projection_run_id, consumer_name))
        self.sql_order.append("advisory")
        if not self.advisory_acquired:
            self.rollback_count += 1
            raise PollerBlockedError("postgresql_advisory_lock_not_acquired")
        self.sql_order.append("checkpoint_for_update")
        checkpoint = copy.deepcopy(self.transaction_checkpoint or self.checkpoint)
        self.sql_order.append("event_reread")
        if self.transaction_events is None:
            transaction_events = self._selected_events(trade_date=trade_date, limit=max_events)
        else:
            transaction_events = copy.deepcopy(self.transaction_events[:max_events])
        snapshot = _cas_snapshot(checkpoint, transaction_events)
        if snapshot["checkpoint_cas_sha256"] != expected_checkpoint_cas_sha256:
            self.rollback_count += 1
            raise PollerBlockedError("checkpoint_cas_mismatch")
        if (
            snapshot["selected_event_cas_sha256"] != expected_selected_event_cas_sha256
            or snapshot["selected_event_count"] != expected_selected_event_count
        ):
            self.rollback_count += 1
            raise PollerBlockedError("selected_event_cas_mismatch")
        prepared = _partition_projection_message_events(transaction_events)
        events = list(prepared["projectable_events"])
        skipped_events = list(prepared["skipped_events"])
        selected_events = list(events) + [item["event"] for item in skipped_events]
        self.sql_order.append("writes" if transaction_events else "no_writes")
        staged_counts = {
            "user_projection_run": 1 if events else 0,
            "user_signal_projection": len(events),
            "user_signal_card": len(events),
            "common_event_inbox": len(selected_events),
            "common_event_consumer_checkpoint": 1 if selected_events else 0,
        }
        for family, count in staged_counts.items():
            self.staged_table_residue[family] = count
            if self.fail_after_write == family:
                self.rollback_count += 1
                self.staged_table_residue = {key: 0 for key in self.staged_table_residue}
                raise RuntimeError("fixture_write_failure")
        self.committed_events.extend(events)
        self.skipped_events.extend(skipped_events)
        self.existing_event_ids.update(event["event_id"] for event in selected_events)
        self.table_residue.update(staged_counts)
        return {
            "committed": bool(selected_events),
            "user_projection_run": 1 if events else 0,
            "user_signal_projection": len(events),
            "user_signal_card": len(events),
            "common_event_inbox": len(selected_events),
            "common_event_consumer_checkpoint": 1 if selected_events else 0,
            "skipped_projection_message": len(skipped_events),
            "selected_events": transaction_events,
            "skipped_events": skipped_events,
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
            max_events=1,
        )

        self.assertEqual(report["result"], "EXECUTE_PASS")
        self.assertEqual(report["selected_event_count"], 1)
        self.assertEqual([event["event_id"] for event in repo.committed_events], ["evt_eligible"])
        self.assertEqual(repo.fetch_calls, [("20260706", "n6_b_track_signal_projection_poller_v1", 1)])
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

    def test_invalid_stock_projection_message_is_audited_and_does_not_block_next_ready_message(self):
        from run_n6_b_track_signal_projection_poller_once import run_b_track_signal_projection_poller

        invalid = n5_event(event_id="evt_invalid_not_ready", outbox_id=12, event_time="2026-07-06T09:30:00+08:00")
        invalid["payload_json"]["projection_message_contract_version"] = "invalid-version"
        invalid["payload_json"]["projection_message_contract_hash"] = "invalid-hash"
        invalid["payload_json"]["projection_message_status"] = "not_ready"
        invalid["payload_json"].pop("projection_message_not_ready_reasons")
        invalid["payload_json"]["asset_name"] = None
        invalid["name"] = None
        ready = n5_event(event_id="evt_ready_after_invalid", outbox_id=13, event_time="2026-07-06T09:30:01+08:00")
        repo = FakeBTrackProjectionRepository(events=[invalid, ready])

        report = run_b_track_signal_projection_poller(
            repository=repo,
            for_trade_date="20260706",
            now=datetime(2026, 7, 6, 9, 30, tzinfo=timezone(timedelta(hours=8))),
            execute=True,
            user_confirmed=True,
        )

        self.assertEqual(report["result"], "EXECUTE_PASS")
        self.assertEqual(report["selected_event_count"], 2)
        self.assertEqual(report["projectable_event_count"], 1)
        self.assertEqual([event["event_id"] for event in repo.committed_events], ["evt_ready_after_invalid"])
        self.assertEqual([item["event"]["event_id"] for item in repo.skipped_events], ["evt_invalid_not_ready"])
        reasons = report["projection_message_audit"]["items"][0]["reasons"]
        self.assertIn("projection_message_marker_missing:projection_message_not_ready_reasons", reasons)
        self.assertIn("projection_message_contract_version_mismatch", reasons)
        self.assertIn("projection_message_contract_hash_mismatch", reasons)
        self.assertIn("projection_message_status_not_ready", reasons)
        self.assertIn("projection_message_asset_name_missing", reasons)
        self.assertEqual(report["write_result"]["user_signal_projection"], 1)
        self.assertEqual(report["write_result"]["common_event_inbox"], 2)
        self.assertEqual(report["write_result"]["common_event_consumer_checkpoint"], 1)
        self.assertEqual(len(repo.commit_calls), 1)

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


class N6BTrackDualLockAndCasTest(unittest.TestCase):
    def test_cas_authority_accepts_fixed_windows_consumer_only(self):
        import run_n6_b_track_signal_projection_poller_once as poller

        common = {
            "cas_authority_mode": "internal_one_shot",
            "max_events": poller.MAX_INTERNAL_BATCH_SIZE,
            "expected_checkpoint_cas_sha256": None,
            "expected_selected_event_cas_sha256": None,
            "expected_selected_event_count": None,
        }

        self.assertEqual(
            "",
            poller._validate_cas_authority(
                consumer_name=poller.WINDOWS_N6_CONSUMER_NAME,
                **common,
            ),
        )
        self.assertEqual(
            "invalid_cas_authority",
            poller._validate_cas_authority(
                consumer_name="arbitrary_n6_consumer",
                **common,
            ),
        )

    def test_internal_one_shot_defaults_to_atomic_batch_of_one_hundred(self):
        import run_n6_b_track_signal_projection_poller_once as poller

        events = [n5_event(event_id=f"evt_{index:03d}", outbox_id=index + 1) for index in range(100)]
        repo = FakeBTrackProjectionRepository(events=events)
        report = run_once(repo)

        self.assertEqual(report["result"], "EXECUTE_PASS")
        self.assertEqual(report["selected_event_count"], 100)
        self.assertEqual(repo.fetch_calls, [("20260706", poller.CONSUMER_NAME, 100)])
        self.assertEqual([event["event_id"] for event in repo.committed_events], [f"evt_{index:03d}" for index in range(100)])
        self.assertEqual(
            inspect.signature(poller.run_b_track_signal_projection_poller).parameters["max_events"].default,
            100,
        )
        self.assertEqual(poller.build_parser().get_default("max_events"), 100)

    def test_invalid_internal_batch_bounds_fail_before_repository_singleton_and_reports(self):
        import run_n6_b_track_signal_projection_poller_once as poller

        for invalid_limit in (0, 101):
            with self.subTest(invalid_limit=invalid_limit), mock.patch.object(
                poller, "PostgresBTrackProjectionRepository"
            ) as repository, mock.patch.object(poller, "_write_json") as write_json, mock.patch.object(
                poller, "_append_history"
            ) as append_history:
                report = poller.run_b_track_signal_projection_poller(
                    max_events=invalid_limit,
                    for_trade_date="20260706",
                    now=datetime(2026, 7, 6, 9, 30, tzinfo=timezone(timedelta(hours=8))),
                    execute=True,
                    user_confirmed=True,
                    write_reports=True,
                )
            self.assertEqual((report["result"], report["reason"]), ("BLOCKED", "invalid_cas_authority"))
            repository.assert_not_called()
            write_json.assert_not_called()
            append_history.assert_not_called()

        external_report = poller.run_b_track_signal_projection_poller(
            repository=FakeBTrackProjectionRepository(events=[n5_event()]),
            max_events=2,
            cas_authority_mode="external_bounded_canary",
            expected_checkpoint_cas_sha256="a" * 64,
            expected_selected_event_cas_sha256="b" * 64,
            expected_selected_event_count=1,
            for_trade_date="20260706",
            now=datetime(2026, 7, 6, 9, 30, tzinfo=timezone(timedelta(hours=8))),
            execute=True,
            user_confirmed=True,
        )
        self.assertEqual(
            (external_report["result"], external_report["reason"]),
            ("BLOCKED", "invalid_cas_authority"),
        )

        with temporary_lock_path() as lock_path, mock.patch.object(
            poller, "acquire_singleton_lock"
        ) as singleton, mock.patch.object(
            poller, "PostgresBTrackProjectionRepository"
        ) as repository, mock.patch.object(
            poller, "_write_json"
        ) as write_json, mock.patch.object(
            poller, "_append_history"
        ) as append_history, mock.patch("builtins.print"):
            rc = poller.main(
                [
                    "--singleton-lock-path",
                    str(lock_path),
                    "--max-events",
                    "101",
                    "--execute",
                    "--user-confirmed",
                ]
            )
        self.assertEqual(rc, 2)
        singleton.assert_not_called()
        repository.assert_not_called()
        write_json.assert_not_called()
        append_history.assert_not_called()

    def test_projection_message_uses_hash_frozen_directional_context_fields(self):
        import run_n6_b_track_signal_projection_poller_once as poller

        for asset_kind in ("stock", "index", "board"):
            for direction, expected in (
                ("buy", ("11", "10.000000")),
                ("sell", ("9", "-10.000000")),
            ):
                with self.subTest(asset_kind=asset_kind, direction=direction):
                    row = n5_event()
                    identity_key = {
                        "stock": "stock:SZ:300139",
                        "index": "index:SH:000300",
                        "board": "board:TDX:880001",
                    }[asset_kind]
                    row.update(
                        {
                            "asset_kind": asset_kind,
                            "identity_key": identity_key,
                            "target_price": "999",
                            "expected_return_pct": "999",
                        }
                    )
                    row["payload_json"]["asset_kind"] = asset_kind
                    row["payload_json"]["identity_key"] = identity_key
                    row["payload_json"]["direction"] = direction
                    context = row["payload_json"]["condition_projection_context"]
                    context["asset_kind"] = asset_kind
                    context["identity_key"] = identity_key
                    context_payload = {key: value for key, value in context.items() if key != "context_hash"}
                    context["context_hash"] = hashlib.sha256(
                        json.dumps(
                            context_payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest()

                    event = poller._projection_event_from_row(row)
                    self.assertEqual((event.target_price, event.expected_return_pct), expected)
                    self.assertEqual(event.payload_json, row["payload_json"])

        source = inspect.getsource(poller._select_unconsumed_n5_action_events)
        self.assertIn("condition_projection_context", source)
        self.assertIn("buy_target_price", source)
        self.assertIn("sell_target_price", source)
        self.assertIn("buy_expected_return_pct", source)
        self.assertIn("sell_expected_return_pct", source)

    def test_reviewed_industry_freeze_handles_unique_missing_ambiguous_and_non_stock(self):
        import run_n6_b_track_signal_projection_poller_once as poller

        unique = {
            "trade_date": "20260703",
            "stock_identity_key": "stock:SZ:300139",
            "board_identity_key": "board:TDX:880001",
            "board_code": "880001",
            "board_name": "黄金",
        }
        second = {**unique, "board_identity_key": "board:TDX:880002", "board_code": "880002"}
        expected = {
            "unique": ("ready", "880001", 1, [unique]),
            "missing": ("not_ready", None, 0, []),
            "ambiguous": ("not_ready", None, 2, [unique, second]),
        }
        for name, (status, board_code, count, rows) in expected.items():
            with self.subTest(name=name):
                event = poller._projection_event_from_row(n5_event())
                cur = mock.Mock()
                cur.fetchall.return_value = rows
                memberships = poller._select_reviewed_industry_rows(cur, [event])
                frozen = poller.freeze_stock_industry_context([event], memberships)[0]
                self.assertEqual(frozen.industry_status, status)
                self.assertEqual(frozen.board_code, board_code)
                self.assertEqual(frozen.industry_provenance["distinct_mapping_count"], count)
                sql = cur.execute.call_args.args[0]
                self.assertIn("FROM v_n6_board_membership_fact", sql)
                self.assertIn("board_type = 'tdx_industry'", sql)
                self.assertNotIn("display_cache", sql)

        board_row = n5_event()
        board_row["asset_kind"] = "board"
        board_row["identity_key"] = "board:TDX:880001"
        board_row["payload_json"]["condition_projection_context"]["asset_kind"] = "board"
        board_row["payload_json"]["condition_projection_context"]["identity_key"] = "board:TDX:880001"
        board_event = poller._projection_event_from_row(board_row)
        cur = mock.Mock()
        memberships = poller._select_reviewed_industry_rows(cur, [board_event])
        frozen = poller.freeze_stock_industry_context([board_event], memberships)[0]
        self.assertEqual(frozen.industry_status, "not_applicable")
        cur.execute.assert_not_called()

    def test_inbox_insert_requires_returning_identity(self):
        import run_n6_b_track_signal_projection_poller_once as poller

        event = poller._projection_event_from_row(n5_event())
        cur = mock.Mock()
        cur.fetchone.return_value = {"inbox_id": 1}
        poller._insert_inbox(cur, event, poller.CONSUMER_NAME)
        self.assertIn("RETURNING inbox_id", cur.execute.call_args.args[0])

        conflict = mock.Mock()
        conflict.fetchone.return_value = None
        with self.assertRaisesRegex(poller.PollerBlockedError, "inbox_idempotency_conflict"):
            poller._insert_inbox(conflict, event, poller.CONSUMER_NAME)

    def test_display_contract_preserves_source_context_and_sanitizes_event_specific_fields(self):
        import run_n6_b_track_signal_projection_poller_once as poller

        eligible = poller._projection_event_from_row(n5_event())
        original_context = copy.deepcopy(eligible.payload_json["condition_projection_context"])
        projection_row = {
            "source_payload_json": {"payload_json": copy.deepcopy(eligible.payload_json)},
            "display_payload_json": {
                "condition_projection_context": copy.deepcopy(original_context),
                "action_price": "99",
                "action_pct": "99.000000",
                "action_pct_status": "ready",
                "score": "88",
                "pe_core": "10.5",
            },
        }
        poller._enforce_n6_display_payload_contract(
            projection_row,
            eligible,
            payload_key="display_payload_json",
        )
        self.assertEqual(
            projection_row["display_payload_json"]["condition_projection_context"],
            original_context,
        )
        self.assertEqual(
            (
                projection_row["display_payload_json"]["action_price"],
                projection_row["display_payload_json"]["action_pct"],
                projection_row["display_payload_json"]["action_pct_status"],
            ),
            (None, None, None),
        )
        self.assertEqual(projection_row["source_payload_json"]["payload_json"], eligible.payload_json)
        self.assertEqual(projection_row["display_payload_json"]["score"], "88")
        self.assertEqual(projection_row["display_payload_json"]["pe_core"], "10.5")

        executed = poller._projection_event_from_row(n5_event(event_type="ActionExecuted"))
        card_row = {
            "card_payload_json": {
                "action_price": "10.2",
                "action_pct": "2.000000",
                "action_pct_status": "ready",
            }
        }
        poller._enforce_n6_display_payload_contract(card_row, executed, payload_key="card_payload_json")
        self.assertEqual(card_row["card_payload_json"]["action_price"], "10.2")
        self.assertEqual(card_row["card_payload_json"]["action_pct"], "2.000000")

        non_stock = copy.deepcopy(eligible)
        non_stock.asset_kind = "index"
        index_row = {"display_payload_json": {"score": None, "pe_core": None}}
        poller._enforce_n6_display_payload_contract(
            index_row,
            non_stock,
            payload_key="display_payload_json",
        )
        self.assertNotIn("score", index_row["display_payload_json"])
        self.assertNotIn("pe_core", index_row["display_payload_json"])

    def test_singleton_contention_loser_never_enters_critical_section(self):
        from run_n6_b_track_signal_projection_poller_once import (
            SingletonLockHeldError,
            acquire_singleton_lock,
        )

        with temporary_lock_path() as lock_path:
            loser_calls = []
            with acquire_singleton_lock(
                lock_path,
                expected_path=lock_path,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
            ):
                with self.assertRaises(SingletonLockHeldError):
                    with acquire_singleton_lock(
                        lock_path,
                        expected_path=lock_path,
                        expected_uid=os.getuid(),
                        expected_gid=os.getgid(),
                    ):
                        loser_calls.append("repository_or_report")
            self.assertEqual(loser_calls, [])

    def test_singleton_rejects_symlink_mode_owner_nlink_and_inode_drift(self):
        import run_n6_b_track_signal_projection_poller_once as poller

        with temporary_lock_path() as lock_path:
            lock_path.symlink_to(lock_path.parent / "target")
            with self.assertRaises(poller.SingletonLockContractError):
                poller._acquire_singleton_lock(
                    lock_path,
                    expected_path=lock_path,
                    expected_uid=os.getuid(),
                    expected_gid=os.getgid(),
                    release_id="fixture",
                    source_commit="",
                )
        with temporary_lock_path() as lock_path:
            lock_path.write_text("", encoding="utf-8")
            lock_path.chmod(0o644)
            with self.assertRaises(poller.SingletonLockContractError):
                poller._acquire_singleton_lock(
                    lock_path,
                    expected_path=lock_path,
                    expected_uid=os.getuid(),
                    expected_gid=os.getgid(),
                    release_id="fixture",
                    source_commit="",
                )
        with temporary_lock_path() as lock_path:
            with self.assertRaises(poller.SingletonLockContractError):
                poller._acquire_singleton_lock(
                    lock_path,
                    expected_path=lock_path,
                    expected_uid=os.getuid() + 1,
                    expected_gid=os.getgid(),
                    release_id="fixture",
                    source_commit="",
                )
        with temporary_lock_path() as lock_path:
            lock_path.write_text("", encoding="utf-8")
            lock_path.chmod(0o600)
            os.link(lock_path, lock_path.parent / "second-link")
            with self.assertRaises(poller.SingletonLockContractError):
                poller._acquire_singleton_lock(
                    lock_path,
                    expected_path=lock_path,
                    expected_uid=os.getuid(),
                    expected_gid=os.getgid(),
                    release_id="fixture",
                    source_commit="",
                )
        with temporary_lock_path() as lock_path:
            original = poller._validate_lock_inode

            def inode_drift(fd, parent_fd, name, **kwargs):
                original(fd, parent_fd, name, **kwargs)
                raise poller.SingletonLockContractError("singleton_lock_contract_invalid")

            with mock.patch.object(poller, "_validate_lock_inode", side_effect=inode_drift):
                with self.assertRaises(poller.SingletonLockContractError):
                    poller._acquire_singleton_lock(
                        lock_path,
                        expected_path=lock_path,
                        expected_uid=os.getuid(),
                        expected_gid=os.getgid(),
                        release_id="fixture",
                        source_commit="",
                    )

    def test_two_process_singleton_competition_has_one_winner(self):
        with temporary_lock_path() as lock_path:
            ctx = multiprocessing.get_context("fork")
            ready = ctx.Event()
            release = ctx.Event()
            queue = ctx.Queue()
            winner = ctx.Process(target=_hold_fixture_lock, args=(str(lock_path), ready, release, queue))
            winner.start()
            self.assertTrue(ready.wait(5))
            loser = ctx.Process(target=_try_fixture_lock, args=(str(lock_path), queue))
            loser.start()
            loser.join(5)
            release.set()
            winner.join(5)
            outcomes = sorted([queue.get(timeout=2), queue.get(timeout=2)])
            self.assertEqual(outcomes, ["held", "winner"])
            self.assertEqual(winner.exitcode, 0)
            self.assertEqual(loser.exitcode, 0)

    def test_os_lock_contract_failure_writes_no_report_or_history(self):
        import run_n6_b_track_signal_projection_poller_once as poller

        with temporary_lock_path() as lock_path, mock.patch.object(
            poller, "PostgresBTrackProjectionRepository"
        ) as repository, mock.patch.object(poller, "_write_json") as write_json, mock.patch.object(
            poller, "_append_history"
        ) as append_history, mock.patch("builtins.print"):
            rc = poller.main(["--singleton-lock-path", str(lock_path), "--execute", "--user-confirmed"])
        self.assertEqual(rc, 2)
        repository.assert_not_called()
        write_json.assert_not_called()
        append_history.assert_not_called()

    def test_advisory_lock_failure_rolls_back_before_writes(self):
        repo = FakeBTrackProjectionRepository(events=[n5_event()], advisory_acquired=False)
        report = run_once(repo)
        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["reason"], "postgresql_advisory_lock_not_acquired")
        self.assertEqual(repo.rollback_count, 1)
        self.assertTrue(all(value == 0 for value in repo.table_residue.values()))
        self.assertEqual(repo.sql_order, ["advisory"])

    def test_postgres_repository_uses_frozen_advisory_sql_before_application_tables(self):
        import run_n6_b_track_signal_projection_poller_once as poller

        connection = ScriptedConnection(advisory_acquired=False)
        with mock.patch.object(poller.psycopg, "connect", return_value=connection):
            with self.assertRaisesRegex(poller.PollerBlockedError, "postgresql_advisory_lock_not_acquired"):
                poller.PostgresBTrackProjectionRepository("fixture-only").commit_projection_events(
                    trade_date="20260706",
                    max_events=1,
                    projection_run_id="fixture",
                    consumer_name=poller.CONSUMER_NAME,
                    expected_checkpoint_cas_sha256="a" * 64,
                    expected_selected_event_cas_sha256="b" * 64,
                    expected_selected_event_count=1,
                )
        statements = [" ".join(sql.split()) for sql, _ in connection.cursor_instance.executions]
        self.assertEqual(statements[0], "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        self.assertEqual(statements[1], poller.ADVISORY_LOCK_SQL)
        self.assertEqual(connection.cursor_instance.executions[1][1], (poller.ADVISORY_LOCK_KEY,))
        self.assertFalse(any("common_event_" in sql for sql in statements[:2]))
        self.assertGreaterEqual(connection.rollback_count, 1)

    def test_postgres_repository_rereads_event_before_any_business_write(self):
        import run_n6_b_track_signal_projection_poller_once as poller

        event = n5_event()
        expected = poller._cas_snapshot(absent_checkpoint(), [event])
        connection = ScriptedConnection(advisory_acquired=True, events=[event])
        business_order = []
        with mock.patch.object(poller.psycopg, "connect", return_value=connection), mock.patch.object(
            poller, "_fetch_admin", return_value=None
        ), mock.patch.object(poller, "build_projection_run_row", return_value={}), mock.patch.object(
            poller, "insert_projection_run", side_effect=lambda *args: business_order.append("run")
        ), mock.patch.object(poller, "build_projection_row", return_value={}), mock.patch.object(
            poller, "insert_signal_projection", side_effect=lambda *args: business_order.append("projection") or 1
        ), mock.patch.object(poller, "build_card_row", return_value={}), mock.patch.object(
            poller, "insert_signal_card", side_effect=lambda *args: business_order.append("card")
        ), mock.patch.object(
            poller, "_insert_inbox", side_effect=lambda *args, **kwargs: business_order.append("inbox")
        ), mock.patch.object(
            poller, "_upsert_checkpoint", side_effect=lambda *args: business_order.append("checkpoint")
        ):
            result = poller.PostgresBTrackProjectionRepository("fixture-only").commit_projection_events(
                trade_date="20260706",
                max_events=1,
                projection_run_id="fixture",
                consumer_name=poller.CONSUMER_NAME,
                expected_checkpoint_cas_sha256=expected["checkpoint_cas_sha256"],
                expected_selected_event_cas_sha256=expected["selected_event_cas_sha256"],
                expected_selected_event_count=1,
            )
        statements = [" ".join(sql.split()) for sql, _ in connection.cursor_instance.executions]
        self.assertIn("FOR UPDATE", statements[2])
        self.assertIn("FROM common_event_outbox", statements[3])
        self.assertEqual(business_order, ["run", "projection", "card", "inbox", "checkpoint"])
        self.assertEqual(result["user_signal_projection"], 1)
        self.assertEqual(connection.rollback_count, 0)

    def test_advisory_identity_constants_match_reviewed_derivation(self):
        import run_n6_b_track_signal_projection_poller_once as poller

        digest = hashlib.sha256(poller.ADVISORY_LOCK_KEY_MATERIAL.encode("utf-8")).digest()
        self.assertEqual(digest.hex(), poller.ADVISORY_LOCK_KEY_MATERIAL_SHA256)
        self.assertEqual(int.from_bytes(digest[:8], byteorder="big", signed=True), poller.ADVISORY_LOCK_KEY)
        self.assertEqual(poller.ADVISORY_LOCK_KEY, -8342571444709044287)

    def test_checkpoint_tuple_and_payload_drift_fail_closed(self):
        changed = absent_checkpoint()
        changed["checkpoint_exists"] = True
        changed.update(
            {
                "consumer_name": "n6_b_track_signal_projection_poller_v1",
                "partition_key": "N5_action",
                "source_layer": "N5_action",
                "last_event_time": "2026-07-06T09:29:00+08:00",
                "last_outbox_id": 99,
                "last_event_id": "drift",
                "checkpoint_payload_sha256": "a" * 64,
                "updated_at": "2026-07-06T09:29:01+08:00",
            }
        )
        repo = FakeBTrackProjectionRepository(
            events=[n5_event()],
            transaction_checkpoint=changed,
        )
        report = run_once(repo)
        self.assertEqual((report["result"], report["reason"]), ("BLOCKED", "checkpoint_cas_mismatch"))
        self.assertEqual(repo.rollback_count, 1)
        self.assertTrue(all(value == 0 for value in repo.table_residue.values()))

    def test_selected_event_all_frozen_fields_and_count_drift_fail_closed(self):
        base = n5_event()
        mutations = {
            "event_time": lambda row: row.__setitem__("event_time", "2026-07-06T09:30:01+08:00"),
            "outbox_id": lambda row: row.__setitem__("outbox_id", 2),
            "event_id": lambda row: row.__setitem__("event_id", "evt_drift"),
            "payload_digest": lambda row: row["payload_json"].__setitem__("trigger_pct", "2.000000"),
            "envelope": lambda row: row.__setitem__("dedup_key", "dedup:drift"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(base)
                mutate(changed)
                repo = FakeBTrackProjectionRepository(events=[base], transaction_events=[changed])
                report = run_once(repo)
                self.assertEqual((report["result"], report["reason"]), ("BLOCKED", "selected_event_cas_mismatch"))
                self.assertTrue(all(value == 0 for value in repo.table_residue.values()))
        repo = FakeBTrackProjectionRepository(events=[base], transaction_events=[])
        report = run_once(repo)
        self.assertEqual((report["result"], report["reason"]), ("BLOCKED", "selected_event_cas_mismatch"))

    def test_one_event_drift_in_hundred_event_batch_rolls_back_entire_batch(self):
        base = [n5_event(event_id=f"evt_{index:03d}", outbox_id=index + 1) for index in range(100)]
        changed = copy.deepcopy(base)
        changed[-1]["payload_json"]["trigger_pct"] = "9.999999"
        repo = FakeBTrackProjectionRepository(events=base, transaction_events=changed)

        report = run_once(repo)

        self.assertEqual((report["result"], report["reason"]), ("BLOCKED", "selected_event_cas_mismatch"))
        self.assertEqual(repo.rollback_count, 1)
        self.assertTrue(all(value == 0 for value in repo.table_residue.values()))

    def test_inbox_idempotency_conflict_rolls_back_before_checkpoint(self):
        import run_n6_b_track_signal_projection_poller_once as poller

        event = n5_event()
        expected = poller._cas_snapshot(absent_checkpoint(), [event])
        connection = ScriptedConnection(advisory_acquired=True, events=[event])
        with mock.patch.object(poller.psycopg, "connect", return_value=connection), mock.patch.object(
            poller, "_fetch_admin", return_value=None
        ), mock.patch.object(poller, "build_projection_run_row", return_value={}), mock.patch.object(
            poller, "insert_projection_run"
        ), mock.patch.object(
            poller, "build_projection_row", return_value={"display_payload_json": {}}
        ), mock.patch.object(
            poller, "insert_signal_projection", return_value=1
        ), mock.patch.object(
            poller, "build_card_row", return_value={"card_payload_json": {}}
        ), mock.patch.object(
            poller, "insert_signal_card"
        ), mock.patch.object(
            poller,
            "_insert_inbox",
            side_effect=poller.PollerBlockedError("inbox_idempotency_conflict"),
        ), mock.patch.object(poller, "_upsert_checkpoint") as checkpoint:
            with self.assertRaisesRegex(poller.PollerBlockedError, "inbox_idempotency_conflict"):
                poller.PostgresBTrackProjectionRepository("fixture-only").commit_projection_events(
                    trade_date="20260706",
                    max_events=100,
                    projection_run_id="fixture",
                    consumer_name=poller.CONSUMER_NAME,
                    expected_checkpoint_cas_sha256=expected["checkpoint_cas_sha256"],
                    expected_selected_event_cas_sha256=expected["selected_event_cas_sha256"],
                    expected_selected_event_count=1,
                )
        self.assertGreaterEqual(connection.rollback_count, 1)
        checkpoint.assert_not_called()

    def test_external_bounded_canary_requires_exact_three_part_authority(self):
        repo = FakeBTrackProjectionRepository(events=[n5_event()])
        report = run_once(repo, cas_authority_mode="external_bounded_canary", max_events=1)
        self.assertEqual(report["reason"], "external_bounded_canary_cas_authority_missing")
        self.assertEqual(repo.fetch_calls, [])
        snapshot = repo.capture_cas_snapshot(
            trade_date="20260706",
            consumer_name="n6_b_track_signal_projection_poller_v1",
            limit=1,
        )
        report = run_once(
            repo,
            cas_authority_mode="external_bounded_canary",
            max_events=1,
            expected_checkpoint_cas_sha256=snapshot["checkpoint_cas_sha256"],
            expected_selected_event_cas_sha256=snapshot["selected_event_cas_sha256"],
            expected_selected_event_count=1,
        )
        self.assertEqual(report["result"], "EXECUTE_PASS")

    def test_noop_acquires_transaction_locks_but_has_zero_writes(self):
        repo = FakeBTrackProjectionRepository(events=[])
        report = run_once(repo)
        self.assertEqual((report["result"], report["reason"]), ("NOOP", "no_unconsumed_n5_action_events"))
        self.assertEqual(repo.sql_order, ["advisory", "checkpoint_for_update", "event_reread", "no_writes"])
        self.assertTrue(all(value == 0 for value in repo.table_residue.values()))
        self.assertFalse(report["side_effects"]["writes_database"])

    def test_write_exception_rolls_back_all_five_write_families(self):
        for family in (
            "user_projection_run",
            "user_signal_projection",
            "user_signal_card",
            "common_event_inbox",
            "common_event_consumer_checkpoint",
        ):
            with self.subTest(family=family):
                repo = FakeBTrackProjectionRepository(events=[n5_event()], fail_after_write=family)
                with self.assertRaisesRegex(RuntimeError, "fixture_write_failure"):
                    run_once(repo)
                self.assertEqual(repo.rollback_count, 1)
                self.assertTrue(all(value == 0 for value in repo.table_residue.values()))
                self.assertTrue(all(value == 0 for value in repo.staged_table_residue.values()))

    def test_sql_order_and_forbidden_source_patterns(self):
        repo = FakeBTrackProjectionRepository(events=[n5_event()])
        report = run_once(repo)
        self.assertEqual(report["result"], "EXECUTE_PASS")
        self.assertEqual(repo.sql_order, ["advisory", "checkpoint_for_update", "event_reread", "writes"])
        source = (Path(__file__).parents[1] / "scripts/run_n6_b_track_signal_projection_poller_once.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("UPDATE common_event_outbox", source)
        self.assertNotIn("pg_advisory_lock(", source)
        self.assertNotIn("hashtext(", source)
        self.assertNotIn("hashtextextended(", source)
        self.assertIn("SELECT pg_try_advisory_xact_lock(%s::bigint) AS acquired", source)
        transaction_block = source[source.index("def commit_projection_events"):source.index("def run_b_track_signal_projection_poller")]
        self.assertLess(
            transaction_block.index("cur.execute(ADVISORY_LOCK_SQL"),
            transaction_block.index("_select_checkpoint_cas(cur"),
        )

    def test_checkpoint_payload_shape_remains_exactly_two_keys(self):
        source = (Path(__file__).parents[1] / "scripts/run_n6_b_track_signal_projection_poller_once.py").read_text(
            encoding="utf-8"
        )
        checkpoint_block = source[source.index("def _upsert_checkpoint"):source.index("def _projection_run_id")]
        self.assertIn('"event_count": len(events)', checkpoint_block)
        self.assertIn('"projection_policy": "n6_b_track_signal_projection"', checkpoint_block)
        self.assertNotIn("projected_event_count", checkpoint_block)
        self.assertNotIn("skipped_event_count", checkpoint_block)


@contextmanager
def temporary_lock_path():
    with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
        parent = Path(directory)
        parent.chmod(0o700)
        yield parent / "poller.lock"


def _hold_fixture_lock(path, ready, release, queue):
    from run_n6_b_track_signal_projection_poller_once import acquire_singleton_lock

    lock_path = Path(path)
    with acquire_singleton_lock(
        lock_path,
        expected_path=lock_path,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    ):
        queue.put("winner")
        ready.set()
        release.wait(5)


def _try_fixture_lock(path, queue):
    from run_n6_b_track_signal_projection_poller_once import (
        SingletonLockHeldError,
        acquire_singleton_lock,
    )

    lock_path = Path(path)
    try:
        with acquire_singleton_lock(
            lock_path,
            expected_path=lock_path,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
        ):
            queue.put("unexpected_winner")
    except SingletonLockHeldError:
        queue.put("held")


def run_once(repo, **overrides):
    from run_n6_b_track_signal_projection_poller_once import run_b_track_signal_projection_poller

    kwargs = {
        "repository": repo,
        "for_trade_date": "20260706",
        "now": datetime(2026, 7, 6, 9, 30, tzinfo=timezone(timedelta(hours=8))),
        "execute": True,
        "user_confirmed": True,
    }
    kwargs.update(overrides)
    return run_b_track_signal_projection_poller(**kwargs)


class ScriptedCursor:
    def __init__(self, *, advisory_acquired):
        self.advisory_acquired = advisory_acquired
        self.executions = []
        self.next_row = None
        self.next_rows = []
        self.events = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=None):
        self.executions.append((sql, params))
        if "pg_try_advisory_xact_lock" in sql:
            self.next_row = {"acquired": self.advisory_acquired}
        elif "FROM common_event_consumer_checkpoint" in sql:
            self.next_row = None
        elif "FROM common_event_outbox" in sql:
            self.next_rows = copy.deepcopy(self.events)

    def fetchone(self):
        row = self.next_row
        self.next_row = None
        return row

    def fetchall(self):
        rows = self.next_rows
        self.next_rows = []
        return rows


class ScriptedTransaction:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is not None:
            self.connection.rollback_count += 1
        return False


class ScriptedConnection:
    def __init__(self, *, advisory_acquired, events=None):
        self.cursor_instance = ScriptedCursor(advisory_acquired=advisory_acquired)
        self.cursor_instance.events = list(events or [])
        self.rollback_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.cursor_instance

    def transaction(self):
        return ScriptedTransaction(self)

    def rollback(self):
        self.rollback_count += 1


def absent_checkpoint():
    return {
        "checkpoint_exists": False,
        "consumer_name": None,
        "partition_key": None,
        "source_layer": None,
        "last_event_time": None,
        "last_outbox_id": None,
        "last_event_id": None,
        "checkpoint_payload_sha256": None,
        "updated_at": None,
    }


def n5_event(
    *,
    event_id="evt_eligible",
    event_type="ActionEligible",
    source_layer="N5_action",
    trade_date="20260706",
    outbox_id=1,
    event_time="2026-07-06T09:30:00+08:00",
):
    context_payload = {
        "contract_version": "N2-condition-projection-context-v1",
        "source_layer": "N2_condition",
        "asset_kind": "stock",
        "identity_key": "stock:SZ:300139",
        "source_trade_date": "20260703",
        "for_trade_date": trade_date,
        "status": "ready",
        "fields": {
            "name": "晓程科技",
            "close": "10",
            "up_reference_period": "W",
            "buy_target_price": "11",
            "buy_expected_return_pct": "10.000000",
            "down_reference_period": "M",
            "sell_target_price": "9",
            "sell_expected_return_pct": "-10.000000",
            "clear_sell_ref_period": "W",
            "up_secondary_target_price": None,
            "up_secondary_expected_return_pct": None,
            "score": "88",
            "pe_core": "10.5",
        },
        "nullable_fields": ["up_secondary_target_price", "up_secondary_expected_return_pct"],
        "not_ready_reasons": [],
    }
    context = {
        **context_payload,
        "context_hash": hashlib.sha256(
            json.dumps(
                context_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }
    payload = {
        "run_id": "n5_live_tracking_20260706_0930",
        "asset_kind": "stock",
        "identity_key": "stock:SZ:300139",
        "direction": "buy",
        "signal_type": "B_BUY",
        "action_state": "eligible",
        "condition_key": "BUY:Q,M,W",
        "original_condition_key": "BUY:Q,M,W",
        "trace_json": {"source": "test"},
        "pct_contract_version": N5_PCT_CONTRACT_VERSION,
        "condition_projection_context": context,
        "condition_projection_context_status": "ready",
        "condition_projection_context_trace": {
            "status": "ready",
            "source_context_hash": context["context_hash"],
        },
        "trigger_price": "10",
        "trigger_pct": "1.000000",
        "trigger_pct_status": "ready",
        "asset_code": "300139",
        "asset_name": "晓程科技",
        "projection_message_contract_version": N5_PROJECTION_MESSAGE_CONTRACT_VERSION,
        "projection_message_contract_hash": N5_PROJECTION_MESSAGE_CONTRACT_HASH,
        "projection_message_status": "ready",
        "projection_message_not_ready_reasons": [],
    }
    if event_type == "ActionExecuted":
        payload.update(
            {
                "action_state": "executed",
                "action_price": "10.2",
                "action_pct": "2.000000",
                "action_pct_status": "ready",
            }
        )
    return {
        "outbox_id": outbox_id,
        "event_id": event_id,
        "event_type": event_type,
        "event_schema_version": "n5_action_event_v1",
        "trade_date": trade_date,
        "asset_kind": "stock",
        "identity_key": "stock:SZ:300139",
        "event_time": event_time,
        "source_layer": source_layer,
        "source_run_id": "n5_live_tracking_20260706_0930",
        "dedup_key": f"dedup:{event_id}",
        "partition_key": "stock:SZ:300139",
        "status": "pending",
        "payload_json": payload,
        "name": "晓程科技",
    }
