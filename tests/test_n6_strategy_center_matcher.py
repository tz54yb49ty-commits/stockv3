from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest

from ashare_v3.user.strategy_center import (
    APPROVED_PACKAGE_POLICY_HASHES,
    APPROVED_PACKAGE_POLICY_PAYLOADS,
    EVALUATOR_POLICY_HASH,
    MembershipRow,
    MembershipSnapshotAuthority,
    ParentExecutedEvent,
    ScopeRow,
    StockSignalEvent,
    STRATEGY_VERSION_V1,
    evaluate_strategy_center,
    evaluate_strategy_center_observations,
    evaluate_strategy_center_versioned,
)
from ashare_v3.user.strategy_center_repository import (
    BOARD_MEMBERSHIP_ROWS_SQL,
    INDEX_MEMBERSHIP_ROWS_SQL,
    N6StrategyCenterReadRepository,
    PARENT_EXECUTED_SIGNAL_IDS_SQL,
    SCOPE_ROWS_SQL,
    SIGNAL_AUTHORITY_ROWS_SQL,
)


TRADE_DATE = "20260721"
STOCK = "stock:SH:600000"
INDEX = "index:SH:000300"
BOARD = "board:TDX:880001"
EPISODE = "evt-n4-entry-1"
_AUTO_MEMBERSHIP_AUTHORITIES = object()


def signal(
    *,
    state: str = "eligible",
    event_id: str = "evt-stock-eligible",
    event_time: str = "2026-07-21T09:40:00+08:00",
    trade_date: str = TRADE_DATE,
    episode: str = EPISODE,
    projection_id: int = 101,
    direction: str = "buy",
) -> StockSignalEvent:
    event_type = "ActionExecuted" if state == "executed" else "ActionEligible"
    return StockSignalEvent(
        user_signal_projection_id=projection_id,
        trade_date=trade_date,
        identity_key=STOCK,
        code="600000",
        name="浦发银行",
        event_id=event_id,
        event_type=event_type,
        action_state=state,
        event_time=event_time,
        action_episode_key=episode,
        source_run_id="n5-run-1",
        event_schema_version="N5ActionEvent.v2",
        signal={
            "identity_key": STOCK,
            "direction": direction,
            "action_state": state,
            "action_price": "10.120000",
            "all_existing_signal_fields": "preserved",
            "condition_projection_context": {
                "source_trade_date": trade_date,
            },
        },
    )


def membership(
    kind: str,
    *,
    identity_key: str | None = None,
    code: str | None = None,
    name: str | None = None,
    board_type: str = "",
    trade_date: str = TRADE_DATE,
    source_version: str = "membership-20260721-v1",
) -> MembershipRow:
    if kind == "index":
        identity_key = identity_key or INDEX
        code = code or "000300"
        name = name or "沪深300"
    else:
        identity_key = identity_key or BOARD
        code = code or "880001"
        name = name or "银行"
        board_type = board_type or "tdx_industry"
    return MembershipRow(
        trade_date=trade_date,
        stock_identity_key=STOCK,
        parent_asset_kind=kind,
        parent_identity_key=identity_key,
        parent_code=code,
        parent_name=name,
        source_version=source_version,
        source_batch_id="membership-batch-1",
        created_at="2026-07-21T08:00:00+08:00",
        board_type=board_type,
    )


def parent_event(
    kind: str,
    *,
    identity_key: str | None = None,
    code: str | None = None,
    name: str | None = None,
    event_id: str | None = None,
    direction: str = "buy",
    trade_date: str = TRADE_DATE,
    event_time: str = "2026-07-21T09:35:00+08:00",
    projection_id: int | None = None,
) -> ParentExecutedEvent:
    row = membership(
        kind,
        identity_key=identity_key,
        code=code,
        name=name,
    )
    return ParentExecutedEvent(
        trade_date=trade_date,
        asset_kind=kind,
        identity_key=row.parent_identity_key,
        code=row.parent_code,
        name=row.parent_name,
        event_id=event_id or f"evt-{kind}-executed",
        event_type="ActionExecuted",
        action_state="executed",
        event_time=event_time,
        source_run_id="n5-parent-run",
        event_schema_version="N5ActionEvent.v2",
        direction=direction,
        user_signal_projection_id=(
            projection_id
            if projection_id is not None
            else 1
        ),
    )


def membership_authorities_for(
    stock_signals: list[StockSignalEvent],
) -> list[MembershipSnapshotAuthority]:
    authorities = []
    episode_keys = sorted(
        {
            (event.identity_key, event.action_episode_key, event.trade_date)
            for event in stock_signals
            if event.identity_key and event.action_episode_key
        }
    )
    for identity_key, episode_key, requested_date in episode_keys:
        for kind in ("index", "board"):
            authorities.append(
                MembershipSnapshotAuthority(
                    stock_identity_key=identity_key,
                    action_episode_key=episode_key,
                    membership_kind=kind,
                    requested_source_trade_date=requested_date,
                    selected_membership_trade_date=TRADE_DATE,
                    source_version="membership-20260721-v1",
                    source_batch_id="membership-batch-1",
                    provenance_status="authoritative_as_of",
                    quality_status="passed",
                )
            )
    return authorities


def evaluate(
    *,
    stock_signals: list[StockSignalEvent] | None = None,
    in_scope: bool = True,
    index_memberships: list[MembershipRow] | None = None,
    board_memberships: list[MembershipRow] | None = None,
    parent_events: list[ParentExecutedEvent] | None = None,
    packages: tuple[str, ...] = ("package_1", "package_2"),
    evaluation_time: str | None = None,
    membership_authorities=_AUTO_MEMBERSHIP_AUTHORITIES,
    frozen_matches=(),
    frozen_observations=(),
):
    resolved_signals = stock_signals if stock_signals is not None else [signal()]
    resolved_authorities = (
        membership_authorities_for(resolved_signals)
        if membership_authorities is _AUTO_MEMBERSHIP_AUTHORITIES
        else membership_authorities
    )
    return evaluate_strategy_center(
        trade_date=TRADE_DATE,
        selected_package_keys=packages,
        stock_signals=resolved_signals,
        scope_rows=[ScopeRow(TRADE_DATE, STOCK, "monitor")] if in_scope else [],
        index_memberships=(
            index_memberships
            if index_memberships is not None
            else [membership("index")]
        ),
        board_memberships=(
            board_memberships
            if board_memberships is not None
            else [membership("board")]
        ),
        parent_executed_events=parent_events if parent_events is not None else [],
        membership_authorities=resolved_authorities,
        evaluation_time=evaluation_time,
        frozen_matches=frozen_matches,
        frozen_observations=frozen_observations,
    )


class StrategyCenterMatcherTest(unittest.TestCase):
    def test_approved_v2_package_content_authority_matches_final_rules(self) -> None:
        for package_key, payload in APPROVED_PACKAGE_POLICY_PAYLOADS.items():
            rules = payload["rules"]
            self.assertEqual(
                rules["event_selection"],
                "first_confirmation_then_minimum_span",
            )
            self.assertEqual(
                rules["event_time_authority"],
                "n5_standard_event_time_only",
            )
            self.assertEqual(
                rules["observation_reasons"],
                ["weak_span", "stale_after_confirmation"],
            )
            self.assertEqual(
                rules["arrival_order_authority"],
                "user_signal_projection_id_monotonic",
            )
            self.assertEqual(
                rules["frozen_episode_authority"],
                "persisted_match_or_observation_projection",
            )
            self.assertEqual(
                rules["successive_episode_trigger"],
                "new_qualification_parent_projection_only",
            )
            self.assertEqual(
                rules["cross_surface_uniqueness"],
                "one_coherence_episode_one_surface",
            )
            self.assertEqual(
                rules["mixed_package_level_policy"],
                "qualified_if_any_package_qualified_weak_evidence_retained",
            )
            self.assertTrue(rules["heat_evidence_frozen_per_episode"])
            self.assertFalse(rules["stock_state_upgrade_creates_episode"])
            self.assertEqual(payload["package_version"], "v2")
        independently_hashed = {
            package_key: hashlib.sha256(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            ).hexdigest()
            for package_key, payload in APPROVED_PACKAGE_POLICY_PAYLOADS.items()
        }
        self.assertEqual(APPROVED_PACKAGE_POLICY_HASHES, independently_hashed)
        self.assertEqual(
            set(APPROVED_PACKAGE_POLICY_HASHES),
            {"package_1", "package_2"},
        )

    def test_complete_truth_table_for_selected_packages(self) -> None:
        cases = (
            (False, False, ()),
            (True, False, ()),
            (False, True, ("package_2",)),
            (True, True, ("package_1", "package_2")),
        )
        for index_executed, board_executed, expected in cases:
            with self.subTest(
                index_executed=index_executed,
                board_executed=board_executed,
            ):
                events = []
                if index_executed:
                    events.append(parent_event("index"))
                if board_executed:
                    events.append(parent_event("board"))
                rows = evaluate(parent_events=events)
                actual = rows[0].matched_packages if rows else ()
                self.assertEqual(actual, expected)

        self.assertEqual(evaluate(in_scope=False, parent_events=[
            parent_event("index"), parent_event("board")
        ]), ())
        blocked = replace(
            signal(), action_state="blocked", event_type="ActionBlocked"
        )
        self.assertEqual(evaluate(stock_signals=[blocked], parent_events=[
            parent_event("index"), parent_event("board")
        ]), ())

    def test_selected_package_policy_is_per_user_input_and_never_zero(self) -> None:
        events = [parent_event("index"), parent_event("board")]
        self.assertEqual(
            evaluate(parent_events=events, packages=("package_1",))[0].matched_packages,
            ("package_1",),
        )
        self.assertEqual(
            evaluate(parent_events=events, packages=("package_2",))[0].matched_packages,
            ("package_2",),
        )
        with self.assertRaises(ValueError):
            evaluate(parent_events=events, packages=())
        with self.assertRaises(ValueError):
            evaluate(parent_events=events, packages=("package_1", "package_1"))

    def test_any_index_executes_and_all_authoritative_indices_are_displayed(self) -> None:
        second = membership(
            "index",
            identity_key="index:SH:000905",
            code="000905",
            name="中证500",
        )
        rows = evaluate(
            index_memberships=[membership("index"), second],
            parent_events=[
                parent_event(
                    "index",
                    identity_key="index:SH:000905",
                    code="000905",
                    name="中证500",
                ),
                parent_event("board"),
            ],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            [(item["code"], item["executed_today"]) for item in rows[0].indices],
            [("000300", False), ("000905", True)],
        )
        self.assertEqual(rows[0].matched_packages, ("package_1", "package_2"))

    def test_board_allowlist_accepts_concept_and_rejects_tdx_other_pollution(self) -> None:
        other = membership("board", board_type="tdx_other")
        self.assertEqual(
            evaluate(
                board_memberships=[other],
                parent_events=[parent_event("board")],
            ),
            (),
        )
        concept = membership("board", board_type="tdx_concept")
        rows = evaluate(
            board_memberships=[concept],
            parent_events=[parent_event("board")],
            packages=("package_2",),
        )
        self.assertEqual(rows[0].matched_boards[0]["board_type"], "tdx_concept")

    def test_same_direction_is_required_and_missing_direction_fails_closed(self) -> None:
        self.assertEqual(evaluate(
            parent_events=[
                parent_event("index", direction="sell"),
                parent_event("board", direction="sell"),
            ]
        ), ())
        self.assertEqual(
            evaluate(
                parent_events=[
                    parent_event("index", direction="buy"),
                    parent_event("board", direction="sell"),
                ]
            ),
            (),
        )

    def test_complete_buy_sell_direction_matrix(self) -> None:
        for stock_direction in ("buy", "sell"):
            for index_direction in ("buy", "sell"):
                for board_direction in ("buy", "sell"):
                    with self.subTest(
                        stock=stock_direction,
                        index=index_direction,
                        board=board_direction,
                    ):
                        rows = evaluate(
                            stock_signals=[signal(direction=stock_direction)],
                            parent_events=[
                                parent_event("index", direction=index_direction),
                                parent_event("board", direction=board_direction),
                            ],
                        )
                        expected = ()
                        if stock_direction == board_direction:
                            expected = (
                                ("package_1", "package_2")
                                if stock_direction == index_direction
                                else ("package_2",)
                            )
                        actual = rows[0].matched_packages if rows else ()
                        self.assertEqual(actual, expected)

    def test_china_world_trade_center_600007_opposite_parents_is_not_visible(self) -> None:
        china_world_trade_center = replace(
            signal(direction="buy"),
            identity_key="stock:SH:600007",
            code="600007",
            name="中国国贸",
        )
        index_membership = replace(
            membership("index"),
            stock_identity_key=china_world_trade_center.identity_key,
        )
        board_membership = replace(
            membership("board"),
            stock_identity_key=china_world_trade_center.identity_key,
        )
        result = evaluate_strategy_center_versioned(
            strategy_version="N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2",
            trade_date=TRADE_DATE,
            selected_package_keys=("package_1", "package_2"),
            stock_signals=(china_world_trade_center,),
            scope_rows=(
                ScopeRow(
                    TRADE_DATE,
                    china_world_trade_center.identity_key,
                    "monitor",
                ),
            ),
            index_memberships=(index_membership,),
            board_memberships=(board_membership,),
            parent_executed_events=(
                parent_event("index", direction="sell"),
                parent_event("board", direction="sell"),
            ),
            membership_authorities=membership_authorities_for(
                [china_world_trade_center]
            ),
            evaluation_time="2026-07-21T09:40:00+08:00",
        )
        self.assertEqual(result.matches, ())
        self.assertEqual(result.observations, ())

    def test_trading_minute_boundaries_midday_break_and_staleness(self) -> None:
        strong = evaluate(
            stock_signals=[signal(event_time="2026-07-21T10:00:00+08:00")],
            parent_events=[
                parent_event("board", event_time="2026-07-21T09:45:00+08:00")
            ],
            packages=("package_2",),
        )[0]
        strong_audit = strong.confluence
        self.assertEqual(strong_audit["coherence_level"], "STRONG")
        self.assertEqual(strong_audit["coherence_span_trading_minutes"], 15)

        medium = evaluate(
            stock_signals=[signal(event_time="2026-07-21T10:00:00+08:00")],
            parent_events=[
                parent_event("board", event_time="2026-07-21T09:30:00+08:00")
            ],
            packages=("package_2",),
        )[0]
        medium_audit = medium.confluence
        self.assertEqual(medium_audit["coherence_level"], "MEDIUM")
        self.assertEqual(medium_audit["coherence_span_trading_minutes"], 30)

        for stock_time in ("10:01", "10:30", "10:31"):
            with self.subTest(stock_time=stock_time):
                self.assertEqual(
                    evaluate(
                        stock_signals=[
                            signal(
                                event_time=(
                                    f"2026-07-21T{stock_time}:00+08:00"
                                )
                            )
                        ],
                        parent_events=[
                            parent_event(
                                "board",
                                event_time="2026-07-21T09:30:00+08:00",
                            )
                        ],
                        packages=("package_2",),
                    ),
                    (),
                )

        midday = evaluate(
            stock_signals=[signal(event_time="2026-07-21T13:00:00+08:00")],
            parent_events=[
                parent_event("board", event_time="2026-07-21T11:30:00+08:00")
            ],
            packages=("package_2",),
        )[0]
        midday_audit = midday.confluence
        self.assertEqual(midday_audit["coherence_span_trading_minutes"], 0)
        self.assertEqual(
            evaluate(
                parent_events=[
                    parent_event(
                        "board", event_time="2026-07-21T12:00:00+08:00"
                    )
                ],
                packages=("package_2",),
            ),
            (),
        )

        live = dict(
            stock_signals=[signal(event_time="2026-07-21T14:00:00+08:00")],
            parent_events=[
                parent_event("board", event_time="2026-07-21T14:00:00+08:00")
            ],
            packages=("package_2",),
        )
        self.assertEqual(
            len(evaluate(**live, evaluation_time="2026-07-21T14:30:00+08:00")),
            1,
        )
        self.assertEqual(
            evaluate(**live, evaluation_time="2026-07-21T14:31:00+08:00"),
            (),
        )

        ten_minutes = evaluate(
            **live, evaluation_time="2026-07-21T14:10:00+08:00"
        )
        twenty_minutes = evaluate(
            **live, evaluation_time="2026-07-21T14:20:00+08:00"
        )
        self.assertEqual(ten_minutes, twenty_minutes)
        self.assertEqual(
            ten_minutes[0].projection_hash,
            twenty_minutes[0].projection_hash,
        )
        frozen_audit = ten_minutes[0].confluence
        self.assertNotIn("evaluation_time", frozen_audit)
        self.assertEqual(
            frozen_audit["stale_at"], "2026-07-21T14:30:00+08:00"
        )
        self.assertEqual(
            frozen_audit["stale_at_trading_second_coordinate"],
            12600,
        )
        self.assertTrue(frozen_audit["stale_at_same_trade_date"])

    def test_weak_31_to_60_is_not_a_qualified_match_projection(self) -> None:
        for stock_time in ("10:01", "10:30"):
            with self.subTest(stock_time=stock_time):
                rows = evaluate(
                    stock_signals=[
                        signal(event_time=f"2026-07-21T{stock_time}:00+08:00")
                    ],
                    parent_events=[
                        parent_event(
                            "board",
                            event_time="2026-07-21T09:30:00+08:00",
                        )
                    ],
                    packages=("package_2",),
                )
                self.assertEqual(rows, ())

    def test_weak_31_to_60_has_separate_display_only_surface(self) -> None:
        for stock_time, expected_minutes in (("10:01", 31), ("10:30", 60)):
            with self.subTest(stock_time=stock_time):
                stock = signal(
                    event_time=f"2026-07-21T{stock_time}:00+08:00"
                )
                observations = evaluate_strategy_center_observations(
                    trade_date=TRADE_DATE,
                    selected_package_keys=("package_2",),
                    stock_signals=[stock],
                    scope_rows=[ScopeRow(TRADE_DATE, STOCK, "monitor")],
                    index_memberships=[membership("index")],
                    board_memberships=[membership("board")],
                    parent_executed_events=[
                        parent_event(
                            "board",
                            event_time="2026-07-21T09:30:00+08:00",
                        )
                    ],
                    membership_authorities=membership_authorities_for([stock]),
                    evaluation_time=f"2026-07-21T{stock_time}:00+08:00",
                )
                self.assertEqual(len(observations), 1)
                payload = observations[0].as_payload()
                audit = payload["confluence"]
                self.assertEqual(audit["coherence_level"], "WEAK")
                self.assertEqual(
                    audit["coherence_span_trading_minutes"],
                    expected_minutes,
                )
                self.assertEqual(payload["observed_packages"], ["package_2"])
                self.assertFalse(payload["qualified_strategy_match"])
                self.assertNotIn("matched_packages", payload)

        expired_stock = signal(event_time="2026-07-21T10:31:00+08:00")
        self.assertEqual(
            evaluate_strategy_center_observations(
                trade_date=TRADE_DATE,
                selected_package_keys=("package_2",),
                stock_signals=[expired_stock],
                scope_rows=[ScopeRow(TRADE_DATE, STOCK, "monitor")],
                index_memberships=[membership("index")],
                board_memberships=[membership("board")],
                parent_executed_events=[
                    parent_event(
                        "board",
                        event_time="2026-07-21T09:30:00+08:00",
                    )
                ],
                membership_authorities=membership_authorities_for(
                    [expired_stock]
                ),
                evaluation_time="2026-07-21T10:31:00+08:00",
            ),
            (),
        )

    def test_no_lookahead_and_cross_timestamp_trade_date_fail_closed(self) -> None:
        future_board = parent_event(
            "board", event_time="2026-07-21T10:10:00+08:00"
        )
        stock = signal(event_time="2026-07-21T10:00:00+08:00")
        self.assertEqual(
            evaluate(
                stock_signals=[stock],
                parent_events=[future_board],
                packages=("package_2",),
                evaluation_time="2026-07-21T10:05:00+08:00",
            ),
            (),
        )
        self.assertEqual(
            len(
                evaluate(
                    stock_signals=[stock],
                    parent_events=[future_board],
                    packages=("package_2",),
                    evaluation_time="2026-07-21T10:10:00+08:00",
                )
            ),
            1,
        )
        wrong_timestamp_day = signal(
            event_time="2026-07-20T10:00:00+08:00"
        )
        self.assertEqual(
            evaluate(
                stock_signals=[wrong_timestamp_day],
                parent_events=[parent_event("board")],
                packages=("package_2",),
            ),
            (),
        )
        with self.assertRaises(ValueError):
            evaluate(
                parent_events=[parent_event("board")],
                packages=("package_2",),
                evaluation_time="2026-07-20T12:00:00+08:00",
            )

    def test_preopen_midday_and_postclose_evaluation_clock_is_safe(self) -> None:
        self.assertEqual(
            evaluate(
                parent_events=[parent_event("board")],
                packages=("package_2",),
                evaluation_time="2026-07-21T09:00:00+08:00",
            ),
            (),
        )

        lunch_inputs = {
            "stock_signals": [
                signal(event_time="2026-07-21T11:00:00+08:00")
            ],
            "parent_events": [
                parent_event("board", event_time="2026-07-21T11:00:00+08:00")
            ],
            "packages": ("package_2",),
        }
        at_morning_close = evaluate(
            **lunch_inputs,
            evaluation_time="2026-07-21T11:30:00+08:00",
        )
        during_lunch = evaluate(
            **lunch_inputs,
            evaluation_time="2026-07-21T12:59:59+08:00",
        )
        self.assertEqual(at_morning_close, during_lunch)
        self.assertEqual(
            at_morning_close[0].projection_hash,
            during_lunch[0].projection_hash,
        )
        self.assertEqual(
            evaluate(
                **lunch_inputs,
                evaluation_time="2026-07-21T13:01:00+08:00",
            ),
            (),
        )
        self.assertEqual(
            evaluate(
                stock_signals=[
                    signal(event_time="2026-07-21T13:00:00+08:00")
                ],
                parent_events=[
                    parent_event(
                        "board", event_time="2026-07-21T13:00:00+08:00"
                    )
                ],
                packages=("package_2",),
                evaluation_time="2026-07-21T12:00:00+08:00",
            ),
            (),
        )

        postclose_inputs = {
            "stock_signals": [
                signal(event_time="2026-07-21T14:45:00+08:00")
            ],
            "parent_events": [
                parent_event("board", event_time="2026-07-21T14:45:00+08:00")
            ],
            "packages": ("package_2",),
        }
        at_close = evaluate(
            **postclose_inputs,
            evaluation_time="2026-07-21T15:00:00+08:00",
        )
        after_close = evaluate(
            **postclose_inputs,
            evaluation_time="2026-07-21T18:00:00+08:00",
        )
        self.assertEqual(len(at_close), 1)
        self.assertEqual(at_close, after_close)
        self.assertEqual(at_close[0].projection_hash, after_close[0].projection_hash)
        close_audit = at_close[0].confluence
        self.assertIsNone(close_audit["stale_at"])
        self.assertEqual(
            close_audit["stale_at_trading_second_coordinate"],
            15300,
        )
        self.assertFalse(close_audit["stale_at_same_trade_date"])
        self.assertNotIn("stale_at_truncated_by_trade_date", close_audit)
        self.assertEqual(
            evaluate(
                stock_signals=[
                    signal(event_time="2026-07-21T14:20:00+08:00")
                ],
                parent_events=[
                    parent_event(
                        "board", event_time="2026-07-21T14:20:00+08:00"
                    )
                ],
                packages=("package_2",),
                evaluation_time="2026-07-21T18:00:00+08:00",
            ),
            (),
        )

        for invalid_event_time in ("09:00:00", "12:00:00", "15:30:00"):
            with self.subTest(invalid_event_time=invalid_event_time):
                self.assertEqual(
                    evaluate(
                        stock_signals=[
                            signal(
                                event_time=(
                                    "2026-07-21T"
                                    f"{invalid_event_time}+08:00"
                                )
                            )
                        ],
                        parent_events=[parent_event("board")],
                        packages=("package_2",),
                        evaluation_time="2026-07-21T18:00:00+08:00",
                    ),
                    (),
                )

    def test_earliest_qualified_confirmation_freezes_future_shorter_span(
        self,
    ) -> None:
        second_board = membership(
            "board",
            identity_key="board:TDX:880002",
            code="880002",
            name="证券",
        )
        farther = parent_event(
            "board",
            event_time="2026-07-21T09:50:00+08:00",
            projection_id=201,
        )
        closer = parent_event(
            "board",
            identity_key="board:TDX:880002",
            code="880002",
            name="证券",
            event_id="evt-board-closer",
            event_time="2026-07-21T10:05:00+08:00",
            projection_id=202,
        )
        kwargs = {
            "stock_signals": [signal(event_time="2026-07-21T10:00:00+08:00")],
            "board_memberships": [membership("board"), second_board],
            "packages": ("package_2",),
        }
        first = evaluate(
            parent_events=[farther],
            evaluation_time="2026-07-21T10:05:00+08:00",
            **kwargs,
        )
        after_future = evaluate(
            parent_events=[farther, closer],
            evaluation_time="2026-07-21T10:05:00+08:00",
            frozen_matches=first,
            **kwargs,
        )
        replay = evaluate(
            parent_events=[closer, farther, closer],
            evaluation_time="2026-07-21T10:05:00+08:00",
            frozen_matches=first,
            **kwargs,
        )
        self.assertEqual(after_future, replay)
        self.assertEqual(len(after_future), 2)
        self.assertEqual(first[0], after_future[0])
        audit = first[0].confluence
        self.assertEqual(audit["coherence_span_trading_minutes"], 10)
        self.assertEqual(
            audit["confirmation_time"],
            "2026-07-21T10:00:00+08:00",
        )
        self.assertEqual(
            audit["package_evidence"][0]["board_event_id"],
            farther.event_id,
        )
        self.assertNotIn(closer.event_id, after_future[0].source_event_ids)
        self.assertIn(closer.event_id, after_future[1].source_event_ids)
        self.assertEqual(first[0].projection_hash, after_future[0].projection_hash)

    def test_market_heat_four_states_do_not_create_candidates(self) -> None:
        heat_1 = dict(
            identity_key="index:SH:000001",
            code="000001",
            name="上证指数",
            event_id="evt-heat-sh",
        )
        heat_2 = dict(
            identity_key="index:SZ:399001",
            code="399001",
            name="深证成指",
            event_id="evt-heat-sz",
        )
        board = parent_event("board")
        cases = (
            ([], "MARKET_HEAT_NEUTRAL"),
            (
                [parent_event("index", direction="buy", **heat_1)],
                "MARKET_HEAT_MIXED",
            ),
            (
                [parent_event("index", direction="sell", **heat_1)],
                "MARKET_HEAT_MIXED",
            ),
            (
                [
                    parent_event("index", direction="buy", **heat_1),
                    parent_event("index", direction="buy", **heat_2),
                ],
                "MARKET_HEAT_SUPPORTIVE",
            ),
            (
                [
                    parent_event("index", direction="sell", **heat_1),
                    parent_event("index", direction="sell", **heat_2),
                ],
                "MARKET_HEAT_ADVERSE",
            ),
            (
                [
                    parent_event("index", direction="buy", **heat_1),
                    parent_event("index", direction="sell", **heat_2),
                ],
                "MARKET_HEAT_MIXED",
            ),
        )
        for heat_events, expected in cases:
            with self.subTest(expected=expected):
                rows = evaluate(
                    parent_events=[board, *heat_events],
                    packages=("package_2",),
                )
                audit = rows[0].confluence
                self.assertEqual(audit["market_heat_state"], expected)
                self.assertFalse(audit["market_heat_creates_candidate"])

        stale_heat = parent_event(
            "index",
            direction="buy",
            event_time="2026-07-21T09:35:00+08:00",
            **heat_1,
        )
        late_rows = evaluate(
            stock_signals=[signal(event_time="2026-07-21T10:10:00+08:00")],
            parent_events=[
                parent_event("board", event_time="2026-07-21T10:10:00+08:00"),
                stale_heat,
            ],
            packages=("package_2",),
        )
        self.assertEqual(
            late_rows[0].confluence["market_heat_state"],
            "MARKET_HEAT_NEUTRAL",
        )
        self.assertEqual(
            evaluate(
                parent_events=[
                    parent_event("index", direction="buy", **heat_1),
                    parent_event("index", direction="buy", **heat_2),
                ],
                packages=("package_2",),
            ),
            (),
        )

    def test_market_heat_affects_only_deterministic_candidate_ranking(self) -> None:
        supportive_stock = "stock:SH:600002"
        adverse_stock = "stock:SH:600001"
        supportive = replace(
            signal(event_id="evt-supportive", episode="episode-supportive"),
            identity_key=supportive_stock,
            code="600002",
            name="支持",
            signal={
                **signal().signal,
                "identity_key": supportive_stock,
                "direction": "buy",
            },
        )
        adverse = replace(
            signal(
                event_id="evt-adverse",
                episode="episode-adverse",
                direction="sell",
                projection_id=102,
            ),
            identity_key=adverse_stock,
            code="600001",
            name="逆势",
            signal={
                **signal(direction="sell").signal,
                "identity_key": adverse_stock,
            },
        )
        board = membership("board")
        memberships = [
            replace(board, stock_identity_key=supportive_stock),
            replace(board, stock_identity_key=adverse_stock),
        ]
        heat = parent_event(
            "index",
            identity_key="index:SH:000001",
            code="000001",
            name="上证指数",
            event_id="evt-market-heat-buy",
            direction="buy",
        )
        second_heat = parent_event(
            "index",
            identity_key="index:SZ:399001",
            code="399001",
            name="深证成指",
            event_id="evt-market-heat-sz-buy",
            direction="buy",
        )
        rows = evaluate_strategy_center(
            trade_date=TRADE_DATE,
            selected_package_keys=("package_2",),
            stock_signals=[adverse, supportive],
            scope_rows=[
                ScopeRow(TRADE_DATE, adverse_stock, "monitor"),
                ScopeRow(TRADE_DATE, supportive_stock, "monitor"),
            ],
            index_memberships=[],
            board_memberships=memberships,
            parent_executed_events=[
                parent_event("board", event_id="evt-board-buy", direction="buy"),
                parent_event("board", event_id="evt-board-sell", direction="sell"),
                heat,
                second_heat,
            ],
            membership_authorities=membership_authorities_for(
                [adverse, supportive]
            ),
        )
        self.assertEqual(
            [row.stock_identity_key for row in rows],
            [supportive_stock, adverse_stock],
        )
        self.assertEqual(
            [
                row.confluence["market_heat_state"]
                for row in rows
            ],
            ["MARKET_HEAT_SUPPORTIVE", "MARKET_HEAT_ADVERSE"],
        )
        for row in rows:
            audit = row.confluence
            self.assertFalse(audit["proposal_authorized"])
            self.assertFalse(audit["order_authorized"])
            self.assertFalse(audit["trade_authorized"])
            self.assertFalse(audit["position_or_cash_mutation_authorized"])

    def test_exact_seven_index_membership_allowlist(self) -> None:
        allowed = (
            ("index:SH:000016", "000016"),
            ("index:SH:000300", "000300"),
            ("index:SH:000688", "000688"),
            ("index:SH:000852", "000852"),
            ("index:SH:000905", "000905"),
            ("index:SZ:399006", "399006"),
            ("index:SZ:399303", "399303"),
        )
        for identity_key, code in allowed:
            with self.subTest(identity_key=identity_key):
                index_row = membership(
                    "index", identity_key=identity_key, code=code, name=code
                )
                rows = evaluate(
                    index_memberships=[index_row],
                    parent_events=[
                        parent_event(
                            "index",
                            identity_key=identity_key,
                            code=code,
                            name=code,
                        ),
                        parent_event("board"),
                    ],
                    packages=("package_1",),
                )
                self.assertEqual(rows[0].matched_packages, ("package_1",))

        unsupported = membership(
            "index",
            identity_key="index:SH:999999",
            code="999999",
            name="unsupported",
        )
        parents = [
            parent_event(
                "index",
                identity_key="index:SH:999999",
                code="999999",
                name="unsupported",
            ),
            parent_event("board"),
        ]
        self.assertEqual(
            evaluate(
                index_memberships=[unsupported],
                parent_events=parents,
                packages=("package_1",),
            ),
            (),
        )
        self.assertEqual(
            evaluate(
                index_memberships=[unsupported],
                parent_events=parents,
                packages=("package_2",),
            )[0].matched_packages,
            ("package_2",),
        )
        self.assertEqual(
            evaluate(
                parent_events=[
                    replace(parent_event("index"), direction=""),
                    parent_event("board"),
                ],
                packages=("package_1",),
            ),
            (),
        )
        self.assertEqual(
            evaluate(
                stock_signals=[signal(direction="")],
                parent_events=[parent_event("index"), parent_event("board")],
            ),
            (),
        )

    def test_package_2_can_match_without_index_mapping_and_marks_quality(self) -> None:
        rows = evaluate(
            index_memberships=[],
            parent_events=[parent_event("board")],
            packages=("package_2",),
        )
        self.assertEqual(rows[0].indices, ())
        self.assertEqual(rows[0].mapping_quality, "missing_index")
        self.assertEqual(
            [item["membership_kind"] for item in rows[0].membership_provenance],
            ["board", "index"],
        )
        self.assertTrue(
            all(
                item["provenance_status"] == "authoritative_as_of"
                and item["quality_status"] == "passed"
                for item in rows[0].membership_provenance
            )
        )

    def test_missing_authority_fails_closed_without_tempting_fallbacks(self) -> None:
        self.assertEqual(
            evaluate(
                parent_events=[parent_event("board")],
                packages=("package_2",),
                membership_authorities=None,
            ),
            (),
        )
        partial_authority = membership_authorities_for([signal()])[:1]
        self.assertEqual(
            evaluate(
                parent_events=[parent_event("board")],
                packages=("package_2",),
                membership_authorities=partial_authority,
            ),
            (),
        )
        no_episode = replace(signal(), action_episode_key="")
        self.assertEqual(
            evaluate(
                stock_signals=[no_episode],
                parent_events=[parent_event("index"), parent_event("board")],
            ),
            (),
        )
        missing_parent_name = replace(parent_event("board"), name="")
        self.assertEqual(
            evaluate(parent_events=[parent_event("index"), missing_parent_name]),
            (),
        )
        missing_membership_version = membership("board", source_version="")
        self.assertEqual(
            evaluate(
                board_memberships=[missing_membership_version],
                parent_events=[parent_event("index"), parent_event("board")],
            ),
            (),
        )

    def test_any_invalid_selected_membership_row_fails_closed(self) -> None:
        invalid_index = membership("index", source_version="")
        self.assertEqual(
            evaluate(
                index_memberships=[invalid_index],
                parent_events=[parent_event("board")],
                packages=("package_2",),
            ),
            (),
        )
        invalid_board = membership("board", board_type="tdx_other")
        self.assertEqual(
            evaluate(
                board_memberships=[membership("board"), invalid_board],
                parent_events=[parent_event("board")],
                packages=("package_2",),
            ),
            (),
        )
        missing_index_rows = evaluate(
            index_memberships=[],
            parent_events=[parent_event("board")],
            packages=("package_2",),
        )
        self.assertEqual(len(missing_index_rows), 1)
        self.assertEqual(missing_index_rows[0].mapping_quality, "missing_index")

    def test_membership_rows_must_match_authority_version_and_batch(self) -> None:
        mismatched_version = membership(
            "board", source_version="unapproved-membership-version"
        )
        self.assertEqual(
            evaluate(
                board_memberships=[mismatched_version],
                parent_events=[parent_event("board")],
                packages=("package_2",),
            ),
            (),
        )
        mismatched_batch = replace(
            membership("board"),
            source_batch_id="unapproved-membership-batch",
        )
        self.assertEqual(
            evaluate(
                board_memberships=[mismatched_batch],
                parent_events=[parent_event("board")],
                packages=("package_2",),
            ),
            (),
        )

    def test_exact_trade_date_is_required_for_signal_membership_and_parent(self) -> None:
        wrong_day = "20260720"
        self.assertEqual(
            evaluate(
                stock_signals=[signal(trade_date=wrong_day)],
                parent_events=[parent_event("index"), parent_event("board")],
            ),
            (),
        )
        self.assertEqual(
            evaluate(
                index_memberships=[membership("index", trade_date=wrong_day)],
                parent_events=[parent_event("index"), parent_event("board")],
            )[0].matched_packages,
            ("package_2",),
        )
        self.assertEqual(
            evaluate(
                parent_events=[
                    parent_event("index", trade_date=wrong_day),
                    parent_event("board", trade_date=wrong_day),
                ]
            ),
            (),
        )

    def test_later_executed_updates_state_without_reselecting_frozen_evidence(self) -> None:
        eligible = signal()
        executed = signal(
            state="executed",
            event_id="evt-stock-executed",
            event_time="2026-07-21T10:10:00+08:00",
            projection_id=102,
        )
        parents = [
            parent_event("index", event_time="2026-07-21T10:00:00+08:00"),
            parent_event("board", event_time="2026-07-21T10:01:00+08:00"),
        ]
        eligible_only = evaluate(stock_signals=[eligible], parent_events=parents)
        first = evaluate(
            stock_signals=[eligible, executed],
            parent_events=parents,
            frozen_matches=eligible_only,
        )
        replay = evaluate(
            stock_signals=[executed, eligible, eligible],
            parent_events=list(reversed(parents)),
            frozen_matches=eligible_only,
        )
        self.assertEqual(len(first), 1)
        self.assertEqual(first, replay)
        self.assertEqual(first[0].action_state, "executed")
        self.assertEqual(first[0].source_signal_projection_id, 102)
        self.assertIn(executed.event_id, first[0].source_event_ids)
        self.assertEqual(
            [item["action_state"] for item in first[0].state_timeline],
            ["eligible", "executed"],
        )
        self.assertEqual(
            first[0].coherence_episode_key,
            eligible_only[0].coherence_episode_key,
        )
        self.assertEqual(
            first[0].confluence["package_evidence"],
            eligible_only[0].confluence["package_evidence"],
        )
        self.assertEqual(len(first[0].projection_hash), 64)
        self.assertEqual(first[0].evaluator_policy_hash, EVALUATOR_POLICY_HASH)
        self.assertEqual(
            first[0].confluence["evaluator_policy_hash"],
            EVALUATOR_POLICY_HASH,
        )

    def test_minimum_span_freezes_projection_at_selected_confirmation(
        self,
    ) -> None:
        eligible = signal(
            event_id="evt-stock-eligible-0930",
            event_time="2026-07-21T09:30:00+08:00",
            projection_id=101,
        )
        executed = signal(
            state="executed",
            event_id="evt-stock-executed-1010",
            event_time="2026-07-21T10:10:00+08:00",
            projection_id=102,
        )
        board = parent_event(
            "board",
            event_id="evt-board-0931",
            event_time="2026-07-21T09:31:00+08:00",
        )
        first = evaluate(
            stock_signals=[eligible, executed],
            parent_events=[board],
            packages=("package_2",),
        )
        replay = evaluate(
            stock_signals=[executed, eligible, eligible],
            parent_events=[board, board],
            packages=("package_2",),
        )
        without_future = evaluate(
            stock_signals=[eligible],
            parent_events=[board],
            packages=("package_2",),
        )
        self.assertEqual(first, replay)
        self.assertEqual(first[0].action_state, "executed")
        self.assertEqual(first[0].source_signal_projection_id, 102)
        self.assertEqual(first[0].signal["action_state"], "executed")
        self.assertIn(executed.event_id, first[0].source_event_ids)
        self.assertEqual(
            [item["event_id"] for item in first[0].state_timeline],
            [eligible.event_id, executed.event_id],
        )
        self.assertEqual(
            first[0].coherence_episode_key,
            without_future[0].coherence_episode_key,
        )
        audit = first[0].confluence
        self.assertEqual(audit["coherence_span_trading_minutes"], 1)
        self.assertEqual(audit["confirmation_time"], board.event_time)
        self.assertEqual(
            audit["package_evidence"][0]["stock_event_id"],
            eligible.event_id,
        )
        self.assertEqual(
            audit["package_evidence"],
            without_future[0].confluence["package_evidence"],
        )

        later_board = parent_event(
            "board",
            event_id="evt-board-1011",
            event_time="2026-07-21T10:11:00+08:00",
        )
        self.assertEqual(
            evaluate(
                stock_signals=[eligible, executed],
                parent_events=[board, later_board],
                packages=("package_2",),
                evaluation_time="2026-07-21T10:11:00+08:00",
            ),
            (),
        )

        new_episode_executed = replace(
            executed,
            event_id="evt-stock-executed-new-episode",
            action_episode_key="evt-n4-entry-new",
            user_signal_projection_id=103,
        )
        upgraded = evaluate(
            stock_signals=[eligible, executed, new_episode_executed],
            parent_events=[board, later_board],
            packages=("package_2",),
            evaluation_time="2026-07-21T10:11:00+08:00",
        )[0]
        self.assertEqual(upgraded.action_state, "executed")
        self.assertEqual(upgraded.action_episode_key, "evt-n4-entry-new")
        self.assertEqual(upgraded.source_signal_projection_id, 103)
        self.assertEqual(upgraded.signal["action_state"], "executed")
        upgraded_audit = upgraded.confluence
        self.assertEqual(
            upgraded_audit["package_evidence"][0]["stock_event_id"],
            new_episode_executed.event_id,
        )

    def test_package_two_then_package_one_create_distinct_confirmation_episodes(self) -> None:
        stock = signal(event_time="2026-07-21T10:00:00+08:00")
        board = parent_event(
            "board",
            event_time="2026-07-21T10:00:00+08:00",
        )
        index = parent_event(
            "index",
            event_time="2026-07-21T10:05:00+08:00",
        )
        rows = evaluate(
            stock_signals=[stock],
            parent_events=[index, board],
            evaluation_time="2026-07-21T10:05:00+08:00",
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            [row.matched_packages for row in rows],
            [("package_2",), ("package_1",)],
        )
        self.assertEqual(
            [row.confluence["confirmation_time"] for row in rows],
            [board.event_time, index.event_time],
        )
        self.assertEqual(len({row.coherence_episode_key for row in rows}), 2)

    def test_same_confirmation_merges_packages_and_signal_dto_stays_canonical(self) -> None:
        stock = signal(event_time="2026-07-21T10:00:00+08:00")
        parents = [
            parent_event("index", event_time=stock.event_time),
            parent_event("board", event_time=stock.event_time),
        ]
        rows = evaluate(stock_signals=[stock], parent_events=parents)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].matched_packages, ("package_1", "package_2"))
        self.assertEqual(rows[0].signal, stock.signal)
        self.assertNotIn("strategy_center_temporal_confluence", rows[0].signal)
        self.assertEqual(
            [item["package"] for item in rows[0].confluence["package_evidence"]],
            ["package_1", "package_2"],
        )

    def test_same_confirmation_mixed_levels_use_one_qualified_surface(self) -> None:
        stock = signal(event_time="2026-07-21T10:30:00+08:00")
        result = evaluate_strategy_center_versioned(
            strategy_version="N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2",
            trade_date=TRADE_DATE,
            selected_package_keys=("package_1", "package_2"),
            stock_signals=(stock,),
            scope_rows=(ScopeRow(TRADE_DATE, STOCK, "monitor"),),
            index_memberships=(membership("index"),),
            board_memberships=(membership("board"),),
            parent_executed_events=(
                parent_event(
                    "index",
                    event_time="2026-07-21T09:35:00+08:00",
                ),
                parent_event(
                    "board",
                    event_time="2026-07-21T10:30:00+08:00",
                ),
            ),
            membership_authorities=membership_authorities_for([stock]),
            evaluation_time="2026-07-21T10:30:00+08:00",
        )
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.observations, ())
        row = result.matches[0]
        self.assertEqual(row.matched_packages, ("package_2",))
        self.assertEqual(
            [
                (item["package"], item["coherence_level"])
                for item in row.confluence["package_evidence"]
            ],
            [("package_1", "WEAK"), ("package_2", "STRONG")],
        )
        self.assertEqual(row.confluence["qualified_packages"], ["package_2"])
        self.assertEqual(
            row.confluence["observation_packages"], ["package_1"]
        )

    def test_late_market_heat_does_not_rewrite_frozen_episode(self) -> None:
        stock = signal(event_time="2026-07-21T10:00:00+08:00")
        board = parent_event(
            "board",
            event_time="2026-07-21T09:55:00+08:00",
            projection_id=201,
        )
        heat = parent_event(
            "index",
            identity_key="index:SH:000001",
            code="000001",
            name="上证指数",
            event_id="evt-heat-initial",
            event_time="2026-07-21T09:58:00+08:00",
            projection_id=202,
        )
        first = evaluate(
            stock_signals=[stock],
            parent_events=[board, heat],
            packages=("package_2",),
            evaluation_time="2026-07-21T10:00:00+08:00",
        )
        late_heat = parent_event(
            "index",
            identity_key="index:SH:000001",
            code="000001",
            name="上证指数",
            event_id="evt-heat-late",
            event_time="2026-07-21T09:59:00+08:00",
            direction="sell",
            projection_id=203,
        )
        refreshed = evaluate(
            stock_signals=[stock],
            parent_events=[board, heat, late_heat],
            packages=("package_2",),
            evaluation_time="2026-07-21T10:00:00+08:00",
            frozen_matches=first,
        )
        self.assertEqual(refreshed, first)
        self.assertNotIn(late_heat.event_id, refreshed[0].source_event_ids)

    def test_late_arriving_earlier_parent_creates_successive_episode(self) -> None:
        stock = signal(event_time="2026-07-21T10:00:00+08:00")
        first_parent = parent_event(
            "board",
            event_id="evt-board-first-arrival",
            event_time="2026-07-21T10:00:00+08:00",
            projection_id=201,
        )
        first = evaluate(
            stock_signals=[stock],
            parent_events=[first_parent],
            packages=("package_2",),
            evaluation_time="2026-07-21T10:00:00+08:00",
        )
        late_earlier = parent_event(
            "board",
            event_id="evt-board-late-earlier",
            event_time="2026-07-21T09:59:00+08:00",
            projection_id=202,
        )
        replay = evaluate(
            stock_signals=[stock],
            parent_events=[late_earlier, first_parent],
            packages=("package_2",),
            evaluation_time="2026-07-21T10:00:00+08:00",
            frozen_matches=first,
        )
        self.assertEqual(len(replay), 2)
        self.assertEqual(replay[0], first[0])
        self.assertNotEqual(
            replay[0].coherence_episode_key,
            replay[1].coherence_episode_key,
        )
        self.assertEqual(
            replay[1].confluence["parent_projection_arrival_watermark"],
            202,
        )

    def test_batch_and_incremental_parent_arrivals_replay_identically(self) -> None:
        stock = signal(
            event_time="2026-07-21T10:00:00+08:00",
            projection_id=100,
        )
        board_1 = parent_event(
            "board",
            event_id="evt-board-arrival-101",
            event_time=stock.event_time,
            projection_id=101,
        )
        board_2 = parent_event(
            "board",
            event_id="evt-board-arrival-102",
            event_time=stock.event_time,
            projection_id=102,
        )
        index_1 = parent_event(
            "index",
            event_id="evt-index-arrival-103",
            event_time=stock.event_time,
            projection_id=103,
        )
        common = {
            "strategy_version": "N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2",
            "trade_date": TRADE_DATE,
            "selected_package_keys": ("package_1", "package_2"),
            "stock_signals": (stock,),
            "scope_rows": (ScopeRow(TRADE_DATE, STOCK, "monitor"),),
            "index_memberships": (membership("index"),),
            "board_memberships": (membership("board"),),
            "membership_authorities": membership_authorities_for([stock]),
            "evaluation_time": stock.event_time,
        }
        batch = evaluate_strategy_center_versioned(
            **common,
            parent_executed_events=(board_1, board_2, index_1),
        )
        tick_1 = evaluate_strategy_center_versioned(
            **common,
            parent_executed_events=(board_1,),
        )
        tick_2 = evaluate_strategy_center_versioned(
            **common,
            parent_executed_events=(board_1, board_2),
            frozen_matches=tick_1.matches,
        )
        tick_3 = evaluate_strategy_center_versioned(
            **common,
            parent_executed_events=(board_1, board_2, index_1),
            frozen_matches=tick_2.matches,
        )
        self.assertEqual(batch, tick_3)
        self.assertEqual(batch.observations, ())
        self.assertEqual(
            [
                (
                    row.matched_packages,
                    row.confluence["projection_arrival_watermark"],
                )
                for row in batch.matches
            ],
            [
                (("package_2",), 101),
                (("package_2",), 102),
                (("package_1",), 103),
            ],
        )
        self.assertEqual(
            len({row.projection_hash for row in batch.matches}),
            3,
        )

    def test_stock_arrival_simultaneously_qualifies_both_packages(self) -> None:
        stock = signal(
            event_time="2026-07-21T10:00:00+08:00",
            projection_id=103,
        )
        board = parent_event(
            "board",
            event_id="evt-board-arrival-101-before-stock",
            event_time=stock.event_time,
            projection_id=101,
        )
        index = parent_event(
            "index",
            event_id="evt-index-arrival-102-before-stock",
            event_time=stock.event_time,
            projection_id=102,
        )
        result = evaluate_strategy_center_versioned(
            strategy_version="N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2",
            trade_date=TRADE_DATE,
            selected_package_keys=("package_1", "package_2"),
            stock_signals=(stock,),
            scope_rows=(ScopeRow(TRADE_DATE, STOCK, "monitor"),),
            index_memberships=(membership("index"),),
            board_memberships=(membership("board"),),
            parent_executed_events=(board, index),
            membership_authorities=membership_authorities_for([stock]),
            evaluation_time=stock.event_time,
        )
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.observations, ())
        row = result.matches[0]
        self.assertEqual(
            row.matched_packages,
            ("package_1", "package_2"),
        )
        self.assertEqual(
            row.confluence["projection_arrival_watermark"],
            103,
        )
        self.assertEqual(
            row.confluence["parent_projection_arrival_watermark"],
            102,
        )
        self.assertEqual(
            [item["package"] for item in row.confluence["package_evidence"]],
            ["package_1", "package_2"],
        )

    def test_frozen_fresh_episode_moves_atomically_to_observation_surface(self) -> None:
        stock = signal(event_time="2026-07-21T10:00:00+08:00")
        board = parent_event("board", event_time=stock.event_time)
        common = {
            "strategy_version": "N6_STRATEGY_CENTER_TEMPORAL_CONFLUENCE_V2",
            "trade_date": TRADE_DATE,
            "selected_package_keys": ("package_2",),
            "stock_signals": (stock,),
            "scope_rows": (ScopeRow(TRADE_DATE, STOCK, "monitor"),),
            "index_memberships": (membership("index"),),
            "board_memberships": (membership("board"),),
            "parent_executed_events": (board,),
            "membership_authorities": membership_authorities_for([stock]),
        }
        initial = evaluate_strategy_center_versioned(
            **common,
            evaluation_time="2026-07-21T10:30:00+08:00",
        )
        transitioned = evaluate_strategy_center_versioned(
            **common,
            evaluation_time="2026-07-21T10:30:01+08:00",
            frozen_matches=initial.matches,
        )
        self.assertEqual(len(initial.matches), 1)
        self.assertEqual(initial.observations, ())
        self.assertEqual(transitioned.matches, ())
        self.assertEqual(len(transitioned.observations), 1)
        self.assertEqual(
            transitioned.observations[0].coherence_episode_key,
            initial.matches[0].coherence_episode_key,
        )
        self.assertEqual(
            transitioned.observations[0].observation_reason,
            "stale_after_confirmation",
        )

    def test_fresh_candidate_moves_to_generic_stale_observation_after_30_minutes(self) -> None:
        stock = signal(event_time="2026-07-21T10:00:00+08:00")
        board = parent_event("board", event_time=stock.event_time)
        kwargs = {
            "trade_date": TRADE_DATE,
            "selected_package_keys": ("package_2",),
            "stock_signals": [stock],
            "scope_rows": [ScopeRow(TRADE_DATE, STOCK, "monitor")],
            "index_memberships": [membership("index")],
            "board_memberships": [membership("board")],
            "parent_executed_events": [board],
            "membership_authorities": membership_authorities_for([stock]),
        }
        self.assertEqual(
            len(
                evaluate_strategy_center(
                    **kwargs,
                    evaluation_time="2026-07-21T10:30:00+08:00",
                )
            ),
            1,
        )
        self.assertEqual(
            evaluate_strategy_center(
                **kwargs,
                evaluation_time="2026-07-21T10:30:01+08:00",
            ),
            (),
        )
        observations = evaluate_strategy_center_observations(
            **kwargs,
            evaluation_time="2026-07-21T15:00:00+08:00",
        )
        self.assertEqual(len(observations), 1)
        self.assertEqual(
            observations[0].observation_reason,
            "stale_after_confirmation",
        )
        self.assertEqual(
            observations[0].confluence["freshness_status"],
            "stale",
        )

    def test_v1_dispatch_preserves_whole_day_directionless_semantics(self) -> None:
        stock = signal(direction="buy", event_time="2026-07-21T12:00:00+08:00")
        board = parent_event(
            "board",
            direction="sell",
            event_time="2026-07-21T12:01:00+08:00",
        )
        result = evaluate_strategy_center_versioned(
            strategy_version=STRATEGY_VERSION_V1,
            trade_date=TRADE_DATE,
            selected_package_keys=("package_2",),
            stock_signals=[stock],
            scope_rows=[ScopeRow(TRADE_DATE, STOCK, "monitor")],
            index_memberships=[membership("index")],
            board_memberships=[membership("board")],
            parent_executed_events=[board],
            membership_authorities=membership_authorities_for([stock]),
            evaluation_time="2026-07-21T13:00:00+08:00",
        )
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.matches[0].matched_packages, ("package_2",))
        self.assertEqual(
            result.matches[0].confluence["strategy_version"],
            STRATEGY_VERSION_V1,
        )
        self.assertFalse(
            result.matches[0].confluence["direction_match_required"]
        )
        self.assertEqual(result.observations, ())

    def test_new_episode_is_independent_and_replay_remains_idempotent(self) -> None:
        first_episode = signal()
        second_episode = signal(
            episode="evt-n4-entry-2",
            event_id="evt-stock-episode-2",
            event_time="2026-07-21T09:41:00+08:00",
            projection_id=102,
        )
        parents = [parent_event("index"), parent_event("board")]
        rows = evaluate(
            stock_signals=[second_episode, first_episode, second_episode],
            parent_events=list(reversed(parents)),
        )
        replay = evaluate(
            stock_signals=[first_episode, second_episode],
            parent_events=parents,
        )
        self.assertEqual(rows, replay)
        self.assertEqual(
            [row.action_episode_key for row in rows],
            [EPISODE, "evt-n4-entry-2"],
        )

    def test_conflicting_duplicate_event_id_fails_closed(self) -> None:
        original = signal()
        polluted = replace(original, code="999999")
        self.assertEqual(
            evaluate(
                stock_signals=[original, polluted],
                parent_events=[parent_event("index"), parent_event("board")],
            ),
            (),
        )

    def test_conflicting_parent_event_id_fails_closed(self) -> None:
        index_event = parent_event("index")
        board_event = parent_event("board")
        polluted_board_event = replace(board_event, name="污染板块名")
        rows = evaluate(
            parent_events=[index_event, board_event, polluted_board_event]
        )
        self.assertEqual(rows, ())

        duplicate_rows = evaluate(
            parent_events=[index_event, board_event, board_event]
        )
        self.assertEqual(
            duplicate_rows[0].matched_packages,
            ("package_1", "package_2"),
        )

    def test_scope_union_preserves_all_three_sources_in_stable_order(self) -> None:
        rows = evaluate_strategy_center(
            trade_date=TRADE_DATE,
            selected_package_keys=("package_2",),
            stock_signals=[signal()],
            scope_rows=[
                ScopeRow(TRADE_DATE, STOCK, "virtual_position"),
                ScopeRow(TRADE_DATE, STOCK, "monitor"),
                ScopeRow(TRADE_DATE, STOCK, "realtime_scope"),
            ],
            index_memberships=[],
            board_memberships=[membership("board")],
            parent_executed_events=[parent_event("board")],
            membership_authorities=membership_authorities_for([signal()]),
        )
        self.assertEqual(
            rows[0].scope_sources,
            ("monitor", "realtime_scope", "virtual_position"),
        )


class StrategyCenterRepositoryContractTest(unittest.TestCase):
    def test_positive_authority_queries_only_n6_delivered_projection_and_views(self) -> None:
        combined = "\n".join(
            (
                SCOPE_ROWS_SQL,
                PARENT_EXECUTED_SIGNAL_IDS_SQL,
                SIGNAL_AUTHORITY_ROWS_SQL,
                INDEX_MEMBERSHIP_ROWS_SQL,
                BOARD_MEMBERSHIP_ROWS_SQL,
            )
        ).lower()
        for required in (
            "from user_signal_projection",
            "from user_monitor_stock",
            "from user_realtime_monitor_scope",
            "from n6_virtual_account",
            "join n6_virtual_position",
            "from v_n6_index_membership_fact",
            "from v_n6_board_membership_fact",
            "valid_for_trade_date",
            "p.quantity > 0",
            "p.position_status = 'open_virtual'",
            "action_entry_trigger_matched_ref",
        ):
            self.assertIn(required, combined)
        self.assertNotIn("m.direction = 'buy'", combined)

    def test_signal_authority_uses_typed_date_and_slim_event_time(self) -> None:
        sql = SIGNAL_AUTHORITY_ROWS_SQL.lower()
        self.assertIn(
            "p.for_trade_date = pg_catalog.to_date(%(trade_date)s, 'yyyymmdd')",
            sql,
        )
        self.assertIn(
            "pg_catalog.to_char(p.for_trade_date, 'yyyymmdd') as trade_date",
            sql,
        )
        self.assertIn("p.source_payload_json->>'event_time'", sql)
        self.assertIn("as source_event_time", sql)
        self.assertIn("as projection_event_time", sql)
        self.assertIn("as source_direction", sql)
        self.assertIn("as projection_direction", sql)
        self.assertNotIn("p.created_at", sql)
        self.assertNotIn("join user_signal_card", sql)
        self.assertNotIn("card_payload_json", sql)
        self.assertNotIn("display_payload_json", sql)
        self.assertNotIn("->>'trade_date'", sql)

    def test_signal_authority_preserves_canonical_episode_source(self) -> None:
        sql = SIGNAL_AUTHORITY_ROWS_SQL.lower()
        self.assertIn("action_entry_trigger_matched_ref", sql)
        self.assertIn("p.source_payload_json", sql)
        self.assertIn("p.trace_json", sql)
        self.assertNotIn("list_payload_json->>'n4_trigger_event_id'", sql)

    def test_signal_authority_downpushes_exact_ids_and_parent_state(self) -> None:
        authority_sql = " ".join(SIGNAL_AUTHORITY_ROWS_SQL.lower().split())
        parent_sql = " ".join(
            PARENT_EXECUTED_SIGNAL_IDS_SQL.lower().split()
        )
        self.assertIn(
            "p.user_signal_projection_id = any(%(projection_ids)s)",
            authority_sql,
        )
        self.assertIn("p.user_id = %(user_id)s", authority_sql)
        self.assertIn("p.user_id = %(user_id)s", parent_sql)
        self.assertIn("p.action_state = 'executed'", parent_sql)
        self.assertNotIn("'eligible'", parent_sql)

        class Cursor:
            def __init__(self) -> None:
                self.params = {}

            def execute(self, _query, params) -> None:
                self.params = params

            def fetchall(self):
                return []

        cursor = Cursor()
        rows = N6StrategyCenterReadRepository.fetch_signal_authority_rows(
            cursor,
            user_id=11,
            trade_date=TRADE_DATE,
            projection_ids=[103, 101, 103],
        )
        self.assertEqual(rows, [])
        self.assertEqual(cursor.params["projection_ids"], [101, 103])

    def test_negative_pollution_and_write_paths_are_absent(self) -> None:
        repository_path = (
            Path(__file__).resolve().parents[1]
            / "src/ashare_v3/user/strategy_center_repository.py"
        )
        text = repository_path.read_text(encoding="utf-8").lower()
        for forbidden in (
            "common_action_event",
            "stock_action_confirmation",
            "index_action_confirmation",
            "board_action_confirmation",
            "common_event_outbox",
            "source_event_dedup_key",
            "n6_virtual_trade_proposal",
            " insert ",
            " update ",
            " delete ",
        ):
            self.assertNotIn(forbidden, text)
        self.assertNotIn("tdx_other", BOARD_MEMBERSHIP_ROWS_SQL)
        self.assertNotIn("source_trigger_event_id', '')\n+       ) as action_episode_key", SIGNAL_AUTHORITY_ROWS_SQL.lower())

    def test_repository_executes_select_with_user_and_principal_scope(self) -> None:
        class Cursor:
            def __init__(self) -> None:
                self.query = ""
                self.params = {}

            def execute(self, query, params):
                self.query = query
                self.params = params

            def fetchall(self):
                return [{"trade_date": TRADE_DATE, "stock_identity_key": STOCK, "scope_source": "monitor"}]

        cursor = Cursor()
        rows = N6StrategyCenterReadRepository.fetch_scope_rows(
            cursor,
            principal_id=7,
            principal_type="human_user",
            user_id=11,
            trade_date=TRADE_DATE,
        )
        self.assertEqual(rows[0]["scope_source"], "monitor")
        self.assertEqual(
            cursor.params,
            {
                "principal_id": 7,
                "principal_type": "human_user",
                "user_id": 11,
                "trade_date": TRADE_DATE,
            },
        )
        self.assertTrue(cursor.query.lstrip().upper().startswith("WITH"))


if __name__ == "__main__":
    unittest.main()
