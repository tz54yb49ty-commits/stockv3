import hashlib
import inspect
import json
import unittest

from ashare_v3.user.projection_plan import (
    CANONICAL_EVENT_TYPES,
    EXPECTED_N5_OUTBOX_COUNTS,
    IndustryMembershipRow,
    LEGACY_EXPECTED_N5_OUTBOX_COUNTS,
    LEGACY_EVENT_TYPES,
    N5_PROJECTION_MESSAGE_CONTRACT_HASH,
    N5_PROJECTION_MESSAGE_CONTRACT_VERSION,
    N6_INDUSTRY_READ_ROLE,
    N6_INDUSTRY_SOURCE_RELATION,
    AdminUser,
    FilterProfile,
    PostgresProjectionPlanRepository,
    ProjectionEvent,
    ProjectionInputSnapshot,
    build_parser,
    evaluate_projection_message_contract,
    freeze_stock_industry_context,
    parse_expected_n5_outbox_counts,
    run_projection_dry_run,
)
from ashare_v3.user.projection_plan import USER_MESSAGE_EVENT_TYPES
from ashare_v3.user.stale_active_lineage import (
    HINT_30M_STALE_SOURCE_ACTION_RUN_IDS,
    N2_D_ANCHOR_STALE_SOURCE_ACTION_RUN_IDS,
)


class FakeProjectionRepository:
    def __init__(self, snapshot: ProjectionInputSnapshot) -> None:
        self.snapshot = snapshot
        self.fetch_calls = 0

    def fetch_input_snapshot(self) -> ProjectionInputSnapshot:
        self.fetch_calls += 1
        return self.snapshot


class N6ProjectionPlanTest(unittest.TestCase):
    def test_parser_accepts_json_and_rejects_execute_in_runner_logic(self) -> None:
        parser = build_parser()
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }

        self.assertIn("--json", option_strings)
        self.assertIn("--execute", option_strings)
        self.assertIn("--expected-n5-outbox-count", option_strings)

    def test_parse_explicit_expected_counts_for_gate(self) -> None:
        parsed = parse_expected_n5_outbox_counts(["ActionExecuted:pending=4", "ActionBlocked:pending=1"])

        self.assertEqual(parsed, {"ActionExecuted:pending": 4, "ActionBlocked:pending": 1})

    def test_execute_flag_blocks_before_repository_read(self) -> None:
        repo = FakeProjectionRepository(default_snapshot())

        report = run_projection_dry_run(repository=repo, execute=True)

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("execute_flag_not_allowed", report["blockers"])
        self.assertEqual(report["quality"]["p0_count"], 1)
        self.assertEqual(repo.fetch_calls, 0)
        self.assertFalse(report["side_effects"]["writes_database"])
        self.assertFalse(report["side_effects"]["n5_outbox_consumed"])

    def test_stale_hint_30m_source_action_run_blocks_projection_plan(self) -> None:
        stale_run_id = HINT_30M_STALE_SOURCE_ACTION_RUN_IDS[0]
        repo = FakeProjectionRepository(default_snapshot())

        report = run_projection_dry_run(repository=repo, source_action_run_id=stale_run_id)

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("stale_source_action_run_id", report["blockers"])
        self.assertEqual(report["quality"]["p0_count"], 1)
        self.assertFalse(report["side_effects"]["writes_database"])
        self.assertFalse(report["side_effects"]["n5_outbox_consumed"])

    def test_superseded_20260617_source_action_run_blocks_projection_plan(self) -> None:
        stale_run_id = N2_D_ANCHOR_STALE_SOURCE_ACTION_RUN_IDS[0]
        repo = FakeProjectionRepository(default_snapshot())

        report = run_projection_dry_run(repository=repo, source_action_run_id=stale_run_id)

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("stale_source_action_run_id", report["blockers"])
        self.assertEqual(report["quality"]["p0_count"], 1)
        self.assertFalse(report["side_effects"]["writes_database"])
        self.assertFalse(report["side_effects"]["n5_outbox_consumed"])

    def test_canonical_action_blocked_builds_blocked_card_and_queued_notification_plan(self) -> None:
        repo = FakeProjectionRepository(default_snapshot())

        report = run_projection_dry_run(repository=repo)

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(report["planned_row_counts"]["user_projection_run"], 1)
        self.assertEqual(report["planned_row_counts"]["user_signal_projection"], 2)
        self.assertEqual(report["planned_row_counts"]["user_signal_card"], 2)
        self.assertEqual(report["planned_row_counts"]["user_notification_queue"], 2)
        self.assertEqual(report["planned_row_counts"]["user_signal_decision"], 0)
        self.assertEqual(report["planned_row_counts"]["user_sim_rows"], 0)
        self.assertEqual(report["notification_plan_summary"]["queue_status_counts"], {"queued_only": 2})
        self.assertEqual(report["notification_plan_summary"]["notification_source_counts"], {"n5_action_blocked": 2})
        self.assertTrue(report["notification_plan_summary"]["queued_only_passed"])
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertEqual(report["missing_fields_summary"]["current_price_missing"], 2)
        self.assertEqual(report["event_summary"]["by_event_type"], {"ActionBlocked": 2})
        self.assertEqual(report["sample_plans"][0]["projection"]["user_id"], 1)
        self.assertEqual(report["sample_plans"][0]["projection"]["user_filter_profile_id"], 1)
        self.assertEqual(report["sample_plans"][0]["projection"]["source_action_event_id"], "evt_blocked_buy")
        self.assertEqual(report["sample_plans"][0]["projection"]["source_action_event_type"], "ActionBlocked")
        self.assertEqual(report["sample_plans"][0]["projection"]["action_state"], "blocked")
        self.assertEqual(report["sample_plans"][0]["card"]["card_type"], "blocked")
        self.assertEqual(report["sample_plans"][0]["card"]["card_status"], "blocked")
        self.assertFalse(report["sample_plans"][0]["card"]["decision_buttons"])
        self.assertFalse(report["sample_plans"][0]["notification"]["actual_push"])
        self.assertFalse(report["side_effects"]["writes_database"])
        self.assertFalse(report["side_effects"]["updates_n5_outbox_status"])
        self.assertFalse(report["side_effects"]["voice_mobile_push"])
        self.assertFalse(report["input_boundary"]["n4_n3_n2_naked_fact_substitution"])

    def test_missing_direction_is_p0(self) -> None:
        snapshot = default_snapshot()
        snapshot.events[0].payload_json.pop("direction")
        repo = FakeProjectionRepository(snapshot)

        report = run_projection_dry_run(repository=repo)

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("required_payload_field_missing:direction", report["blockers"])
        self.assertGreaterEqual(report["quality"]["p0_count"], 1)

    def test_missing_source_event_id_is_p0(self) -> None:
        snapshot = default_snapshot()
        snapshot.events[0].event_id = ""
        repo = FakeProjectionRepository(snapshot)

        report = run_projection_dry_run(repository=repo)

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("required_event_envelope_missing:event_id", report["blockers"])
        self.assertGreaterEqual(report["quality"]["p0_count"], 1)

    def test_missing_display_basis_is_p1_warning_not_p0(self) -> None:
        snapshot = default_snapshot()
        snapshot.events[0].display_basis_id = None
        snapshot.events[0].code = None
        snapshot.events[0].name = None
        repo = FakeProjectionRepository(snapshot)

        report = run_projection_dry_run(repository=repo)

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertNotIn("code_or_name_unfillable_from_n2_display_basis", report["blockers"])
        self.assertIn("display_basis_missing", report["warnings"])
        self.assertEqual(report["missing_fields_summary"]["display_basis_missing"], 2)
        self.assertEqual(report["quality"]["p0_count"], 0)

    def test_admin_missing_is_p0(self) -> None:
        snapshot = default_snapshot(admin=None, default_profile=None)
        repo = FakeProjectionRepository(snapshot)

        report = run_projection_dry_run(repository=repo)

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_active_admin", report["blockers"])
        self.assertIn("missing_default_admin_filter_profile", report["blockers"])

    def test_outbox_count_mismatch_is_p0(self) -> None:
        snapshot = default_snapshot()
        snapshot.n5_outbox_counts = {"ActionBlocked:pending": 1}
        repo = FakeProjectionRepository(snapshot)

        report = run_projection_dry_run(repository=repo)

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("n5_outbox_count_mismatch_without_new_gate", report["blockers"])

    def test_explicit_20260602_action_confirmation_baseline_passes_dry_run(self) -> None:
        expected = {"ActionExecuted:pending": 4, "ActionBlocked:pending": 1}
        snapshot = default_snapshot(
            n5_outbox_counts=expected,
            events=[
                projection_event(
                    event_id="evt_executed_1",
                    event_type="ActionExecuted",
                    direction="sell",
                    signal_type="S_SELL",
                    action_mark="30m_shrink",
                ),
                projection_event(
                    event_id="evt_executed_2",
                    event_type="ActionExecuted",
                    direction="sell",
                    signal_type="S_SELL",
                    action_mark="30m_shrink",
                ),
                projection_event(
                    event_id="evt_executed_3",
                    event_type="ActionExecuted",
                    direction="sell",
                    signal_type="S_SELL",
                    action_mark="30m_shrink",
                ),
                projection_event(
                    event_id="evt_executed_4",
                    event_type="ActionExecuted",
                    direction="sell",
                    signal_type="S_SELL",
                    action_mark="30m_shrink",
                ),
                projection_event(event_id="evt_blocked_1", event_type="ActionBlocked", direction="buy", signal_type="B_BUY"),
            ],
        )
        repo = FakeProjectionRepository(snapshot)

        report = run_projection_dry_run(repository=repo, expected_n5_outbox_counts=expected)

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(report["quality"]["p0_count"], 0)
        self.assertEqual(report["input_state"]["n5_outbox_expected_source"], "explicit_gate")
        self.assertEqual(report["event_summary"]["by_event_type"], {"ActionBlocked": 1, "ActionExecuted": 4})
        self.assertEqual(report["planned_row_counts"]["user_projection_run"], 1)
        self.assertEqual(report["planned_row_counts"]["user_signal_projection"], 5)
        self.assertEqual(report["planned_row_counts"]["user_signal_card"], 5)
        self.assertEqual(report["planned_row_counts"]["user_notification_queue"], 5)
        self.assertEqual(report["planned_row_counts"]["user_signal_decision"], 0)
        self.assertEqual(report["planned_row_counts"]["user_sim_rows"], 0)
        self.assertEqual(
            report["notification_plan_summary"]["notification_source_counts"],
            {"n5_action_blocked": 1, "n5_action_executed": 4},
        )
        self.assertEqual(report["notification_plan_summary"]["queue_status_counts"], {"queued_only": 5})
        executed_sample = next(row for row in report["sample_plans"] if row["source_event_id"] == "evt_executed_1")
        self.assertEqual(executed_sample["card"]["card_status"], "action_confirmed")
        self.assertEqual(executed_sample["notification"]["notification_source"], "n5_action_executed")
        self.assertEqual(executed_sample["notification"]["queue_status"], "queued_only")
        self.assertFalse(executed_sample["notification"]["actual_push"])
        self.assertFalse(executed_sample["card"]["sim_allowed"])
        self.assertFalse(executed_sample["card"]["real_trade_allowed"])

    def test_user_message_filter_excludes_action_blocked_from_ordinary_projection(self) -> None:
        expected = {"ActionBlocked:pending": 836}
        snapshot = default_snapshot(
            n5_outbox_counts=expected,
            events=[
                projection_event(event_id=f"evt_blocked_{idx}", event_type="ActionBlocked", direction="buy", signal_type="B_BUY")
                for idx in range(3)
            ],
        )
        repo = FakeProjectionRepository(snapshot)

        report = run_projection_dry_run(
            repository=repo,
            expected_n5_outbox_counts=expected,
            user_message_event_filter=USER_MESSAGE_EVENT_TYPES,
        )

        self.assertEqual(report["result"], "PROJECTION_PASS_ZERO_USER_MESSAGES")
        self.assertEqual(report["event_summary"]["input_event_count"], 3)
        self.assertEqual(report["user_message_summary"]["eligible_user_message_count"], 0)
        self.assertEqual(report["user_message_summary"]["diagnosis_only_count"], 3)
        self.assertEqual(report["planned_row_counts"]["user_projection_run"], 1)
        self.assertEqual(report["planned_row_counts"]["user_signal_projection"], 0)
        self.assertEqual(report["planned_row_counts"]["user_signal_card"], 0)
        self.assertEqual(report["planned_row_counts"]["user_notification_queue"], 0)
        self.assertEqual(report["sample_plans"], [])

    def test_user_message_filter_projects_action_eligible_and_executed_only(self) -> None:
        expected = {"ActionEligible:pending": 1, "ActionExecuted:pending": 1, "ActionBlocked:pending": 1, "ActionSkipped:pending": 1}
        snapshot = default_snapshot(
            n5_outbox_counts=expected,
            events=[
                projection_event(event_id="evt_eligible", event_type="ActionEligible", direction="buy", signal_type="B_BUY"),
                projection_event(event_id="evt_executed", event_type="ActionExecuted", direction="sell", signal_type="S_SELL"),
                projection_event(event_id="evt_blocked", event_type="ActionBlocked", direction="buy", signal_type="B_BUY"),
                projection_event(event_id="evt_skipped", event_type="ActionSkipped", direction="sell", signal_type="S_SELL"),
            ],
        )
        repo = FakeProjectionRepository(snapshot)

        report = run_projection_dry_run(
            repository=repo,
            expected_n5_outbox_counts=expected,
            user_message_event_filter=USER_MESSAGE_EVENT_TYPES,
        )

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(report["user_message_summary"]["eligible_user_message_count"], 2)
        self.assertEqual(report["user_message_summary"]["diagnosis_only_count"], 2)
        self.assertEqual(report["planned_row_counts"]["user_projection_run"], 1)
        self.assertEqual(report["planned_row_counts"]["user_signal_projection"], 2)
        self.assertEqual(report["planned_row_counts"]["user_signal_card"], 2)
        self.assertEqual(report["planned_row_counts"]["user_notification_queue"], 2)
        self.assertEqual(
            [row["source_event_id"] for row in report["sample_plans"]],
            ["evt_eligible", "evt_executed"],
        )

    def test_missing_user_message_filter_blocks(self) -> None:
        repo = FakeProjectionRepository(default_snapshot())

        report = run_projection_dry_run(repository=repo, user_message_event_filter=[])

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("missing_user_message_event_filter", report["blockers"])

    def test_unknown_user_message_filter_blocks(self) -> None:
        repo = FakeProjectionRepository(default_snapshot())

        report = run_projection_dry_run(repository=repo, user_message_event_filter=["ActionFoo"])

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("unsupported_user_message_event_filter", report["blockers"])

    def test_projection_message_contract_projects_n5_payload_without_recalculation(self) -> None:
        events: list[ProjectionEvent] = []
        for asset_kind in ("stock", "index", "board"):
            for event_type in ("ActionEligible", "ActionExecuted"):
                event = projection_event(
                    event_id=f"evt_{asset_kind}_{event_type}",
                    event_type=event_type,
                    direction="buy",
                    signal_type="B_BUY",
                    action_mark="normal" if event_type == "ActionExecuted" else None,
                )
                set_event_asset(event, asset_kind)
                add_projection_message_contract(event)
                events.append(event)
        events = freeze_stock_industry_context(
            events,
            [industry_membership_row("stock:SH:600000", "board:TDX:880001", "880001", "银行")],
        )
        expected = {"ActionEligible:pending": 3, "ActionExecuted:pending": 3}

        report = run_projection_dry_run(
            repository=FakeProjectionRepository(default_snapshot(n5_outbox_counts=expected, events=events)),
            expected_n5_outbox_counts=expected,
            user_message_event_filter=["ActionEligible", "ActionExecuted"],
        )

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(report["planned_row_counts"]["user_signal_projection"], 6)
        samples = {sample["source_event_id"]: sample for sample in report["sample_plans"]}
        for event in events:
            for output in (samples[event.event_id]["projection"], samples[event.event_id]["card"]):
                self.assertEqual(output["condition_projection_context"], event.payload_json["condition_projection_context"])
                self.assertEqual(output["projection_message_contract_hash"], N5_PROJECTION_MESSAGE_CONTRACT_HASH)
                self.assertEqual(output["trigger_pct"], "999.123456")
                self.assertEqual(output["code"], event.payload_json["asset_code"])
                self.assertEqual(output["name"], event.payload_json["asset_name"])
                if event.event_type == "ActionExecuted":
                    self.assertEqual(output["action_pct"], "888.654321")
                else:
                    self.assertIsNone(output["action_price"])
                    self.assertIsNone(output["action_pct"])
            expected_industry_status = "ready" if event.asset_kind == "stock" else "not_applicable"
            self.assertEqual(samples[event.event_id]["card"]["industry_status"], expected_industry_status)

    def test_projection_message_tamper_is_event_scoped(self) -> None:
        valid = projection_event(event_id="evt_message_ready", event_type="ActionEligible", direction="buy", signal_type="B_BUY")
        invalid = projection_event(event_id="evt_message_tampered", event_type="ActionEligible", direction="sell", signal_type="S_SELL")
        add_projection_message_contract(valid)
        add_projection_message_contract(invalid)
        invalid.payload_json["projection_message_contract_hash"] = "tampered"
        expected = {"ActionEligible:pending": 2}

        report = run_projection_dry_run(
            repository=FakeProjectionRepository(default_snapshot(n5_outbox_counts=expected, events=[valid, invalid])),
            expected_n5_outbox_counts=expected,
            user_message_event_filter=["ActionEligible"],
        )

        self.assertEqual(report["result"], "DRY_RUN_PASS_WITH_EVENT_P0_SKIPS")
        self.assertEqual(report["planned_row_counts"]["user_signal_projection"], 1)
        self.assertEqual(report["event_projection_quality"]["skipped_event_count"], 1)
        reasons = report["event_projection_quality"]["items"][0]["details"]["reasons"]
        self.assertIn("projection_message_contract_hash_mismatch", reasons)

    def test_projection_message_marker_version_status_and_pct_fail_closed(self) -> None:
        mutations = {
            "projection_message_contract_version_mismatch": (
                "projection_message_contract_version",
                "wrong-version",
            ),
            "projection_message_status_not_ready": ("projection_message_status", "not_ready"),
            "trigger_pct_format_invalid": ("trigger_pct", "1.2"),
        }
        for expected_reason, (field, value) in mutations.items():
            event = projection_event(
                event_id=f"evt_{expected_reason}",
                event_type="ActionEligible",
                direction="buy",
                signal_type="B_BUY",
            )
            add_projection_message_contract(event)
            event.payload_json[field] = value

            evaluation = evaluate_projection_message_contract(event)

            self.assertFalse(evaluation["projectable"], expected_reason)
            self.assertIn(expected_reason, evaluation["reasons"])

    def test_stock_industry_freeze_uses_exact_distinct_view_mapping(self) -> None:
        ready = projection_event(event_id="evt_industry_ready", event_type="ActionEligible", direction="buy", signal_type="B_BUY")
        missing = projection_event(event_id="evt_industry_missing", event_type="ActionEligible", direction="buy", signal_type="B_BUY")
        ambiguous = projection_event(event_id="evt_industry_ambiguous", event_type="ActionEligible", direction="buy", signal_type="B_BUY")
        for event, code in ((ready, "600000"), (missing, "600001"), (ambiguous, "600002")):
            event.identity_key = f"stock:SH:{code}"
            event.partition_key = event.identity_key
            event.payload_json["asset_kind"] = "stock"
            event.payload_json["identity_key"] = event.identity_key
            event.board_identity_key = "board:TDX:999999"
            event.board_code = "999999"
            event.board_name = "forbidden legacy pollution"
            add_projection_message_contract(event)

        duplicate = industry_membership_row("stock:SH:600000", "board:TDX:880001", "880001", "银行")
        rows = [
            duplicate,
            duplicate,
            industry_membership_row("stock:SH:600002", "board:TDX:880002", "880002", "证券"),
            industry_membership_row("stock:SH:600002", "board:TDX:880003", "880003", "保险"),
        ]

        frozen = freeze_stock_industry_context([ready, missing, ambiguous], rows)

        self.assertEqual(frozen[0].industry_status, "ready")
        self.assertEqual(frozen[0].board_identity_key, "board:TDX:880001")
        self.assertEqual(frozen[0].board_code, "880001")
        self.assertEqual(frozen[0].board_name, "银行")
        self.assertEqual(frozen[0].industry_provenance["source_relation"], N6_INDUSTRY_SOURCE_RELATION)
        self.assertEqual(frozen[0].industry_provenance["read_role"], N6_INDUSTRY_READ_ROLE)
        self.assertEqual(frozen[0].industry_provenance["distinct_mapping_count"], 1)
        self.assertEqual(frozen[1].industry_status, "not_ready")
        self.assertIsNone(frozen[1].board_code)
        self.assertEqual(frozen[1].industry_provenance["reason"], "industry_membership_missing")
        self.assertEqual(frozen[2].industry_status, "not_ready")
        self.assertIsNone(frozen[2].board_code)
        self.assertEqual(frozen[2].industry_provenance["reason"], "industry_membership_ambiguous")

    def test_industry_not_ready_does_not_block_core_projection(self) -> None:
        event = projection_event(event_id="evt_industry_not_ready", event_type="ActionEligible", direction="buy", signal_type="B_BUY")
        add_projection_message_contract(event)
        event = freeze_stock_industry_context([event], [])[0]
        expected = {"ActionEligible:pending": 1}

        report = run_projection_dry_run(
            repository=FakeProjectionRepository(default_snapshot(n5_outbox_counts=expected, events=[event])),
            expected_n5_outbox_counts=expected,
            user_message_event_filter=["ActionEligible"],
        )

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(report["planned_row_counts"]["user_signal_projection"], 1)
        self.assertEqual(report["sample_plans"][0]["card"]["industry_status"], "not_ready")

    def test_industry_query_uses_reviewed_view_and_exact_filters(self) -> None:
        source = inspect.getsource(PostgresProjectionPlanRepository._fetch_reviewed_industry_rows)

        self.assertIn("SELECT DISTINCT", source)
        self.assertIn("FROM v_n6_board_membership_fact", source)
        self.assertIn("stock_identity_key = ANY(%s)", source)
        self.assertIn("trade_date = ANY(%s)", source)
        self.assertIn("board_type = 'tdx_industry'", source)
        self.assertNotIn("n6_board_membership_display_cache", source)
        self.assertNotIn("n6_display_cache_run", source)
        self.assertNotIn("FROM board_membership_fact", source)

    def test_historical_event_without_marker_keeps_legacy_output_shape(self) -> None:
        event = projection_event(event_id="evt_no_marker", event_type="ActionEligible", direction="buy", signal_type="B_BUY")
        expected = {"ActionEligible:pending": 1}

        report = run_projection_dry_run(
            repository=FakeProjectionRepository(default_snapshot(n5_outbox_counts=expected, events=[event])),
            expected_n5_outbox_counts=expected,
            user_message_event_filter=["ActionEligible"],
        )

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertNotIn("projection_message_contract_version", report["sample_plans"][0]["card"])
        self.assertNotIn("industry_status", report["sample_plans"][0]["card"])

    def test_legacy_action_event_and_hint_event_remain_compatible(self) -> None:
        snapshot = default_snapshot(
            n5_outbox_counts=dict(LEGACY_EXPECTED_N5_OUTBOX_COUNTS),
            events=[
                projection_event(event_id="evt_legacy_action", event_type="ActionEvent", direction="buy", signal_type="B_BUY"),
                projection_event(event_id="evt_legacy_hint", event_type="HintEvent", direction="sell", signal_type="S_SELL"),
            ],
        )
        repo = FakeProjectionRepository(snapshot)

        report = run_projection_dry_run(repository=repo)

        self.assertEqual(report["result"], "DRY_RUN_PASS")
        self.assertEqual(report["event_summary"]["by_event_type"], {"ActionEvent": 1, "HintEvent": 1})
        self.assertEqual(
            report["notification_plan_summary"]["notification_source_counts"],
            {"n5_action_event": 1, "n5_hint_event": 1},
        )
        self.assertEqual(report["quality"]["p0_count"], 0)

    def test_buy_hint_and_sell_hint_are_not_input_event_types(self) -> None:
        snapshot = default_snapshot(
            events=[
                projection_event(event_id="evt_buy_hint_type", event_type="BUY_HINT", direction="buy", signal_type="B_BUY"),
                projection_event(event_id="evt_sell_hint_type", event_type="SELL_HINT", direction="sell", signal_type="S_SELL"),
            ],
        )
        repo = FakeProjectionRepository(snapshot)

        report = run_projection_dry_run(repository=repo)

        self.assertEqual(report["result"], "BLOCKED")
        self.assertIn("input_event_type_not_supported_n5_action_event", report["blockers"])

    def test_supported_event_type_contract_lists_canonical_and_legacy_events(self) -> None:
        repo = FakeProjectionRepository(default_snapshot())

        report = run_projection_dry_run(repository=repo)

        boundary = report["input_boundary"]["n5_outbox"]
        self.assertEqual(tuple(boundary["canonical_event_types"]), CANONICAL_EVENT_TYPES)
        self.assertEqual(tuple(boundary["legacy_compat_event_types"]), LEGACY_EVENT_TYPES)


def default_snapshot(
    *,
    admin: AdminUser | None = AdminUser(user_id=1, login_name="admin", role="admin", status="active"),
    default_profile: FilterProfile | None = FilterProfile(
        user_filter_profile_id=1,
        user_id=1,
        profile_name="MVP default",
        is_default=True,
        status="active",
    ),
    n5_outbox_counts: dict[str, int] | None = None,
    events: list[ProjectionEvent] | None = None,
) -> ProjectionInputSnapshot:
    return ProjectionInputSnapshot(
        table_counts={
            "user_account": 1,
            "user_filter_profile": 1,
            "user_session": 0,
            "user_watchlist": 0,
            "user_watchlist_item": 0,
            "user_projection_run": 0,
            "user_signal_projection": 0,
            "user_signal_card": 0,
            "user_signal_decision": 0,
            "user_notification_queue": 0,
            "user_sim_account": 0,
            "user_sim_order": 0,
            "user_sim_trade": 0,
            "user_sim_position": 0,
        },
        admin=admin,
        default_profile=default_profile,
        n5_outbox_counts=dict(n5_outbox_counts or EXPECTED_N5_OUTBOX_COUNTS),
        display_basis_counts={},
        events=events
        if events is not None
        else [
            projection_event(event_id="evt_blocked_buy", event_type="ActionBlocked", direction="buy", signal_type="B_BUY"),
            projection_event(event_id="evt_blocked_sell", event_type="ActionBlocked", direction="sell", signal_type="S_SELL"),
        ],
    )


def projection_event(
    *,
    event_id: str,
    event_type: str,
    direction: str,
    signal_type: str,
    target_price: str | None = None,
    expected_return_pct: str | None = None,
    action_mark: str | None = None,
) -> ProjectionEvent:
    source_run_id = (
        "action_consumer_canonical_20260529_trigger_execute_20260529_condition_layer_20260528_source_20260528_v1"
        if event_type not in LEGACY_EVENT_TYPES
        else "action_consumer_current_real_execute_20260525_trigger_projection_matcher_execute_20260525_condition_layer_20260522_to_20260525102249"
    )
    payload_json = {
        "run_id": source_run_id,
        "asset_kind": "stock",
        "identity_key": "stock:SH:600000",
        "direction": direction,
        "signal_type": signal_type,
        "action_type": "buy_candidate" if direction == "buy" else "sell_candidate",
        "lane": "hint" if event_type == "HintEvent" else "policy_pending",
        "condition_key": "BUY:Y" if direction == "buy" else "SELL:Y",
        "trigger_period": "30m",
        "action_key": f"action:{event_id}",
        "dedup_key": f"dedup:{event_id}",
        "source_condition_run_id": "condition_layer_20260528_source_20260528_v1",
        "source_market_data_run_id": "market_data_subscription_20260529_condition_layer_20260528_source_20260528_v1",
        "source_market_trace": {"trace_source": "test"},
    }
    if event_type in CANONICAL_EVENT_TYPES:
        action_state_by_type = {
            "ActionEligible": "eligible",
            "ActionBlocked": "blocked",
            "ActionExecuted": "executed",
            "ActionSkipped": "skipped",
        }
        payload_json.update(
            {
                "action_state": action_state_by_type[event_type],
                "action_mark": action_mark,
                "original_condition_key": payload_json["condition_key"],
                "trace_json": {
                    "condition_key": payload_json["condition_key"],
                    "original_condition_key": payload_json["condition_key"],
                    "hint_family": "BUY_HINT" if direction == "buy" else "SELL_HINT",
                },
            }
        )
    return ProjectionEvent(
        outbox_id=1,
        event_id=event_id,
        event_type=event_type,
        event_schema_version="v1",
        trade_date="20260525",
        asset_kind="stock",
        identity_key="stock:SH:600000",
        event_time="2026-05-25T14:10:00+08:00",
        source_layer="N5_action",
        source_run_id=source_run_id,
        dedup_key=f"dedup:{event_id}",
        partition_key="stock:SH:600000",
        status="pending",
        payload_json=payload_json,
        source_display_table=None,
        display_basis_id=None,
        display_run_id=payload_json["source_condition_run_id"],
        code="600000",
        name="浦发银行",
        target_price=target_price,
        expected_return_pct=expected_return_pct,
        board_code=None,
        board_name=None,
    )


def set_event_asset(event: ProjectionEvent, asset_kind: str) -> None:
    identity_key, code, name = {
        "stock": ("stock:SH:600000", "600000", "浦发银行"),
        "index": ("index:SH:000300", "000300", "沪深300"),
        "board": ("board:TDX:880001", "880001", "银行"),
    }[asset_kind]
    event.asset_kind = asset_kind
    event.identity_key = identity_key
    event.partition_key = identity_key
    event.code = code
    event.name = name
    event.payload_json["asset_kind"] = asset_kind
    event.payload_json["identity_key"] = identity_key


def add_pct_contract(event: ProjectionEvent) -> dict:
    fields = {
        "name": event.name or event.identity_key,
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
    }
    if event.asset_kind == "stock":
        fields.update({"score": "88", "pe_core": "10.5"})
    context_payload = {
        "contract_version": "N2-condition-projection-context-v1",
        "source_layer": "N2_condition",
        "asset_kind": event.asset_kind,
        "identity_key": event.identity_key,
        "source_trade_date": "20260524",
        "for_trade_date": event.trade_date,
        "status": "ready",
        "fields": fields,
        "nullable_fields": [
            key for key, value in fields.items() if value is None
        ],
        "not_ready_reasons": [],
    }
    context = {
        **context_payload,
        "context_hash": stable_context_hash(context_payload),
    }
    event.event_schema_version = "v2"
    event.payload_json.update(
        {
            "pct_contract_version": "N5-trigger-action-pct-context-v1",
            "condition_projection_context": context,
            "condition_projection_context_status": "ready",
            "condition_projection_context_trace": {
                "policy_version": "N4-condition-projection-passthrough-v1",
                "policy_hash": "2cd95d3d427ec07ccd208bc7b939081d104415f6b9da3c4bf78e40b78a6d279e",
                "status": "ready",
                "source_context_hash": context["context_hash"],
            },
            "trigger_price": "10.5",
            "trigger_pct": "999.123456",
            "trigger_pct_status": "ready",
        }
    )
    if event.event_type == "ActionExecuted":
        event.payload_json.update(
            {
                "action_price": "10.8",
                "action_pct": "888.654321",
                "action_pct_status": "ready",
            }
        )
    return context


def add_projection_message_contract(event: ProjectionEvent) -> dict:
    context = add_pct_contract(event)
    fields = context["fields"]
    event.payload_json.update(
        {
            "projection_message_contract_version": N5_PROJECTION_MESSAGE_CONTRACT_VERSION,
            "projection_message_contract_hash": N5_PROJECTION_MESSAGE_CONTRACT_HASH,
            "projection_message_status": "ready",
            "projection_message_not_ready_reasons": [],
            "asset_code": event.identity_key.split(":")[-1],
            "asset_name": fields["name"],
            "buy_expected_return_pct": fields["buy_expected_return_pct"],
            "sell_expected_return_pct": fields["sell_expected_return_pct"],
            "up_secondary_expected_return_pct": fields["up_secondary_expected_return_pct"],
            "up_reference_period": fields["up_reference_period"],
            "down_reference_period": fields["down_reference_period"],
            "primary_trigger_period": "D",
            "all_trigger_periods": ["D"],
        }
    )
    if event.asset_kind == "stock":
        event.payload_json.update({"score": fields["score"], "pe_core": fields["pe_core"]})
    event.target_price = fields["buy_target_price"]
    event.expected_return_pct = fields["buy_expected_return_pct"]
    return context


def industry_membership_row(
    stock_identity_key: str,
    board_identity_key: str,
    board_code: str,
    board_name: str,
) -> IndustryMembershipRow:
    return IndustryMembershipRow(
        trade_date="20260524",
        stock_identity_key=stock_identity_key,
        board_identity_key=board_identity_key,
        board_code=board_code,
        board_name=board_name,
    )


def stable_context_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


if __name__ == "__main__":
    unittest.main()
