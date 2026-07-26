from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch
import json
import unittest

import psycopg
from psycopg.rows import dict_row

from ashare_v3.user.strategy_center import (
    APPROVED_PACKAGE_POLICY_HASHES,
    APPROVED_PACKAGE_POLICY_PAYLOADS,
    MembershipRow,
    MembershipSnapshotAuthority,
    ParentExecutedEvent,
    ScopeRow,
    StockSignalEvent,
)
from ashare_v3.user.strategy_center_worker import (
    AUTO_EVALUATION_SCOPES_SQL,
    AUTO_SOURCE_WATERMARKS_SQL,
    AUTO_TRADE_DATE_SQL,
    DATABASE_LOCK_TIMEOUT_MS,
    DATABASE_STATEMENT_TIMEOUT_MS,
    EvaluationInput,
    N6DisplayBatchAuthority,
    N6TradeDateAuthority,
    N6_TRADE_DATE_AUTHORITY_SQL,
    PostgresStrategyCenterEvaluatorRepository,
    READ_ONLY_CONNECTION_OPTIONS,
    SelectionWorkItem,
    StrategyCenterWorkerBlocked,
    StrategyEvaluatorScope,
    WRITE_CONNECTION_OPTIONS,
    WorkerSnapshot,
    WORK_ITEMS_SQL,
    _v2_standard_event_authority,
    _raise_database_timeout,
    build_worker_plan,
    n6_trade_date_authority,
    run_strategy_center_once,
    selection_cas_hash,
    snapshot_hash,
)
from ashare_v3.user.strategy_center_repository import (
    N6StrategyCenterReadRepository,
    SIGNAL_AUTHORITY_ROWS_SQL,
)
from ashare_v3.web.n6_app_v1 import app_signal_item
from ashare_v3.web.n6_user_app import PostgresN6UserRepository
from scripts.run_n6_strategy_center_once import (
    build_parser,
    evaluator_scope_from_args,
    run_from_args,
    strict_positive_int,
    validate_worker_environment,
)
from tests.test_n6_strategy_worker_canonical_acl_079 import (
    _temporary_postgres,
)


TRADE_DATE = "20260722"
SOURCE_TRADE_DATE = "20260721"
EVALUATION_TIME = "2026-07-22T09:40:00+08:00"
STOCK = "stock:SH:600000"
BOUNDED_SCOPE = StrategyEvaluatorScope(
    principal_id=2,
    user_id=3,
    selection_revision_id=9,
)
PACKAGE_1_POLICY_HASH = APPROVED_PACKAGE_POLICY_HASHES["package_1"]
PACKAGE_2_POLICY_HASH = APPROVED_PACKAGE_POLICY_HASHES["package_2"]
PACKAGE_1_RULE_AUTHORITY = json.dumps(
    APPROVED_PACKAGE_POLICY_PAYLOADS["package_1"],
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)
PACKAGE_2_RULE_AUTHORITY = json.dumps(
    APPROVED_PACKAGE_POLICY_PAYLOADS["package_2"],
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)
N6_AUTHORITY_ROWS = (
    {
        "asset_kind": "stock",
        "source_trade_date": SOURCE_TRADE_DATE,
        "for_trade_date": TRADE_DATE,
        "source_run_id": "stock-display-run",
        "row_count": 1559,
    },
    {
        "asset_kind": "index",
        "source_trade_date": "20260720",
        "for_trade_date": TRADE_DATE,
        "source_run_id": "index-display-run",
        "row_count": 9,
    },
    {
        "asset_kind": "board",
        "source_trade_date": SOURCE_TRADE_DATE,
        "for_trade_date": TRADE_DATE,
        "source_run_id": "board-display-run",
        "row_count": 127,
    },
)
N6_AUTHORITY = n6_trade_date_authority(N6_AUTHORITY_ROWS)


def selection(status: str = "active") -> SelectionWorkItem:
    return SelectionWorkItem(
        selection_revision_id=9,
        principal_id=2,
        principal_type="human_user",
        user_id=3,
        revision_no=2,
        selection_status=status,
        replay_status="pending",
        previous_revision_id=8 if status == "pending" else None,
        active_revision_id=8 if status == "pending" else 9,
        selected_package_keys=("package_1", "package_2"),
        selected_package_versions=("v2", "v2"),
        selected_package_statuses=("active", "active"),
        effective_trade_date=TRADE_DATE,
        selection_immutable_authority="selection-authority-v1",
        selected_package_authority=(
            f"package_1|v2|{PACKAGE_1_POLICY_HASH}",
            f"package_2|v2|{PACKAGE_2_POLICY_HASH}",
        ),
        selected_package_rule_authority=(
            PACKAGE_1_RULE_AUTHORITY,
            PACKAGE_2_RULE_AUTHORITY,
        ),
        selection_lifecycle_authority=f"selection-lifecycle-{status}",
        active_revision_authority=(
            "active-revision-8" if status == "pending" else "active-revision-9"
        ),
    )


def evaluation_input(*, canonical_signal: bool = True) -> EvaluationInput:
    signal_dto = (
        {
            "user_signal_projection_id": "101",
            "identity_key": STOCK,
            "action_state": "eligible",
            "action_price": 10.12,
            "direction": "buy",
            "all_existing_signal_fields": "canonical-app-signal-item",
            "condition_projection_context": {
                "source_trade_date": SOURCE_TRADE_DATE,
            },
        }
        if canonical_signal
        else {}
    )
    stock = StockSignalEvent(
        user_signal_projection_id=101,
        trade_date=TRADE_DATE,
        identity_key=STOCK,
        code="600000",
        name="浦发银行",
        event_id="evt-stock-eligible",
        event_type="ActionEligible",
        action_state="eligible",
        event_time="2026-07-22T09:40:00+08:00",
        action_episode_key="evt-n4-entry",
        source_run_id="n5-run",
        event_schema_version="N5ActionEvent.v2",
        signal=signal_dto,
    )
    index_membership = MembershipRow(
        trade_date=SOURCE_TRADE_DATE,
        stock_identity_key=STOCK,
        parent_asset_kind="index",
        parent_identity_key="index:SH:000300",
        parent_code="000300",
        parent_name="沪深300",
        source_version="membership-v1",
        source_batch_id="membership-batch-1",
    )
    board_membership = MembershipRow(
        trade_date=SOURCE_TRADE_DATE,
        stock_identity_key=STOCK,
        parent_asset_kind="board",
        parent_identity_key="board:TDX:880001",
        parent_code="880001",
        parent_name="银行",
        source_version="membership-v1",
        source_batch_id="membership-batch-1",
        board_type="tdx_industry",
    )
    parents = (
        ParentExecutedEvent(
            trade_date=TRADE_DATE,
            asset_kind="index",
            identity_key="index:SH:000300",
            code="000300",
            name="沪深300",
            event_id="evt-index-executed",
            event_type="ActionExecuted",
            action_state="executed",
            event_time="2026-07-22T09:31:00+08:00",
            source_run_id="n5-run",
            event_schema_version="N5ActionEvent.v2",
            direction="buy",
            user_signal_projection_id=201,
        ),
        ParentExecutedEvent(
            trade_date=TRADE_DATE,
            asset_kind="board",
            identity_key="board:TDX:880001",
            code="880001",
            name="银行",
            event_id="evt-board-executed",
            event_type="ActionExecuted",
            action_state="executed",
            event_time="2026-07-22T09:32:00+08:00",
            source_run_id="n5-run",
            event_schema_version="N5ActionEvent.v2",
            direction="buy",
            user_signal_projection_id=202,
        ),
    )
    return EvaluationInput(
        selection=selection(),
        scope_rows=(ScopeRow(TRADE_DATE, STOCK, "monitor"),),
        stock_signals=(stock,),
        index_memberships=(index_membership,),
        board_memberships=(board_membership,),
        parent_executed_events=parents,
        membership_authorities=(
            membership_authority("index"),
            membership_authority("board"),
        ),
    )


def membership_authority(
    membership_kind: str,
    *,
    stock_identity_key: str = STOCK,
    episode: str = "evt-n4-entry",
    requested: str = SOURCE_TRADE_DATE,
    selected: str = SOURCE_TRADE_DATE,
    quality_status: str = "passed",
) -> MembershipSnapshotAuthority:
    return MembershipSnapshotAuthority(
        stock_identity_key=stock_identity_key,
        action_episode_key=episode,
        membership_kind=membership_kind,
        requested_source_trade_date=requested,
        selected_membership_trade_date=selected,
        source_version="membership-v1" if selected else "",
        source_batch_id="membership-batch-1" if selected else "",
        provenance_status=(
            "authoritative_as_of" if quality_status == "passed" else "unavailable"
        ),
        quality_status=quality_status,
    )


def snapshot(
    item: EvaluationInput | None = None,
    *,
    scope: StrategyEvaluatorScope | None = None,
    evaluation_time: str | None = None,
    trade_date_authority: N6TradeDateAuthority | None = None,
    source_watermarks: dict | None = None,
) -> WorkerSnapshot:
    value = item or evaluation_input()
    if scope is not None:
        value = replace(value, evaluator_scope=scope)
    inputs = (value,)
    if evaluation_time is None:
        evaluation_time = max(
            (
                event.event_time
                for event in (
                    *value.stock_signals,
                    *value.parent_executed_events,
                )
            ),
            default=EVALUATION_TIME,
        )
    return WorkerSnapshot(
        trade_date=TRADE_DATE,
        evaluation_time=evaluation_time,
        inputs=inputs,
        snapshot_hash=snapshot_hash(
            TRADE_DATE,
            inputs,
            evaluation_time=evaluation_time,
            scope=scope,
            trade_date_authority=trade_date_authority,
            source_watermarks=source_watermarks,
        ),
        evaluator_scope=scope,
        selection_cas_hash=selection_cas_hash(inputs),
        trade_date_authority=trade_date_authority,
        source_watermarks=source_watermarks,
    )


class FakeRepository:
    def __init__(self, value: WorkerSnapshot) -> None:
        self.value = value
        self.loads = []
        self.commits = []

    def load_snapshot(
        self,
        trade_date: str,
        *,
        scope: StrategyEvaluatorScope | None = None,
        evaluation_time: str | None = None,
    ) -> WorkerSnapshot:
        self.loads.append((trade_date, scope, evaluation_time))
        if trade_date != self.value.trade_date:
            raise AssertionError("unexpected trade date")
        if scope != self.value.evaluator_scope:
            raise AssertionError("unexpected evaluator scope")
        return self.value

    def commit_plan(self, plan):
        self.commits.append(plan)
        return {"committed": True, "upsert": 1, "remove": 0, "reset": 0}


class StrategyCenterWorkerTest(unittest.TestCase):
    @staticmethod
    def _work_item_row(**overrides):
        row = {
            "selection_revision_id": 9,
            "principal_id": 2,
            "principal_type": "human_user",
            "user_id": 3,
            "revision_no": 2,
            "selection_status": "active",
            "replay_status": "pending",
            "previous_revision_id": None,
            "active_revision_id": 9,
            "effective_trade_date": TRADE_DATE,
            "selected_package_keys": ["package_1", "package_2"],
            "selected_package_versions": ["v2", "v2"],
            "selected_package_statuses": ["active", "active"],
            "selected_package_authority": [
                f"package_1|v2|{PACKAGE_1_POLICY_HASH}",
                f"package_2|v2|{PACKAGE_2_POLICY_HASH}",
            ],
            "selected_package_rule_authority": [
                APPROVED_PACKAGE_POLICY_PAYLOADS["package_1"],
                APPROVED_PACKAGE_POLICY_PAYLOADS["package_2"],
            ],
        }
        row.update(overrides)
        return row

    @staticmethod
    def _worker_environment():
        return {
            "PGSERVICE": "n6_strategy_worker",
            "PGSERVICEFILE": "/private/config/pg_service.conf",
            "PGPASSFILE": "/private/config/worker.pgpass",
        }

    def test_cli_scope_contract_all_or_none_and_strict_positive_integers(self) -> None:
        parser = build_parser()
        base = [
            "--trade-date",
            TRADE_DATE,
            "--evaluator-run-id",
            "strategy-center-cli-contract",
        ]
        all_users = parser.parse_args(base)
        self.assertIsNone(evaluator_scope_from_args(all_users))

        bounded = parser.parse_args(
            base
            + [
                "--principal-id",
                "2",
                "--user-id",
                "3",
                "--selection-revision-id",
                "9",
            ]
        )
        self.assertEqual(evaluator_scope_from_args(bounded), BOUNDED_SCOPE)

        for missing_args in (
            ["--principal-id", "2", "--user-id", "3"],
            ["--principal-id", "2", "--selection-revision-id", "9"],
            ["--user-id", "3", "--selection-revision-id", "9"],
        ):
            with self.subTest(missing_args=missing_args), self.assertRaisesRegex(
                ValueError, "strategy_evaluator_scope_all_or_none_required"
            ):
                evaluator_scope_from_args(parser.parse_args(base + missing_args))

        for invalid in ("", "0", "-1", "1.0", "true", True):
            with self.subTest(invalid=invalid), self.assertRaises(
                Exception
            ):
                strict_positive_int(invalid)

    def test_runner_passes_explicit_scope_without_environment_inference(self) -> None:
        args = build_parser().parse_args(
            [
                "--trade-date",
                TRADE_DATE,
                "--evaluator-run-id",
                "strategy-center-cli-scope",
                "--principal-id",
                "2",
                "--user-id",
                "3",
                "--selection-revision-id",
                "9",
            ]
        )
        with patch.dict("os.environ", self._worker_environment(), clear=True), patch(
            "scripts.run_n6_strategy_center_once.PostgresStrategyCenterEvaluatorRepository"
        ) as repository_type, patch(
            "scripts.run_n6_strategy_center_once.run_strategy_center_once",
            return_value={"ok": True},
        ) as worker:
            self.assertEqual(run_from_args(args), {"ok": True})
        repository_type.assert_called_once_with("service=n6_strategy_worker")
        self.assertEqual(worker.call_args.kwargs["scope"], BOUNDED_SCOPE)

    def test_runner_passes_frozen_evaluation_time(self) -> None:
        args = build_parser().parse_args(
            [
                "--trade-date", TRADE_DATE,
                "--evaluator-run-id", "strategy-center-cli-time",
                "--principal-id", "2", "--user-id", "3",
                "--selection-revision-id", "9",
                "--evaluation-time", EVALUATION_TIME,
            ]
        )
        with patch.dict("os.environ", self._worker_environment(), clear=True), patch(
            "scripts.run_n6_strategy_center_once.PostgresStrategyCenterEvaluatorRepository"
        ), patch(
            "scripts.run_n6_strategy_center_once.run_strategy_center_once",
            return_value={"ok": True},
        ) as worker:
            self.assertEqual(run_from_args(args), {"ok": True})
        self.assertEqual(worker.call_args.kwargs["evaluation_time"], EVALUATION_TIME)

    def test_bounded_dry_run_and_execute_keep_authorization_gate(self) -> None:
        repository = FakeRepository(snapshot(scope=BOUNDED_SCOPE))
        dry_run = run_strategy_center_once(
            repository=repository,
            trade_date=TRADE_DATE,
            evaluator_run_id="strategy-center-bounded-dry",
            scope=BOUNDED_SCOPE,
        )
        self.assertEqual(dry_run["scope_mode"], "single_user_revision")
        self.assertEqual(dry_run["principal_id"], 2)
        self.assertEqual(dry_run["user_id"], 3)
        self.assertEqual(dry_run["selection_revision_id"], 9)
        self.assertEqual(repository.commits, [])

        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "strategy_evaluation_time_required_for_execute",
        ):
            run_strategy_center_once(
                repository=repository,
                trade_date=TRADE_DATE,
                evaluator_run_id="strategy-center-bounded-missing-time",
                scope=BOUNDED_SCOPE,
                execute=True,
                runtime_authorized=True,
            )
        self.assertEqual(repository.commits, [])

        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked, "runtime_authorization_required"
        ):
            run_strategy_center_once(
                repository=repository,
                trade_date=TRADE_DATE,
                evaluator_run_id="strategy-center-bounded-exec",
                scope=BOUNDED_SCOPE,
                execute=True,
            )
        self.assertEqual(repository.commits, [])

    def test_all_users_summary_remains_backward_compatible(self) -> None:
        result = run_strategy_center_once(
            repository=FakeRepository(snapshot()),
            trade_date=TRADE_DATE,
            evaluator_run_id="strategy-center-all-users",
        )
        self.assertEqual(result["scope_mode"], "all_users")
        self.assertNotIn("principal_id", result)

    def test_work_items_sql_downpushes_all_bound_scope_fields(self) -> None:
        normalized = " ".join(WORK_ITEMS_SQL.split()).lower()
        for predicate in (
            "revision.principal_id = %(principal_id)s",
            "revision.user_id = %(user_id)s",
            "revision.selection_revision_id = %(selection_revision_id)s",
            "revision.effective_trade_date <= to_date(%(trade_date)s, 'yyyymmdd')",
        ):
            self.assertIn(predicate, normalized)
        self.assertIn(
            "count(*) = ( select count(*) from n6_user_strategy_selection_item",
            normalized,
        )
        params = PostgresStrategyCenterEvaluatorRepository._scope_params(
            TRADE_DATE, BOUNDED_SCOPE
        )
        self.assertEqual(
            params,
            {
                "trade_date": TRADE_DATE,
                "scope_mode": "single_user_revision",
                "principal_id": 2,
                "user_id": 3,
                "selection_revision_id": 9,
            },
        )

    def test_work_items_sql_freezes_immutable_and_lifecycle_authority(self) -> None:
        with _temporary_postgres() as postgres:
            postgres.sql(
                """
                CREATE TABLE user_account (
                  user_id bigint PRIMARY KEY,
                  status text NOT NULL
                );
                CREATE TABLE n6_principal (
                  principal_id bigint PRIMARY KEY,
                  principal_type text NOT NULL,
                  owner_user_id bigint NOT NULL,
                  principal_status text NOT NULL
                );
                CREATE TABLE n6_user_strategy_selection_revision (
                  selection_revision_id bigint PRIMARY KEY,
                  principal_id bigint NOT NULL,
                  principal_type text NOT NULL,
                  user_id bigint NOT NULL,
                  revision_no bigint NOT NULL,
                  selection_status text NOT NULL,
                  replay_status text NOT NULL,
                  request_id text NOT NULL,
                  effective_trade_date date NOT NULL,
                  previous_revision_id bigint,
                  selection_policy_hash text NOT NULL,
                  created_by_user_id bigint NOT NULL,
                  selection_metadata_json jsonb NOT NULL,
                  created_at timestamptz NOT NULL,
                  activated_at timestamptz,
                  superseded_at timestamptz
                );
                CREATE TABLE n6_user_strategy_selection_item (
                  selection_revision_id bigint NOT NULL,
                  package_key text NOT NULL,
                  package_version text NOT NULL,
                  selected_at timestamptz NOT NULL
                );
                CREATE TABLE n6_strategy_package_catalog (
                  package_key text NOT NULL,
                  package_version text NOT NULL,
                  package_status text NOT NULL,
                  policy_hash text NOT NULL,
                  rule_json jsonb NOT NULL,
                  updated_at timestamptz NOT NULL,
                  PRIMARY KEY (package_key, package_version)
                );
                INSERT INTO user_account VALUES (3, 'active');
                INSERT INTO n6_principal VALUES
                  (2, 'human_user', 3, 'active');
                INSERT INTO n6_user_strategy_selection_revision VALUES
                  (8, 2, 'human_user', 3, 1, 'active', 'passed',
                   'request-8', DATE '2026-07-22', NULL, 'policy-8', 3,
                   '{}'::jsonb, '2026-07-22 09:00+08',
                   '2026-07-22 09:00+08', NULL),
                  (9, 2, 'human_user', 3, 2, 'pending', 'pending',
                   'request-9', DATE '2026-07-22', 8, 'policy-9', 3,
                   '{}'::jsonb, '2026-07-22 09:10+08', NULL, NULL);
                INSERT INTO n6_strategy_package_catalog VALUES
                  ('package_1', 'v2', 'active',
                   '70c44d41d045ddf4ccea9a692925eb56a0bf73f85389186d5ac89337c863d667',
                   '{"rule":"one"}'::jsonb, '2026-07-22 08:00+08'),
                  ('package_2', 'v2', 'active',
                   '51a81ff172d7d4de94dd1e677c0bc4ad56d516d924c2bcbb74ba8af3cbfc0ef8',
                   '{"rule":"two"}'::jsonb, '2026-07-22 08:00+08');
                INSERT INTO n6_user_strategy_selection_item VALUES
                  (9, 'package_1', 'v2', '2026-07-22 09:10+08'),
                  (9, 'package_2', 'v2', '2026-07-22 09:10+08');
                """
            )
            params = {
                **PostgresStrategyCenterEvaluatorRepository._scope_params(
                    TRADE_DATE, BOUNDED_SCOPE
                ),
                "selection_revision_ids": None,
            }
            dsn = (
                f"host={postgres.socket_dir} port={postgres.port} "
                "dbname=ashare_v3 user=ashare_v3_user"
            )
            with psycopg.connect(dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(WORK_ITEMS_SQL, params)
                    columns = [column.name for column in cursor.description]
                    pending = dict(zip(columns, cursor.fetchone()))
            postgres.sql(
                """
                UPDATE n6_user_strategy_selection_revision
                SET selection_status='superseded',
                    superseded_at='2026-07-22 10:00+08'
                WHERE selection_revision_id=8;
                UPDATE n6_user_strategy_selection_revision
                SET selection_status='active', replay_status='passed',
                    activated_at='2026-07-22 10:00+08'
                WHERE selection_revision_id=9;
                """
            )
            with psycopg.connect(dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(WORK_ITEMS_SQL, params)
                    columns = [column.name for column in cursor.description]
                    active = dict(zip(columns, cursor.fetchone()))

        self.assertEqual(
            pending["selection_immutable_authority"],
            active["selection_immutable_authority"],
        )
        self.assertEqual(
            pending["selected_package_authority"],
            active["selected_package_authority"],
        )
        self.assertEqual(
            pending["selected_package_rule_authority"],
            active["selected_package_rule_authority"],
        )
        self.assertNotEqual(
            pending["selection_lifecycle_authority"],
            active["selection_lifecycle_authority"],
        )
        self.assertNotEqual(
            pending["active_revision_authority"],
            active["active_revision_authority"],
        )

    def test_pending_primary_and_active_replays_are_database_idempotent(self) -> None:
        pending_selection = selection("pending")
        active_selection = replace(
            selection("active"),
            previous_revision_id=pending_selection.previous_revision_id,
            replay_status="passed",
        )
        pending_input = replace(
            evaluation_input(),
            selection=pending_selection,
            evaluator_scope=BOUNDED_SCOPE,
        )
        active_input = replace(
            evaluation_input(),
            selection=active_selection,
            evaluator_scope=BOUNDED_SCOPE,
        )
        pending_plan = build_worker_plan(
            snapshot(pending_input, scope=BOUNDED_SCOPE),
            evaluator_run_id="strategy-center-db-idempotent",
        )
        active_plan = build_worker_plan(
            snapshot(active_input, scope=BOUNDED_SCOPE),
            evaluator_run_id="strategy-center-db-idempotent",
        )
        weak_input = replace(
            active_input,
            stock_signals=(
                replace(
                    active_input.stock_signals[0],
                    event_time="2026-07-22T10:03:00+08:00",
                ),
            ),
        )
        weak_plan = build_worker_plan(
            snapshot(
                weak_input,
                scope=BOUNDED_SCOPE,
                evaluation_time="2026-07-22T10:03:00+08:00",
            ),
            evaluator_run_id="strategy-center-db-weak-idempotent",
        )
        self.assertEqual(len(weak_plan.work_plans[0].matches), 0)
        self.assertEqual(len(weak_plan.work_plans[0].observations), 1)
        empty_weak_plan = replace(
            weak_plan,
            work_plans=(
                replace(
                    weak_plan.work_plans[0],
                    observations=(),
                ),
            ),
        )
        repository = PostgresStrategyCenterEvaluatorRepository(
            "service=n6_strategy_worker"
        )
        with _temporary_postgres() as postgres:
            postgres.sql(
                """
                CREATE TABLE n6_user_strategy_selection_revision (
                  selection_revision_id bigint PRIMARY KEY,
                  principal_id bigint NOT NULL,
                  principal_type text NOT NULL,
                  user_id bigint NOT NULL,
                  selection_status text NOT NULL,
                  replay_status text NOT NULL,
                  activated_at timestamptz,
                  superseded_at timestamptz
                );
                CREATE TABLE n6_strategy_match_projection (
                  strategy_match_projection_id bigint GENERATED ALWAYS AS IDENTITY
                    PRIMARY KEY,
                  selection_revision_id bigint NOT NULL,
                  principal_id bigint NOT NULL,
                  principal_type text NOT NULL,
                  user_id bigint NOT NULL,
                  trade_date date NOT NULL,
                  stock_identity_key text NOT NULL,
                  action_episode_key text NOT NULL,
                  strategy_version text NOT NULL,
                  coherence_episode_key text,
                  direction text,
                  coherence_level text,
                  freshness_status text,
                  confluence_json jsonb,
                  package_evidence_json jsonb,
                  action_state text NOT NULL,
                  source_signal_projection_id bigint NOT NULL,
                  source_event_ids text[] NOT NULL,
                  matched_packages text[] NOT NULL,
                  scope_sources text[] NOT NULL,
                  indices_json jsonb NOT NULL,
                  matched_boards_json jsonb NOT NULL,
                  signal_json jsonb NOT NULL,
                  state_timeline_json jsonb NOT NULL,
                  mapping_quality text NOT NULL,
                  membership_source_trade_date date NOT NULL,
                  evaluator_policy_hash text NOT NULL,
                  projection_hash text NOT NULL,
                  matched_at timestamptz NOT NULL,
                  updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
                );
                CREATE TABLE n6_strategy_match_change (
                  strategy_match_change_id bigint GENERATED ALWAYS AS IDENTITY
                    PRIMARY KEY,
                  strategy_match_projection_id bigint,
                  strategy_observation_projection_id bigint,
                  surface_kind text NOT NULL,
                  selection_revision_id bigint NOT NULL,
                  principal_id bigint NOT NULL,
                  principal_type text NOT NULL,
                  user_id bigint NOT NULL,
                  trade_date date NOT NULL,
                  change_type text NOT NULL,
                  dedup_key text NOT NULL,
                  source_event_id text,
                  payload_json jsonb NOT NULL,
                  payload_hash text NOT NULL,
                  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                  UNIQUE (principal_id, principal_type, user_id, dedup_key)
                );
                CREATE TABLE n6_strategy_observation_projection (
                  strategy_observation_projection_id bigint
                    GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                  selection_revision_id bigint NOT NULL,
                  principal_id bigint NOT NULL,
                  principal_type text NOT NULL,
                  user_id bigint NOT NULL,
                  trade_date date NOT NULL,
                  stock_identity_key text NOT NULL,
                  action_episode_key text NOT NULL,
                  coherence_episode_key text NOT NULL,
                  action_state text NOT NULL,
                  source_signal_projection_id bigint NOT NULL,
                  source_event_ids text[] NOT NULL,
                  observed_packages text[] NOT NULL,
                  scope_sources text[] NOT NULL,
                  indices_json jsonb NOT NULL,
                  observed_boards_json jsonb NOT NULL,
                  signal_json jsonb NOT NULL,
                  strategy_version text NOT NULL,
                  direction text NOT NULL,
                  coherence_level text NOT NULL,
                  freshness_status text NOT NULL,
                  qualification_status text NOT NULL,
                  confluence_json jsonb NOT NULL,
                  package_evidence_json jsonb NOT NULL,
                  state_timeline_json jsonb NOT NULL,
                  mapping_quality text NOT NULL,
                  membership_source_trade_date date NOT NULL,
                  evaluator_policy_hash text NOT NULL,
                  observation_hash text NOT NULL,
                  observation_kind text NOT NULL,
                  observed_at timestamptz NOT NULL,
                  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                  UNIQUE (
                    principal_id, principal_type, user_id, trade_date,
                    stock_identity_key, action_episode_key,
                    coherence_episode_key, observation_kind,
                    selection_revision_id
                  )
                );
                INSERT INTO n6_user_strategy_selection_revision VALUES
                  (8, 2, 'human_user', 3, 'active', 'passed',
                   '2026-07-22 09:00+08', NULL),
                  (9, 2, 'human_user', 3, 'pending', 'pending', NULL, NULL);
                """
            )
            dsn = (
                f"host={postgres.socket_dir} port={postgres.port} "
                "dbname=ashare_v3 user=ashare_v3_user"
            )
            with psycopg.connect(dsn, row_factory=dict_row) as connection:
                with connection.cursor() as cursor:
                    primary = repository._apply_plan(cursor, pending_plan)
                connection.commit()
            with psycopg.connect(dsn, row_factory=dict_row) as connection:
                with connection.cursor() as cursor:
                    first_replay = repository._apply_plan(cursor, active_plan)
                    second_replay = repository._apply_plan(cursor, active_plan)
                    cursor.execute(
                        """
                        SELECT
                          (SELECT count(*) FROM n6_strategy_match_projection)
                            AS projection_count,
                          (SELECT count(*) FROM n6_strategy_match_change)
                            AS change_count
                        """
                    )
                    counts = cursor.fetchone()
                    weak_primary = repository._apply_plan(cursor, weak_plan)
                    cursor.execute(
                        """
                        SELECT
                          (
                            SELECT count(*)
                            FROM n6_strategy_match_projection
                          ) AS qualified_count,
                          (
                            SELECT count(*)
                            FROM n6_strategy_observation_projection
                          ) AS observation_count
                        """
                    )
                    cross_surface_counts = cursor.fetchone()
                    weak_replay = repository._apply_plan(cursor, weak_plan)
                    weak_remove = repository._apply_plan(
                        cursor, empty_weak_plan
                    )
                    cursor.execute(
                        """
                        SELECT count(*) AS weak_projection_count
                        FROM n6_strategy_observation_projection
                        """
                    )
                    weak_counts = cursor.fetchone()
                connection.commit()

        self.assertEqual(
            primary,
            {
                "committed": True,
                "upsert": 1,
                "remove": 0,
                "reset": 1,
                "unchanged": 0,
                "observation_upsert": 0,
                "observation_remove": 0,
                "observation_unchanged": 0,
            },
        )
        for replay in (first_replay, second_replay):
            self.assertEqual(
                replay,
                {
                    "committed": True,
                    "upsert": 0,
                    "remove": 0,
                    "reset": 0,
                    "unchanged": 1,
                    "observation_upsert": 0,
                    "observation_remove": 0,
                    "observation_unchanged": 0,
                },
            )
        self.assertEqual(counts, {"projection_count": 1, "change_count": 1})
        self.assertEqual(
            weak_primary,
            {
                "committed": True,
                "upsert": 0,
                "remove": 1,
                "reset": 0,
                "unchanged": 0,
                "observation_upsert": 1,
                "observation_remove": 0,
                "observation_unchanged": 0,
            },
        )
        self.assertEqual(
            cross_surface_counts,
            {"qualified_count": 0, "observation_count": 1},
        )
        self.assertEqual(
            weak_replay,
            {
                "committed": True,
                "upsert": 0,
                "remove": 0,
                "reset": 0,
                "unchanged": 0,
                "observation_upsert": 0,
                "observation_remove": 0,
                "observation_unchanged": 1,
            },
        )
        self.assertEqual(
            weak_remove,
            {
                "committed": True,
                "upsert": 0,
                "remove": 0,
                "reset": 0,
                "unchanged": 0,
                "observation_upsert": 0,
                "observation_remove": 1,
                "observation_unchanged": 0,
            },
        )
        self.assertEqual(weak_counts, {"weak_projection_count": 0})

    def test_targeted_revision_set_is_frozen_in_snapshot_plan_and_cas(self) -> None:
        item = evaluation_input()
        inputs = (item,)
        revision_ids = (9,)
        targeted_snapshot = WorkerSnapshot(
            trade_date=TRADE_DATE,
            evaluation_time=EVALUATION_TIME,
            inputs=inputs,
            snapshot_hash=snapshot_hash(
                TRADE_DATE,
                inputs,
                evaluation_time=EVALUATION_TIME,
                selection_revision_ids=revision_ids,
            ),
            selection_revision_ids=revision_ids,
            selection_cas_hash=selection_cas_hash(inputs),
        )

        class TargetedRepository:
            received = None

            def load_snapshot(
                self,
                trade_date,
                *,
                scope=None,
                selection_revision_ids=None,
            ):
                self.received = (trade_date, scope, selection_revision_ids)
                return targeted_snapshot

            def commit_plan(self, plan):
                raise AssertionError("dry-run must not commit")

        repository = TargetedRepository()
        result = run_strategy_center_once(
            repository=repository,
            trade_date=TRADE_DATE,
            evaluator_run_id="strategy-center-targeted-revision-set",
            selection_revision_ids=[9, 9],
        )
        self.assertEqual(
            repository.received,
            (TRADE_DATE, None, revision_ids),
        )
        self.assertEqual(result["selection_revision_ids"], [9])
        self.assertEqual(result["scope_mode"], "selection_revision_set")
        plan = build_worker_plan(
            targeted_snapshot,
            evaluator_run_id="strategy-center-targeted-plan",
        )
        self.assertEqual(plan.selection_revision_ids, revision_ids)
        PostgresStrategyCenterEvaluatorRepository._validate_plan_integrity(plan)

    def test_target_filter_is_after_per_user_latest_revision_rank(self) -> None:
        normalized = " ".join(WORK_ITEMS_SQL.split()).lower()
        rank_position = normalized.index("row_number() over")
        target_position = normalized.index("target_revision as")
        filter_position = normalized.index(
            "%(scope_mode)s = 'selection_revision_set'"
        )
        self.assertLess(rank_position, target_position)
        self.assertLess(target_position, filter_position)
        self.assertIn(
            "revision.selection_revision_id = any(", normalized
        )

    def test_auto_authority_uses_n6_display_consensus_and_asof_membership(self) -> None:
        trade_sql = " ".join(AUTO_TRADE_DATE_SQL.split()).lower()
        source_sql = " ".join(AUTO_SOURCE_WATERMARKS_SQL.split()).lower()
        scope_sql = " ".join(AUTO_EVALUATION_SCOPES_SQL.split()).lower()
        self.assertEqual(AUTO_TRADE_DATE_SQL, N6_TRADE_DATE_AUTHORITY_SQL)
        self.assertNotIn("common_trade_calendar", trade_sql)
        self.assertNotIn("clock_timestamp", trade_sql)
        for relation in (
            "v_n6_stock_condition_display_basis",
            "v_n6_index_condition_display_basis",
            "v_n6_board_condition_display_basis",
        ):
            self.assertIn(relation, trade_sql)
        self.assertEqual(trade_sql.count("select max(for_trade_date)"), 3)
        self.assertEqual(
            trade_sql.count("count(distinct ("), 3
        )
        self.assertNotIn(
            "n6_user_strategy_selection_revision", source_sql
        )
        self.assertIn(
            "n6_user_strategy_selection_revision", scope_sql
        )
        self.assertIn("revision.principal_id", scope_sql)
        self.assertIn("revision.user_id", scope_sql)
        self.assertIn("revision.selection_status = 'active'", scope_sql)
        self.assertIn("revision.selection_status = 'pending'", scope_sql)
        self.assertIn(
            "order by case revision.selection_status when 'pending' then 0 else 1 end, revision.selection_revision_id",
            scope_sql,
        )
        for required in (
            "user_signal_projection",
            "user_signal_card",
            "user_monitor_stock",
            "user_realtime_monitor_scope",
            "n6_virtual_position",
            "v_n6_index_membership_fact",
            "v_n6_board_membership_fact",
        ):
            self.assertIn(required, source_sql)
        self.assertIn(
            "membership.trade_date <= %(membership_asof_upper_bound)s",
            source_sql,
        )
        self.assertNotIn(
            "membership.trade_date = %(trade_date)s",
            source_sql,
        )

    def test_n6_trade_date_authority_qualifies_joined_for_trade_date(self) -> None:
        """The authority query must compile when latest and approved share a column."""
        trade_sql = " ".join(N6_TRADE_DATE_AUTHORITY_SQL.split()).lower()
        self.assertEqual(
            trade_sql.count("min(approved.for_trade_date::text) as for_trade_date"),
            3,
        )
        self.assertNotIn(
            "min(for_trade_date::text) as for_trade_date",
            trade_sql,
        )

    def test_n6_trade_date_authority_accepts_per_asset_lineage(self) -> None:
        authority = n6_trade_date_authority(N6_AUTHORITY_ROWS)
        self.assertEqual(authority.trade_date, TRADE_DATE)
        self.assertEqual(
            tuple(item.asset_kind for item in authority.batches),
            ("stock", "index", "board"),
        )
        self.assertEqual(
            tuple(item.source_run_id for item in authority.batches),
            (
                "stock-display-run",
                "index-display-run",
                "board-display-run",
            ),
        )
        self.assertEqual(
            authority.membership_asof_upper_bound,
            SOURCE_TRADE_DATE,
        )

    def test_n6_trade_date_authority_fails_closed(self) -> None:
        mismatched_date = tuple(
            {
                **row,
                "for_trade_date": (
                    "20260723"
                    if row["asset_kind"] == "board"
                    else row["for_trade_date"]
                ),
            }
            for row in N6_AUTHORITY_ROWS
        )
        invalid_source_date = tuple(
            {
                **row,
                "source_trade_date": (
                    "20260723"
                    if row["asset_kind"] == "index"
                    else row["source_trade_date"]
                ),
            }
            for row in N6_AUTHORITY_ROWS
        )
        impossible_source_date = tuple(
            {
                **row,
                "source_trade_date": (
                    "20260231"
                    if row["asset_kind"] == "stock"
                    else row["source_trade_date"]
                ),
            }
            for row in N6_AUTHORITY_ROWS
        )
        impossible_for_trade_date = tuple(
            {
                **row,
                "for_trade_date": "20260231",
            }
            for row in N6_AUTHORITY_ROWS
        )
        for rows in (
            N6_AUTHORITY_ROWS[:-1],
            N6_AUTHORITY_ROWS + (N6_AUTHORITY_ROWS[0],),
            mismatched_date,
            invalid_source_date,
            impossible_source_date,
            impossible_for_trade_date,
            tuple(
                {
                    **row,
                    "source_run_id": (
                        "" if row["asset_kind"] == "stock"
                        else row["source_run_id"]
                    ),
                }
                for row in N6_AUTHORITY_ROWS
            ),
        ):
            with self.subTest(rows=rows), self.assertRaisesRegex(
                StrategyCenterWorkerBlocked,
                "n6_trade_date_authority_invalid",
            ):
                n6_trade_date_authority(rows)

    def test_snapshot_hash_freezes_n6_batch_and_projection_card_watermarks(
        self,
    ) -> None:
        inputs = (evaluation_input(),)
        watermarks = {
            "projection": {"max_projection_id": "101"},
            "signal_card": {"max_card_id": "201"},
        }
        original = snapshot_hash(
            TRADE_DATE,
            inputs,
            evaluation_time=EVALUATION_TIME,
            trade_date_authority=N6_AUTHORITY,
            source_watermarks=watermarks,
        )
        drifted_authority = N6TradeDateAuthority(
            trade_date=TRADE_DATE,
            batches=(
                replace(
                    N6_AUTHORITY.batches[0],
                    source_run_id="stock-display-run-drift",
                ),
                *N6_AUTHORITY.batches[1:],
            ),
        )
        self.assertNotEqual(
            original,
            snapshot_hash(
                TRADE_DATE,
                inputs,
                evaluation_time=EVALUATION_TIME,
                trade_date_authority=drifted_authority,
                source_watermarks=watermarks,
            ),
        )
        self.assertNotEqual(
            original,
            snapshot_hash(
                TRADE_DATE,
                inputs,
                evaluation_time=EVALUATION_TIME,
                trade_date_authority=N6_AUTHORITY,
                source_watermarks={
                    **watermarks,
                    "signal_card": {"max_card_id": "202"},
                },
            ),
        )

    def test_plan_rejects_n6_batch_or_watermark_drift(self) -> None:
        value = snapshot(
            trade_date_authority=N6_AUTHORITY,
            source_watermarks={
                "projection": {"max_projection_id": "101"},
                "signal_card": {"max_card_id": "201"},
            },
        )
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "strategy_worker_snapshot_invalid",
        ):
            build_worker_plan(
                replace(
                    value,
                    trade_date_authority=N6TradeDateAuthority(
                        trade_date=TRADE_DATE,
                        batches=(
                            replace(
                                N6_AUTHORITY.batches[0],
                                source_run_id="drifted-run",
                            ),
                            *N6_AUTHORITY.batches[1:],
                        ),
                    ),
                ),
                evaluator_run_id="strategy-center-authority-drift",
            )
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "strategy_worker_snapshot_invalid",
        ):
            build_worker_plan(
                replace(
                    value,
                    source_watermarks={
                        "projection": {"max_projection_id": "102"},
                        "signal_card": {"max_card_id": "201"},
                    },
                ),
                evaluator_run_id="strategy-center-watermark-drift",
            )

    def test_pending_v2_execute_requires_reviewed_natural_event_group(
        self,
    ) -> None:
        pending = replace(
            evaluation_input(),
            selection=selection("pending"),
            evaluator_scope=BOUNDED_SCOPE,
        )
        ready_repository = FakeRepository(
            snapshot(pending, scope=BOUNDED_SCOPE)
        )
        ready = run_strategy_center_once(
            repository=ready_repository,
            trade_date=TRADE_DATE,
            evaluator_run_id="strategy-center-natural-ready",
            scope=BOUNDED_SCOPE,
        )
        self.assertEqual(
            ready["reviewed_natural_event_group_counts"], {9: 1}
        )
        self.assertTrue(ready["ready_for_execute"])

        empty = replace(
            pending,
            stock_signals=(),
            parent_executed_events=(),
        )
        empty_repository = FakeRepository(
            snapshot(empty, scope=BOUNDED_SCOPE)
        )
        dry = run_strategy_center_once(
            repository=empty_repository,
            trade_date=TRADE_DATE,
            evaluator_run_id="strategy-center-natural-empty-dry",
            scope=BOUNDED_SCOPE,
        )
        self.assertFalse(dry["ready_for_execute"])
        self.assertEqual(dry["pending_v2_without_natural_events"], [9])
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "reviewed_n6_natural_event_group_missing",
        ):
            run_strategy_center_once(
                repository=empty_repository,
                trade_date=TRADE_DATE,
                evaluator_run_id="strategy-center-natural-empty-execute",
                scope=BOUNDED_SCOPE,
                evaluation_time=dry["evaluation_time"],
                execute=True,
                runtime_authorized=True,
            )

    def test_bounded_work_item_validation_fails_closed(self) -> None:
        repository = object.__new__(PostgresStrategyCenterEvaluatorRepository)
        valid = repository._work_item(
            self._work_item_row(), trade_date=TRADE_DATE, scope=BOUNDED_SCOPE
        )
        self.assertEqual(valid.selection_revision_id, 9)
        cases = (
            (
                self._work_item_row(user_id=4),
                "bounded_scope_work_item_mismatch",
            ),
            (
                self._work_item_row(selection_status="superseded"),
                "selection_revision_status_invalid",
            ),
            (
                self._work_item_row(effective_trade_date="20260723"),
                "selection_effective_trade_date_invalid",
            ),
            (
                self._work_item_row(selected_package_keys=[]),
                "selected_package_authority_invalid",
            ),
        )
        for row, reason in cases:
            with self.subTest(reason=reason), self.assertRaisesRegex(
                StrategyCenterWorkerBlocked, reason
            ):
                repository._work_item(
                    row, trade_date=TRADE_DATE, scope=BOUNDED_SCOPE
                )

    def test_temporal_confluence_v2_package_authority_is_exact(self) -> None:
        repository = object.__new__(PostgresStrategyCenterEvaluatorRepository)
        valid = repository._work_item(
            self._work_item_row(), trade_date=TRADE_DATE, scope=BOUNDED_SCOPE
        )
        self.assertEqual(
            valid.selected_package_authority,
            (
                f"package_1|v2|{PACKAGE_1_POLICY_HASH}",
                f"package_2|v2|{PACKAGE_2_POLICY_HASH}",
            ),
        )
        self.assertEqual(
            valid.selected_package_rule_authority,
            (PACKAGE_1_RULE_AUTHORITY, PACKAGE_2_RULE_AUTHORITY),
        )

        invalid_authorities = (
            (f"package_1|v1|{PACKAGE_1_POLICY_HASH}",
             f"package_2|v2|{PACKAGE_2_POLICY_HASH}"),
            (f"package_1|v2|{PACKAGE_1_POLICY_HASH}",),
            (f"package_1|v2|{PACKAGE_1_POLICY_HASH}",
             f"package_1|v2|{PACKAGE_1_POLICY_HASH}"),
            (f"package_1|v2|{PACKAGE_1_POLICY_HASH}",
             f"package_2|v2|{PACKAGE_2_POLICY_HASH}",
             f"package_2|v2|{'3' * 64}"),
            (f"package_1|v2|{PACKAGE_1_POLICY_HASH}",
             f"package_2|v2|{'3' * 64}"),
            ("package_1|v2|not-a-policy-hash",
             f"package_2|v2|{PACKAGE_2_POLICY_HASH}"),
        )
        for authority in invalid_authorities:
            with self.subTest(authority=authority), self.assertRaisesRegex(
                StrategyCenterWorkerBlocked,
                "selected_package_authority_invalid",
            ):
                repository._work_item(
                    self._work_item_row(
                        selected_package_authority=list(authority)
                    ),
                    trade_date=TRADE_DATE,
                    scope=BOUNDED_SCOPE,
                )

        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "selected_package_authority_invalid",
        ):
            repository._work_item(
                self._work_item_row(
                    selected_package_keys=["package_1", "package_1"],
                    selected_package_authority=[
                        f"package_1|v2|{PACKAGE_1_POLICY_HASH}",
                        f"package_1|v2|{PACKAGE_1_POLICY_HASH}",
                    ],
                ),
                trade_date=TRADE_DATE,
                scope=BOUNDED_SCOPE,
            )

        invalid_rule_rows = (
            [],
            [APPROVED_PACKAGE_POLICY_PAYLOADS["package_1"]],
            [
                APPROVED_PACKAGE_POLICY_PAYLOADS["package_1"],
                {"package_id": "tampered"},
            ],
            [
                APPROVED_PACKAGE_POLICY_PAYLOADS["package_2"],
                APPROVED_PACKAGE_POLICY_PAYLOADS["package_1"],
            ],
        )
        for rule_rows in invalid_rule_rows:
            with self.subTest(rule_rows=rule_rows), self.assertRaisesRegex(
                StrategyCenterWorkerBlocked,
                "selected_package_authority_invalid",
            ):
                repository._work_item(
                    self._work_item_row(
                        selected_package_rule_authority=rule_rows
                    ),
                    trade_date=TRADE_DATE,
                    scope=BOUNDED_SCOPE,
                )

    def test_worker_plan_rejects_in_memory_package_authority_pollution(
        self,
    ) -> None:
        item = evaluation_input()
        polluted = replace(
            item,
            selection=replace(
                item.selection,
                selected_package_authority=(
                    f"package_1|v2|{PACKAGE_1_POLICY_HASH}",
                    f"package_2|v1|{PACKAGE_2_POLICY_HASH}",
                ),
            ),
        )
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "selected_package_authority_invalid",
        ):
            build_worker_plan(
                snapshot(polluted),
                evaluator_run_id="strategy-center-v2-authority-pollution",
            )

        polluted_rule = replace(
            item,
            selection=replace(
                item.selection,
                selected_package_rule_authority=(
                    PACKAGE_1_RULE_AUTHORITY,
                    json.dumps({"package_id": "tampered"}),
                ),
            ),
        )
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "selected_package_authority_invalid",
        ):
            build_worker_plan(
                snapshot(polluted_rule),
                evaluator_run_id="strategy-center-v2-rule-pollution",
            )

    def test_bounded_snapshot_coverage_only_queries_target_principal(self) -> None:
        class Cursor:
            def __init__(self, rows):
                self.rows = rows
                self.query = ""
                self.params = None
                self.queries = []

            def execute(self, query, params=None):
                self.query = query
                self.params = params
                self.queries.append((query, params))

            def fetchone(self):
                if "source_watermarks" in self.query:
                    return {
                        "source_watermarks": {
                            "projection": {"projection_count": 3},
                            "signal_card": {"card_count": 3},
                        }
                    }
                if "principal.principal_status" in self.query:
                    return {"count": 1}
                return {
                    "evaluation_time": EVALUATION_TIME,
                }

            def fetchall(self):
                if self.query is N6_TRADE_DATE_AUTHORITY_SQL:
                    return N6_AUTHORITY_ROWS
                if "WITH ranked_revision" in self.query:
                    return self.rows
                return []

        repository = object.__new__(PostgresStrategyCenterEvaluatorRepository)
        repository.signal_source_user_id = None
        repository._load_evaluation_input = (
            lambda _cur, _trade_date, work_item, evaluator_scope=None: replace(
                evaluation_input(),
                selection=work_item,
                evaluator_scope=evaluator_scope,
            )
        )
        cursor = Cursor([self._work_item_row()])
        result = repository._load_snapshot(
            cursor, TRADE_DATE, scope=BOUNDED_SCOPE
        )
        self.assertEqual(result.evaluator_scope, BOUNDED_SCOPE)
        self.assertEqual(result.evaluation_time, EVALUATION_TIME)
        self.assertEqual(result.trade_date_authority, N6_AUTHORITY)
        self.assertIn(
            "pg_catalog.transaction_timestamp()",
            cursor.queries[1][0],
        )
        work_query, work_params = cursor.queries[2]
        coverage_query, coverage_params = cursor.queries[3]
        self.assertIs(work_query, WORK_ITEMS_SQL)
        self.assertEqual(work_params["selection_revision_id"], 9)
        self.assertIn("principal.principal_id = %(principal_id)s", coverage_query)
        self.assertIn("principal.owner_user_id = %(user_id)s", coverage_query)
        self.assertEqual(coverage_params["principal_id"], 2)
        self.assertEqual(coverage_params["user_id"], 3)
        watermark_query, watermark_params = cursor.queries[4]
        self.assertIs(watermark_query, AUTO_SOURCE_WATERMARKS_SQL)
        self.assertEqual(watermark_params["signal_source_user_ids"], [3])
        self.assertEqual(
            watermark_params["membership_asof_upper_bound"],
            SOURCE_TRADE_DATE,
        )

        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "bounded_scope_selection_authority_invalid",
        ):
            repository._load_snapshot(Cursor([]), TRADE_DATE, scope=BOUNDED_SCOPE)
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "n6_trade_date_authority_mismatch",
        ):
            repository._load_snapshot(
                Cursor([self._work_item_row()]),
                "20260723",
                scope=BOUNDED_SCOPE,
            )

    def test_strategy_worker_has_no_calendar_or_upstream_raw_dependency(
        self,
    ) -> None:
        source = Path(
            "src/ashare_v3/user/strategy_center_worker.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("common_trade_calendar", source)
        for forbidden in (
            "FROM stock_condition_display_basis",
            "FROM index_condition_display_basis",
            "FROM board_condition_display_basis",
            "FROM stock_action_fact",
            "FROM index_action_fact",
            "FROM board_action_fact",
            "FROM common_action_event",
            "FROM common_trigger_match",
        ):
            self.assertNotIn(forbidden, source)

    @staticmethod
    def _scope_web_repository() -> PostgresN6UserRepository:
        repository = object.__new__(PostgresN6UserRepository)
        repository._app_v2_relation_exists = lambda _name: True
        repository._app_v1_signal_schema_capabilities = lambda: {
            "n6_virtual_account",
            "n6_virtual_position",
        }
        repository._app_v2_monitor_columns = lambda _name: {
            "source_run_id",
            "valid_source_trade_date",
            "valid_for_trade_date",
            "valid_source_run_id",
        }
        return repository

    def test_canonical_signal_sql_reuses_effective_scope_join_and_user_scope(self) -> None:
        web_repository = self._scope_web_repository()
        scope_cte = web_repository._app_v1_effective_monitor_scope_cte()
        self.assertIn("current_stock_principal_monitors", scope_cte)
        self.assertIn("FROM user_realtime_monitor_scope s", scope_cte)
        self.assertIn("JOIN n6_virtual_position p", scope_cte)
        self.assertIn("s.user_id = %(user_id)s", scope_cte)

        web_repository._app_v1_effective_monitor_scope_cte = lambda: scope_cte
        web_repository._app_v1_signal_select_list = (
            lambda: "p.user_signal_projection_id, monitor_scope.source_type_raw"
        )

        row = {
            "user_signal_projection_id": 101,
            "user_projection_run_id": "projection-run-1",
            "projection_run_id": "projection-run-1",
            "asset_kind": "stock",
            "identity_key": STOCK,
            "code": "600000",
            "name": "浦发银行",
            "direction": "buy",
            "action_state": "eligible",
            "event_type": "ActionEligible",
            "trade_date": TRADE_DATE,
            "source_run_id": "n5-run",
            "quality_status": "reviewed",
            "source_type_raw": "realtime_scope",
            "source_type": "realtime_scope",
            "source_type_label": "实时监控范围",
            "source_object_kind": "none",
            "source_object_identity_key": None,
            "source_object_code": None,
            "source_object_name": None,
            "membership_relation_date": None,
            "condition_projection_context": {
                "source_trade_date": SOURCE_TRADE_DATE,
                "for_trade_date": TRADE_DATE,
                "status": "ready",
            },
        }

        class Cursor:
            def __init__(self) -> None:
                self.query = ""
                self.params = {}

            def execute(self, query, params) -> None:
                self.query = query
                self.params = params

            def fetchall(self):
                return [row]

        cursor = Cursor()
        evaluator_repository = object.__new__(
            PostgresStrategyCenterEvaluatorRepository
        )
        evaluator_repository._web_repository = web_repository
        actual = evaluator_repository._canonical_signal_items(
            cursor,
            selection=selection(),
            trade_date=TRADE_DATE,
            projection_ids=[101],
        )

        normalized_sql = " ".join(cursor.query.split()).lower()
        self.assertIn("join lateral", normalized_sql)
        self.assertIn(") monitor_scope on true", normalized_sql)
        self.assertIn(
            "effective_monitor_scope.identity_key = p.identity_key",
            normalized_sql,
        )
        self.assertIn("where p.user_id = %(user_id)s", normalized_sql)
        self.assertEqual(cursor.params["principal_id"], 2)
        self.assertEqual(cursor.params["principal_type"], "human_user")
        self.assertEqual(cursor.params["user_id"], 3)
        self.assertEqual(actual[101], app_signal_item(dict(row)))
        self.assertEqual(
            actual[101]["condition_projection_context"]["source_trade_date"],
            SOURCE_TRADE_DATE,
        )
        for field in (
            "user_signal_projection_id",
            "identity_key",
            "event_type",
            "action_state",
            "display_code",
            "display_name",
            "source_run_id",
            "projection_run_id",
            "quality_status",
        ):
            self.assertIn(field, actual[101])

    def test_stock_candidate_scope_reuses_web_contract_without_other_monitors(self) -> None:
        evaluator_repository = object.__new__(
            PostgresStrategyCenterEvaluatorRepository
        )
        evaluator_repository._web_repository = self._scope_web_repository()
        stock_scope_cte = evaluator_repository._stock_effective_monitor_scope_cte()
        normalized_scope = " ".join(stock_scope_cte.lower().split())
        self.assertIn("from user_monitor_stock", normalized_scope)
        self.assertIn("from user_realtime_monitor_scope", normalized_scope)
        self.assertIn("join n6_virtual_position", normalized_scope)
        self.assertIn(
            "where approved.for_trade_date::text = %(trade_date)s",
            normalized_scope,
        )
        self.assertNotIn("select max(for_trade_date)", normalized_scope)
        self.assertNotIn("user_monitor_index", normalized_scope)
        self.assertNotIn("user_monitor_board", normalized_scope)

        class Cursor:
            def __init__(self) -> None:
                self.query = ""
                self.params = {}

            def execute(self, query, params) -> None:
                self.query = query
                self.params = params

            def fetchall(self):
                return [
                    {"user_signal_projection_id": 101},
                    {"user_signal_projection_id": 103},
                ]

        cursor = Cursor()
        projection_ids = evaluator_repository._canonical_stock_projection_ids(
            cursor,
            selection=selection(),
            trade_date=TRADE_DATE,
        )
        normalized_query = " ".join(cursor.query.lower().split())
        self.assertEqual(projection_ids, [101, 103])
        self.assertIn("p.asset_kind = 'stock'", normalized_query)
        self.assertIn("p.user_id = %(user_id)s", normalized_query)
        self.assertIn("p.for_trade_date = pg_catalog.to_date", normalized_query)
        self.assertNotIn("user_monitor_index", normalized_query)
        self.assertNotIn("user_monitor_board", normalized_query)
        self.assertEqual(cursor.params["principal_id"], 2)
        self.assertEqual(cursor.params["user_id"], 3)

    def test_shared_signal_source_does_not_replace_target_user_scope(self) -> None:
        evaluator_repository = object.__new__(
            PostgresStrategyCenterEvaluatorRepository
        )
        evaluator_repository.signal_source_user_id = 1
        evaluator_repository._web_repository = self._scope_web_repository()

        class Cursor:
            def __init__(self) -> None:
                self.query = ""
                self.params = {}

            def execute(self, query, params) -> None:
                self.query = query
                self.params = params

            def fetchall(self):
                return [{"user_signal_projection_id": 101}]

        cursor = Cursor()
        projection_ids = evaluator_repository._canonical_stock_projection_ids(
            cursor,
            selection=selection(),
            trade_date=TRADE_DATE,
        )
        normalized_query = " ".join(cursor.query.lower().split())
        self.assertEqual(projection_ids, [101])
        self.assertIn("p.user_id = %(user_id)s", normalized_query)
        self.assertIn("s.user_id = %(scope_user_id)s", normalized_query)
        self.assertNotIn("user_monitor_index", normalized_query)
        self.assertNotIn("user_monitor_board", normalized_query)
        self.assertEqual(cursor.params["user_id"], 1)
        self.assertEqual(cursor.params["scope_user_id"], 3)
        self.assertEqual(cursor.params["principal_id"], 2)

    def test_canonical_signal_dto_is_complete_for_three_asset_channels(self) -> None:
        web_repository = self._scope_web_repository()
        web_repository._app_v1_signal_select_list = (
            lambda: "p.user_signal_projection_id, monitor_scope.source_type_raw"
        )
        identities = {
            "stock": "stock:SH:600000",
            "index": "index:SH:000300",
            "board": "board:TDX:880001",
        }

        class Cursor:
            def __init__(self, row) -> None:
                self.row = row

            def execute(self, _query, _params) -> None:
                return None

            def fetchall(self):
                return [self.row]

        evaluator_repository = object.__new__(
            PostgresStrategyCenterEvaluatorRepository
        )
        evaluator_repository._web_repository = web_repository
        for projection_id, (asset_kind, identity_key) in enumerate(
            identities.items(), start=101
        ):
            row = {
                "user_signal_projection_id": projection_id,
                "user_projection_run_id": "projection-run-1",
                "projection_run_id": "projection-run-1",
                "trade_date": TRADE_DATE,
                "asset_kind": asset_kind,
                "identity_key": identity_key,
                "code": identity_key.rsplit(":", 1)[-1],
                "name": f"{asset_kind}-name",
                "direction": "buy",
                "action_state": "eligible",
                "event_type": "ActionEligible",
                "source_run_id": "n5-run",
                "quality_status": "reviewed",
                "source_type_raw": "realtime_scope",
            }
            with self.subTest(asset_kind=asset_kind):
                actual = evaluator_repository._canonical_signal_items(
                    Cursor(row),
                    selection=selection(),
                    trade_date=TRADE_DATE,
                    projection_ids=[projection_id],
                )[projection_id]
                self.assertEqual(actual["asset_kind"], asset_kind)
                self.assertEqual(actual["identity_key"], identity_key)

    def test_parent_direction_comes_only_from_canonical_projection_authority(
        self,
    ) -> None:
        repository = object.__new__(PostgresStrategyCenterEvaluatorRepository)
        repository._canonical_stock_projection_ids = (
            lambda _cur, selection, trade_date: []
        )
        repository._canonical_signal_items = (
            lambda _cur, selection, trade_date, projection_ids: {}
        )
        repository._membership_authorities = (
            lambda _cur, trade_date, stock_signals: ()
        )
        parent_row = {
            "user_signal_projection_id": 202,
            "trade_date": TRADE_DATE,
            "asset_kind": "index",
            "identity_key": "index:SH:000300",
            "code": "000300",
            "name": "沪深300",
            "event_id": "evt-index-executed",
            "event_type": "ActionExecuted",
            "action_state": "executed",
            "source_event_time": "2026-07-22T09:31:00+08:00",
            "projection_event_time": "2026-07-22T01:31:00Z",
            "source_layer": "N5_action",
            "source_run_id": "n5-run",
            "event_schema_version": "N5ActionEvent.v2",
            "source_direction": "sell",
            "projection_direction": "sell",
        }

        def load(row):
            with patch.object(
                N6StrategyCenterReadRepository,
                "fetch_scope_rows",
                return_value=[],
            ), patch.object(
                N6StrategyCenterReadRepository,
                "fetch_parent_executed_signal_ids",
                return_value=[202],
            ), patch.object(
                N6StrategyCenterReadRepository,
                "fetch_signal_authority_rows",
                return_value=[row],
            ):
                return repository._load_evaluation_input(
                    MagicMock(), TRADE_DATE, selection()
                )

        actual = load(parent_row)
        self.assertEqual(len(actual.parent_executed_events), 1)
        self.assertEqual(actual.parent_executed_events[0].direction, "sell")
        self.assertEqual(
            actual.parent_executed_events[0].event_time,
            parent_row["source_event_time"],
        )
        self.assertEqual(
            actual.parent_executed_events[0].user_signal_projection_id,
            parent_row["user_signal_projection_id"],
        )
        authority_sql = " ".join(SIGNAL_AUTHORITY_ROWS_SQL.split())
        self.assertIn("p.source_payload_json->>'event_time'", authority_sql)
        self.assertIn("p.source_payload_json->'payload_json'->>'direction'", authority_sql)

        for invalid in (None, "", "BUY", "hold"):
            with self.subTest(direction=invalid), self.assertRaisesRegex(
                StrategyCenterWorkerBlocked,
                "n5_standard_event_authority_invalid",
            ):
                load({**parent_row, "source_direction": invalid})

        for changed in (
            {"projection_direction": "buy"},
            {"projection_event_time": "2026-07-22T09:31:01+08:00"},
            {"source_layer": "N6_user"},
        ):
            with self.subTest(changed=changed), self.assertRaisesRegex(
                StrategyCenterWorkerBlocked,
                "n5_standard_event_authority_invalid",
            ):
                load({**parent_row, **changed})

    def test_v2_stock_direction_must_equal_n5_and_canonical_dto(self) -> None:
        row = {
            "source_layer": "N5_action",
            "source_event_time": "2026-07-22T09:31:00+08:00",
            "projection_event_time": "2026-07-22T01:31:00Z",
            "source_direction": "buy",
            "projection_direction": "buy",
        }
        self.assertEqual(
            _v2_standard_event_authority(
                row, canonical_signal={"direction": "buy"}
            ),
            ("2026-07-22T09:31:00+08:00", "buy"),
        )
        for canonical_direction in ("", "sell", "BUY"):
            with self.subTest(
                canonical_direction=canonical_direction
            ), self.assertRaisesRegex(
                StrategyCenterWorkerBlocked,
                "n5_standard_event_authority_invalid",
            ):
                _v2_standard_event_authority(
                    row,
                    canonical_signal={"direction": canonical_direction},
                )

    def test_canonical_signal_missing_identity_fails_closed(self) -> None:
        web_repository = self._scope_web_repository()
        web_repository._app_v1_signal_select_list = (
            lambda: "p.user_signal_projection_id, monitor_scope.source_type_raw"
        )

        class Cursor:
            def execute(self, _query, _params) -> None:
                return None

            def fetchall(self):
                return [
                    {
                        "user_signal_projection_id": 101,
                        "user_projection_run_id": "projection-run-1",
                        "projection_run_id": "projection-run-1",
                        "trade_date": TRADE_DATE,
                        "asset_kind": "stock",
                        "identity_key": "",
                        "code": "600000",
                        "name": "浦发银行",
                        "direction": "buy",
                        "action_state": "eligible",
                        "event_type": "ActionEligible",
                        "source_run_id": "n5-run",
                    }
                ]

        evaluator_repository = object.__new__(
            PostgresStrategyCenterEvaluatorRepository
        )
        evaluator_repository._web_repository = web_repository
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked, "canonical_signal_dto_incomplete"
        ):
            evaluator_repository._canonical_signal_items(
                Cursor(),
                selection=selection(),
                trade_date=TRADE_DATE,
                projection_ids=[101],
            )

    def test_canonical_signal_sql_without_matching_scope_is_omitted(self) -> None:
        web_repository = self._scope_web_repository()
        web_repository._app_v1_effective_monitor_scope_cte = (
            lambda: "effective_monitor_scope AS (SELECT NULL WHERE false)"
        )
        web_repository._app_v1_signal_select_list = (
            lambda: "p.user_signal_projection_id, monitor_scope.source_type_raw"
        )

        class Cursor:
            def __init__(self) -> None:
                self.query = ""
                self.queries = []

            def execute(self, query, _params) -> None:
                self.query = query
                self.queries.append(query)

            def fetchall(self):
                if len(self.queries) == 1:
                    return []
                return [
                    {
                        "user_signal_projection_id": 101,
                        "projection_run_ready": True,
                        "exact_scope_match": False,
                    }
                ]

        cursor = Cursor()
        evaluator_repository = object.__new__(
            PostgresStrategyCenterEvaluatorRepository
        )
        evaluator_repository._web_repository = web_repository
        actual = evaluator_repository._canonical_signal_items(
            cursor,
            selection=selection(),
            trade_date=TRADE_DATE,
            projection_ids=[101],
        )
        self.assertEqual(actual, {})
        self.assertIn("JOIN LATERAL", cursor.queries[0])
        self.assertIn("exact_scope_match", cursor.queries[1])
        for query in cursor.queries:
            self.assertNotIn(" INSERT ", f" {query.upper()} ")
            self.assertNotIn(" UPDATE ", f" {query.upper()} ")
            self.assertNotIn(" DELETE ", f" {query.upper()} ")

    def test_canonical_signal_missing_inside_exact_scope_fails_closed(self) -> None:
        web_repository = self._scope_web_repository()
        web_repository._app_v1_signal_select_list = (
            lambda: "p.user_signal_projection_id, monitor_scope.source_type_raw"
        )

        class Cursor:
            def __init__(self) -> None:
                self.fetch_count = 0

            def execute(self, _query, _params) -> None:
                return None

            def fetchall(self):
                self.fetch_count += 1
                if self.fetch_count == 1:
                    return []
                return [
                    {
                        "user_signal_projection_id": 101,
                        "projection_run_ready": True,
                        "exact_scope_match": True,
                    }
                ]

        evaluator_repository = object.__new__(
            PostgresStrategyCenterEvaluatorRepository
        )
        evaluator_repository._web_repository = web_repository
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked, "canonical_signal_dto_incomplete"
        ):
            evaluator_repository._canonical_signal_items(
                Cursor(),
                selection=selection(),
                trade_date=TRADE_DATE,
                projection_ids=[101],
            )

    def test_worker_filters_formal_signals_to_canonical_dto_ids(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "src/ashare_v3/user/strategy_center_worker.py"
        ).read_text(encoding="utf-8")
        self.assertIn("projection_id not in canonical", source)
        self.assertIn("app_signal_item(dict(row))", source)

    def test_membership_authority_sql_is_bounded_as_of_and_freezes_provenance(self) -> None:
        class Cursor:
            def __init__(self) -> None:
                self.query = ""
                self.params = {}

            def execute(self, query, params) -> None:
                self.query = query
                self.params = params

            def fetchone(self):
                return {
                    "selected_membership_trade_date": "20260721",
                    "source_version": "membership-v1",
                    "source_batch_id": "membership-batch-1",
                    "source_version_count": 1,
                    "source_batch_id_count": 1,
                }

        cursor = Cursor()
        repository = object.__new__(PostgresStrategyCenterEvaluatorRepository)
        actual = repository._membership_snapshot_authority(
            cursor,
            membership_kind="index",
            requested_source_trade_date=TRADE_DATE,
        )
        normalized = " ".join(cursor.query.split()).lower()
        self.assertIn("max(membership.trade_date)", normalized)
        self.assertIn(
            "membership.trade_date <= %(requested_source_trade_date)s", normalized
        )
        self.assertNotIn(
            "membership.trade_date = %(requested_source_trade_date)s",
            normalized,
        )
        self.assertEqual(cursor.params["requested_source_trade_date"], TRADE_DATE)
        self.assertEqual(actual["selected_membership_trade_date"], SOURCE_TRADE_DATE)
        self.assertEqual(actual["source_version"], "membership-v1")
        self.assertEqual(actual["source_batch_id"], "membership-batch-1")
        self.assertEqual(actual["provenance_status"], "authoritative_as_of")
        self.assertEqual(actual["quality_status"], "passed")

    def test_business_day_uses_prior_as_of_and_never_future_snapshot(self) -> None:
        item = evaluation_input()
        future_index = replace(
            item.index_memberships[0], trade_date="20260723", source_version="future"
        )
        older_index = replace(
            item.index_memberships[0], trade_date="20260720", source_version="older"
        )
        actual = build_worker_plan(
            snapshot(
                replace(
                    item,
                    index_memberships=(older_index, item.index_memberships[0], future_index),
                )
            ),
            evaluator_run_id="strategy-center-20260722-asof",
        ).work_plans[0].matches[0]
        self.assertEqual(actual.requested_source_trade_date, SOURCE_TRADE_DATE)
        self.assertEqual(actual.membership_source_trade_date, SOURCE_TRADE_DATE)
        self.assertEqual(actual.indices[0]["membership_source_version"], "membership-v1")
        self.assertNotEqual(actual.indices[0]["membership_source_version"], "future")

    def test_episode_specific_source_dates_do_not_share_global_snapshot(self) -> None:
        item = evaluation_input()
        second = replace(
            item.stock_signals[0],
            user_signal_projection_id=102,
            event_id="evt-stock-second",
            action_episode_key="evt-n4-second",
            signal={
                **item.stock_signals[0].signal,
                "condition_projection_context": {"source_trade_date": "20260720"},
            },
        )
        old_index = replace(item.index_memberships[0], trade_date="20260720")
        old_board = replace(item.board_memberships[0], trade_date="20260720")
        second_authorities = (
            membership_authority("index", episode="evt-n4-second", requested="20260720", selected="20260720"),
            membership_authority("board", episode="evt-n4-second", requested="20260720", selected="20260720"),
        )
        revised = replace(
            item,
            stock_signals=(item.stock_signals[0], second),
            index_memberships=(old_index, item.index_memberships[0]),
            board_memberships=(old_board, item.board_memberships[0]),
            membership_authorities=item.membership_authorities + second_authorities,
        )
        matches = build_worker_plan(
            snapshot(revised), evaluator_run_id="strategy-center-20260722-episodes"
        ).work_plans[0].matches
        self.assertEqual(len(matches), 2)
        self.assertEqual(
            {match.action_episode_key: match.membership_source_trade_date for match in matches},
            {"evt-n4-entry": "20260721", "evt-n4-second": "20260720"},
        )

    def test_missing_invalid_and_future_source_dates_fail_closed(self) -> None:
        repository = object.__new__(PostgresStrategyCenterEvaluatorRepository)

        class NoSqlCursor:
            def execute(self, *_args, **_kwargs) -> None:
                raise AssertionError("invalid source date must not query membership")

        item = evaluation_input()
        cases = (
            ({}, "source_trade_date_missing"),
            ({"source_trade_date": "20260230"}, "source_trade_date_invalid"),
            ({"source_trade_date": "20260723"}, "source_trade_date_future"),
        )
        for context, expected_status in cases:
            with self.subTest(expected_status=expected_status):
                signal = replace(
                    item.stock_signals[0],
                    signal={
                        **item.stock_signals[0].signal,
                        "condition_projection_context": context,
                    },
                )
                authorities = repository._membership_authorities(
                    NoSqlCursor(), trade_date=TRADE_DATE, stock_signals=(signal,)
                )
                self.assertEqual(
                    {authority.quality_status for authority in authorities},
                    {expected_status},
                )
                revised = replace(
                    item,
                    stock_signals=(signal,),
                    membership_authorities=authorities,
                )
                plan = build_worker_plan(
                    snapshot(revised),
                    evaluator_run_id=f"strategy-center-{expected_status}",
                )
                self.assertEqual(plan.work_plans[0].matches, ())

    def test_index_and_board_freeze_independent_as_of_provenance(self) -> None:
        item = evaluation_input()
        revised = replace(
            item,
            index_memberships=(replace(item.index_memberships[0], trade_date="20260720"),),
            membership_authorities=(
                membership_authority("index", selected="20260720"),
                membership_authority("board", selected="20260721"),
            ),
        )
        match = build_worker_plan(
            snapshot(revised), evaluator_run_id="strategy-center-kind-asof"
        ).work_plans[0].matches[0]
        provenance = {
            row["membership_kind"]: row for row in match.membership_provenance
        }
        self.assertEqual(
            provenance["index"]["selected_membership_trade_date"], "20260720"
        )
        self.assertEqual(
            provenance["board"]["selected_membership_trade_date"], "20260721"
        )
        self.assertEqual(match.membership_source_trade_date, "20260721")
        self.assertEqual(match.indices[0]["selected_membership_trade_date"], "20260720")
        self.assertEqual(
            match.matched_boards[0]["selected_membership_trade_date"], "20260721"
        )

    def test_337_index_mapped_and_six_missing_index_quality_is_preserved(self) -> None:
        item = evaluation_input()
        stock_signals = []
        scope_rows = []
        index_rows = []
        board_rows = []
        authorities = []
        for offset in range(343):
            code = f"{600000 + offset:06d}"
            stock_key = f"stock:SH:{code}"
            episode = f"episode-{offset}"
            stock_signals.append(
                replace(
                    item.stock_signals[0],
                    user_signal_projection_id=offset + 1,
                    identity_key=stock_key,
                    code=code,
                    event_id=f"stock-event-{offset}",
                    action_episode_key=episode,
                    signal={
                        **item.stock_signals[0].signal,
                        "identity_key": stock_key,
                    },
                )
            )
            scope_rows.append(ScopeRow(TRADE_DATE, stock_key, "monitor"))
            board_rows.append(
                replace(item.board_memberships[0], stock_identity_key=stock_key)
            )
            if offset < 337:
                index_rows.append(
                    replace(item.index_memberships[0], stock_identity_key=stock_key)
                )
            authorities.extend(
                (
                    membership_authority("index", stock_identity_key=stock_key, episode=episode),
                    membership_authority("board", stock_identity_key=stock_key, episode=episode),
                )
            )
        revised = replace(
            item,
            stock_signals=tuple(stock_signals),
            scope_rows=tuple(scope_rows),
            index_memberships=tuple(index_rows),
            board_memberships=tuple(board_rows),
            membership_authorities=tuple(authorities),
        )
        matches = build_worker_plan(
            snapshot(revised), evaluator_run_id="strategy-center-337-plus-6"
        ).work_plans[0].matches
        self.assertEqual(len(matches), 343)
        quality_counts = {
            quality: sum(match.mapping_quality == quality for match in matches)
            for quality in ("passed", "missing_index")
        }
        self.assertEqual(quality_counts, {"passed": 337, "missing_index": 6})

    def test_parent_executed_evidence_requires_direction_match(self) -> None:
        item = evaluation_input()
        buy_parents = tuple(
            replace(parent, direction="buy") for parent in item.parent_executed_events
        )
        signal = replace(
            item.stock_signals[0], signal={**item.stock_signals[0].signal, "direction": "sell"}
        )
        mismatched = build_worker_plan(
            snapshot(
                replace(
                    item,
                    stock_signals=(signal,),
                    parent_executed_events=buy_parents,
                )
            ),
            evaluator_run_id="strategy-center-direction-mismatch",
        ).work_plans[0].matches
        self.assertEqual(mismatched, ())

        sell_parents = tuple(
            replace(parent, direction="sell")
            for parent in item.parent_executed_events
        )
        match = build_worker_plan(
            snapshot(
                replace(
                    item,
                    stock_signals=(signal,),
                    parent_executed_events=sell_parents,
                )
            ),
            evaluator_run_id="strategy-center-direction-match",
        ).work_plans[0].matches[0]
        self.assertEqual(match.matched_packages, ("package_1", "package_2"))

    def test_plan_preserves_canonical_signals_dto_and_dual_package_one_row(self) -> None:
        plan = build_worker_plan(
            snapshot(), evaluator_run_id="strategy-center-20260722-001"
        )
        self.assertEqual(len(plan.work_plans), 1)
        match = plan.work_plans[0].matches[0]
        self.assertEqual(match.matched_packages, ("package_1", "package_2"))
        self.assertEqual(
            match.signal["all_existing_signal_fields"],
            "canonical-app-signal-item",
        )
        self.assertEqual(len(plan.plan_hash), 64)

    def test_bounded_scope_is_frozen_in_snapshot_plan_and_input_watermark(self) -> None:
        worker_snapshot = snapshot(scope=BOUNDED_SCOPE)
        plan = build_worker_plan(
            worker_snapshot,
            evaluator_run_id="strategy-center-bounded-freeze",
        )
        self.assertEqual(plan.evaluator_scope, BOUNDED_SCOPE)
        self.assertEqual(plan.input_watermark, worker_snapshot.snapshot_hash)
        self.assertEqual(plan.work_plans[0].selection.selection_revision_id, 9)

        repository = object.__new__(PostgresStrategyCenterEvaluatorRepository)
        repository._validate_plan_integrity(plan)
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked, "strategy_worker_plan_scope_invalid"
        ):
            repository._validate_plan_integrity(
                replace(plan, input_watermark="0" * 64)
            )
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked, "strategy_worker_plan_scope_invalid"
        ):
            repository._validate_plan_integrity(
                replace(
                    plan,
                    evaluator_scope=StrategyEvaluatorScope(2, 3, 10),
                )
            )

        class MismatchedRepository:
            def load_snapshot(self, _trade_date, *, scope=None):
                return snapshot()

            def commit_plan(self, _plan):
                raise AssertionError("scope mismatch must not commit")

        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked, "strategy_evaluator_scope_mismatch"
        ):
            run_strategy_center_once(
                repository=MismatchedRepository(),
                trade_date=TRADE_DATE,
                evaluator_run_id="strategy-center-scope-mismatch",
                scope=BOUNDED_SCOPE,
            )

    def test_revision_superseded_before_commit_fails_closed(self) -> None:
        repository = object.__new__(PostgresStrategyCenterEvaluatorRepository)
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked, "selection_revision_status_invalid"
        ):
            repository._work_item(
                self._work_item_row(selection_status="superseded"),
                trade_date=TRADE_DATE,
                scope=BOUNDED_SCOPE,
            )

    def test_pending_activation_targets_only_frozen_revisions(self) -> None:
        class Cursor:
            def __init__(self):
                self.queries = []
                self.rowcount = 0

            def execute(self, query, params):
                self.queries.append((query, params))
                self.rowcount = 1

        cursor = Cursor()
        PostgresStrategyCenterEvaluatorRepository._activate_pending(
            cursor,
            selection("pending"),
            evaluator_scope=BOUNDED_SCOPE,
        )
        self.assertEqual(len(cursor.queries), 2)
        supersede_sql = " ".join(cursor.queries[0][0].split()).lower()
        activate_sql = " ".join(cursor.queries[1][0].split()).lower()
        self.assertIn(
            "selection_revision_id = %(active_revision_id)s", supersede_sql
        )
        self.assertNotIn("selection_revision_id <>", supersede_sql)
        self.assertIn(
            "selection_revision_id = %(selection_revision_id)s", activate_sql
        )
        self.assertIn("selection_status = 'pending'", activate_sql)

    def test_same_evaluator_run_and_input_replay_is_stable(self) -> None:
        first = build_worker_plan(
            snapshot(scope=BOUNDED_SCOPE),
            evaluator_run_id="strategy-center-bounded-idempotent",
        )
        second = build_worker_plan(
            snapshot(scope=BOUNDED_SCOPE),
            evaluator_run_id="strategy-center-bounded-idempotent",
        )
        self.assertEqual(first.plan_hash, second.plan_hash)
        self.assertEqual(first.snapshot_hash, second.snapshot_hash)
        self.assertEqual(first.work_plans, second.work_plans)

    def test_frozen_replay_requires_bounded_scope(self) -> None:
        worker_snapshot = snapshot()
        plan = build_worker_plan(
            worker_snapshot, evaluator_run_id="strategy-center-frozen-replay"
        )
        repository = PostgresStrategyCenterEvaluatorRepository.__new__(
            PostgresStrategyCenterEvaluatorRepository
        )
        with self.assertRaises(StrategyCenterWorkerBlocked) as error:
            repository.commit_frozen_replay(plan)
        self.assertEqual(
            str(error.exception), "strategy_frozen_replay_scope_required"
        )

    def test_evaluation_time_is_frozen_in_snapshot_plan_and_summary(self) -> None:
        first_snapshot = snapshot(
            evaluation_time="2026-07-22T09:40:00+08:00"
        )
        second_snapshot = snapshot(
            evaluation_time="2026-07-22T09:41:00+08:00"
        )
        first_plan = build_worker_plan(
            first_snapshot,
            evaluator_run_id="strategy-center-evaluation-time-authority",
        )
        second_plan = build_worker_plan(
            second_snapshot,
            evaluator_run_id="strategy-center-evaluation-time-authority",
        )
        self.assertNotEqual(
            first_snapshot.snapshot_hash, second_snapshot.snapshot_hash
        )
        self.assertNotEqual(first_plan.plan_hash, second_plan.plan_hash)
        self.assertEqual(first_plan.evaluation_time, first_snapshot.evaluation_time)

        summary = run_strategy_center_once(
            repository=FakeRepository(first_snapshot),
            trade_date=TRADE_DATE,
            evaluator_run_id="strategy-center-evaluation-time-summary",
        )
        self.assertEqual(summary["evaluation_time"], first_snapshot.evaluation_time)

        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "strategy_worker_plan_scope_invalid",
        ):
            PostgresStrategyCenterEvaluatorRepository._validate_plan_integrity(
                replace(
                    first_plan,
                    evaluation_time="2026-07-22T09:41:00+08:00",
                )
            )

    def test_dry_primary_replay_reuse_one_frozen_evaluation_time(self) -> None:
        repository = FakeRepository(snapshot(scope=BOUNDED_SCOPE))
        dry = run_strategy_center_once(
            repository=repository,
            trade_date=TRADE_DATE,
            evaluator_run_id="strategy-center-time-dry",
            scope=BOUNDED_SCOPE,
        )
        primary = run_strategy_center_once(
            repository=repository,
            trade_date=TRADE_DATE,
            evaluator_run_id="strategy-center-time-primary",
            scope=BOUNDED_SCOPE,
            evaluation_time=dry["evaluation_time"],
            execute=True,
            runtime_authorized=True,
        )
        replay = run_strategy_center_once(
            repository=repository,
            trade_date=TRADE_DATE,
            evaluator_run_id="strategy-center-time-replay",
            scope=BOUNDED_SCOPE,
            evaluation_time=dry["evaluation_time"],
            execute=True,
            runtime_authorized=True,
        )
        self.assertEqual(primary["evaluation_time"], dry["evaluation_time"])
        self.assertEqual(replay["evaluation_time"], dry["evaluation_time"])
        self.assertEqual(primary["snapshot_hash"], dry["snapshot_hash"])
        self.assertEqual(replay["snapshot_hash"], dry["snapshot_hash"])
        self.assertEqual(primary["input_watermark"], dry["input_watermark"])
        self.assertEqual(replay["input_watermark"], dry["input_watermark"])

    def test_primary_rejects_repository_evaluation_time_drift(self) -> None:
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "strategy_evaluation_time_input_mismatch",
        ):
            run_strategy_center_once(
                repository=FakeRepository(
                    snapshot(
                        scope=BOUNDED_SCOPE,
                        evaluation_time="2026-07-22T09:41:00+08:00",
                    )
                ),
                trade_date=TRADE_DATE,
                evaluator_run_id="strategy-center-time-drift",
                scope=BOUNDED_SCOPE,
                evaluation_time=EVALUATION_TIME,
            )

    def test_invalid_evaluation_time_authority_fails_closed(self) -> None:
        valid = snapshot()
        for invalid in (
            "",
            "2026-07-22T09:40:00",
            "2026-07-21T09:40:00+08:00",
            "2026-07-22T01:40:00Z",
            "2026-07-22T09:40:00+09:00",
        ):
            with self.subTest(evaluation_time=invalid), self.assertRaisesRegex(
                StrategyCenterWorkerBlocked,
                "strategy_evaluation_time_authority_invalid",
            ):
                build_worker_plan(
                    replace(valid, evaluation_time=invalid),
                    evaluator_run_id="strategy-center-invalid-evaluation-time",
                )
            with self.subTest(
                snapshot_hash_evaluation_time=invalid
            ), self.assertRaisesRegex(
                StrategyCenterWorkerBlocked,
                "strategy_evaluation_time_authority_invalid",
            ):
                snapshot_hash(
                    TRADE_DATE,
                    valid.inputs,
                    evaluation_time=invalid,
                )

    def test_pending_activation_replay_keeps_input_and_plan_hash_stable(self) -> None:
        pending_selection = selection("pending")
        active_selection = replace(
            selection("active"),
            previous_revision_id=pending_selection.previous_revision_id,
        )
        pending_input = replace(
            evaluation_input(),
            selection=pending_selection,
            evaluator_scope=BOUNDED_SCOPE,
        )
        active_input = replace(
            evaluation_input(),
            selection=active_selection,
            evaluator_scope=BOUNDED_SCOPE,
        )
        pending_snapshot = snapshot(pending_input, scope=BOUNDED_SCOPE)
        active_snapshot = snapshot(active_input, scope=BOUNDED_SCOPE)
        pending_plan = build_worker_plan(
            pending_snapshot,
            evaluator_run_id="strategy-center-stable-activation-replay",
        )
        active_plan = build_worker_plan(
            active_snapshot,
            evaluator_run_id="strategy-center-stable-activation-replay",
        )

        self.assertEqual(
            pending_snapshot.snapshot_hash, active_snapshot.snapshot_hash
        )
        self.assertEqual(pending_plan.plan_hash, active_plan.plan_hash)
        self.assertNotEqual(
            pending_plan.selection_cas_watermark,
            active_plan.selection_cas_watermark,
        )

    def test_selected_package_and_catalog_authority_change_input_hash(self) -> None:
        item = evaluation_input()
        package_changed = replace(
            item,
            selection=replace(
                item.selection,
                selected_package_keys=("package_1",),
            ),
        )
        catalog_changed = replace(
            item,
            selection=replace(
                item.selection,
                selected_package_authority=(
                    f"package_1|v2|{PACKAGE_1_POLICY_HASH}",
                    f"package_2|v2|{'3' * 64}",
                ),
            ),
        )
        original = snapshot_hash(
            TRADE_DATE, (item,), evaluation_time=EVALUATION_TIME
        )
        self.assertNotEqual(
            original,
            snapshot_hash(
                TRADE_DATE,
                (package_changed,),
                evaluation_time=EVALUATION_TIME,
            ),
        )
        self.assertNotEqual(
            original,
            snapshot_hash(
                TRADE_DATE,
                (catalog_changed,),
                evaluation_time=EVALUATION_TIME,
            ),
        )

    def test_target_and_predecessor_lifecycle_change_only_cas_hash(self) -> None:
        item = evaluation_input()
        changed = replace(
            item,
            selection=replace(
                item.selection,
                replay_status="failed",
                active_revision_authority="active-revision-9-changed",
            ),
        )
        self.assertEqual(
            snapshot_hash(
                TRADE_DATE, (item,), evaluation_time=EVALUATION_TIME
            ),
            snapshot_hash(
                TRADE_DATE, (changed,), evaluation_time=EVALUATION_TIME
            ),
        )
        self.assertNotEqual(
            selection_cas_hash((item,)),
            selection_cas_hash((changed,)),
        )

    def test_pending_predecessor_must_equal_frozen_active_revision(self) -> None:
        pending = replace(
            evaluation_input(),
            selection=replace(
                selection("pending"),
                previous_revision_id=7,
                active_revision_id=8,
            ),
        )
        invalid_snapshot = snapshot(pending)
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "pending_selection_predecessor_invalid",
        ):
            build_worker_plan(
                invalid_snapshot,
                evaluator_run_id="strategy-center-invalid-predecessor",
            )

    def test_signal_scope_and_membership_changes_input_hash(self) -> None:
        item = evaluation_input()
        signal_changed = replace(
            item,
            stock_signals=(
                replace(item.stock_signals[0], event_id="evt-stock-changed"),
            ),
        )
        scope_changed = replace(
            item,
            scope_rows=(ScopeRow(TRADE_DATE, STOCK, "realtime_scope"),),
        )
        membership_changed = replace(
            item,
            membership_authorities=(
                replace(
                    item.membership_authorities[0],
                    source_version="membership-v2",
                ),
                item.membership_authorities[1],
            ),
        )
        original = snapshot_hash(
            TRADE_DATE, (item,), evaluation_time=EVALUATION_TIME
        )
        for changed in (signal_changed, scope_changed, membership_changed):
            self.assertNotEqual(
                original,
                snapshot_hash(
                    TRADE_DATE,
                    (changed,),
                    evaluation_time=EVALUATION_TIME,
                ),
            )

    def test_tampered_lifecycle_cas_watermark_is_rejected(self) -> None:
        plan = build_worker_plan(
            snapshot(scope=BOUNDED_SCOPE),
            evaluator_run_id="strategy-center-lifecycle-cas",
        )
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "strategy_worker_plan_scope_invalid",
        ):
            PostgresStrategyCenterEvaluatorRepository._validate_plan_integrity(
                replace(plan, selection_cas_watermark="0" * 64)
            )

    def test_predecessor_lifecycle_drift_rejects_commit_before_writes(self) -> None:
        initial = snapshot(scope=BOUNDED_SCOPE)
        plan = build_worker_plan(
            initial,
            evaluator_run_id="strategy-center-predecessor-drift",
        )
        changed_input = replace(
            initial.inputs[0],
            selection=replace(
                initial.inputs[0].selection,
                active_revision_authority="unexpected-predecessor",
            ),
        )
        current = replace(
            initial,
            inputs=(changed_input,),
            selection_cas_hash=selection_cas_hash((changed_input,)),
        )
        repository = PostgresStrategyCenterEvaluatorRepository(
            "service=n6_strategy_worker"
        )
        connection_context = MagicMock()
        connection = connection_context.__enter__.return_value
        transaction_context = connection.transaction.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"acquired": True}
        with (
            patch(
                "ashare_v3.user.strategy_center_worker.psycopg.connect",
                return_value=connection_context,
            ),
            patch.object(repository, "_load_snapshot", return_value=current),
            patch.object(repository, "_apply_plan") as apply_plan,
            self.assertRaisesRegex(
                StrategyCenterWorkerBlocked,
                "strategy_selection_lifecycle_cas_mismatch",
            ),
        ):
            repository.commit_plan(plan)
        apply_plan.assert_not_called()
        self.assertTrue(transaction_context.__exit__.called)

    def test_primary_apply_failure_exits_transaction_without_commit(self) -> None:
        current = snapshot(scope=BOUNDED_SCOPE)
        plan = build_worker_plan(
            current,
            evaluator_run_id="strategy-center-primary-rollback",
        )
        repository = PostgresStrategyCenterEvaluatorRepository(
            "service=n6_strategy_worker"
        )
        connection_context = MagicMock()
        connection = connection_context.__enter__.return_value
        transaction_context = connection.transaction.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"acquired": True}
        with (
            patch(
                "ashare_v3.user.strategy_center_worker.psycopg.connect",
                return_value=connection_context,
            ),
            patch.object(repository, "_load_snapshot", return_value=current),
            patch.object(
                repository,
                "_apply_plan",
                side_effect=RuntimeError("simulated_apply_failure"),
            ),
            self.assertRaisesRegex(RuntimeError, "simulated_apply_failure"),
        ):
            repository.commit_plan(plan)
        self.assertTrue(transaction_context.__exit__.called)
        exit_args = transaction_context.__exit__.call_args.args
        self.assertIs(exit_args[0], RuntimeError)

    def test_later_executed_updates_state_and_preserves_frozen_parent_lineage(self) -> None:
        item = evaluation_input()
        executed = replace(
            item.stock_signals[0],
            user_signal_projection_id=102,
            event_id="evt-stock-executed",
            event_type="ActionExecuted",
            action_state="executed",
            event_time="2026-07-22T09:41:00+08:00",
            signal={
                **item.stock_signals[0].signal,
                "user_signal_projection_id": "102",
                "event_type": "ActionExecuted",
                "action_state": "executed",
            },
        )
        revised = replace(
            item,
            stock_signals=(item.stock_signals[0], executed),
        )
        eligible_match = build_worker_plan(
            snapshot(item),
            evaluator_run_id="strategy-center-state-before-upgrade",
        ).work_plans[0].matches[0]
        revised = replace(revised, frozen_matches=(eligible_match,))
        match = build_worker_plan(
            snapshot(revised),
            evaluator_run_id="strategy-center-state-upgrade",
        ).work_plans[0].matches[0]
        self.assertEqual(match.action_state, "executed")
        self.assertEqual(match.source_signal_projection_id, 102)
        self.assertIn(executed.event_id, match.source_event_ids)
        self.assertEqual(
            [row["event_id"] for row in match.state_timeline],
            [item.stock_signals[0].event_id, executed.event_id],
        )
        self.assertEqual(
            match.coherence_episode_key,
            eligible_match.coherence_episode_key,
        )
        self.assertEqual(
            match.confluence["package_evidence"],
            eligible_match.confluence["package_evidence"],
        )
        self.assertEqual(len((match,)), 1)

    def test_frozen_episode_authority_is_part_of_snapshot_hash_and_plan(self) -> None:
        item = evaluation_input()
        initial = snapshot(item)
        frozen_match = build_worker_plan(
            initial,
            evaluator_run_id="strategy-center-freeze-authority-initial",
        ).work_plans[0].matches[0]
        frozen_item = replace(item, frozen_matches=(frozen_match,))
        frozen_snapshot = snapshot(frozen_item)
        self.assertNotEqual(initial.snapshot_hash, frozen_snapshot.snapshot_hash)
        plan = build_worker_plan(
            frozen_snapshot,
            evaluator_run_id="strategy-center-freeze-authority-replay",
        )
        self.assertEqual(plan.input_watermark, frozen_snapshot.snapshot_hash)
        self.assertEqual(
            plan.work_plans[0].matches[0].coherence_episode_key,
            frozen_match.coherence_episode_key,
        )

    def test_persisted_match_row_reconstructs_frozen_episode_authority(self) -> None:
        item = evaluation_input()
        match = build_worker_plan(
            snapshot(item),
            evaluator_run_id="strategy-center-persisted-freeze-source",
        ).work_plans[0].matches[0]
        row = {
            "trade_date": match.trade_date,
            "stock_identity_key": match.stock_identity_key,
            "action_episode_key": match.action_episode_key,
            "coherence_episode_key": match.coherence_episode_key,
            "action_state": match.action_state,
            "source_signal_projection_id": match.source_signal_projection_id,
            "source_event_ids": list(match.source_event_ids),
            "matched_packages": list(match.matched_packages),
            "scope_sources": list(match.scope_sources),
            "indices_json": list(match.indices),
            "matched_boards_json": list(match.matched_boards),
            "signal_json": dict(match.signal),
            "state_timeline_json": list(match.state_timeline),
            "mapping_quality": match.mapping_quality,
            "membership_source_trade_date": (
                match.membership_source_trade_date
            ),
            "confluence_json": dict(match.confluence),
            "evaluator_policy_hash": match.evaluator_policy_hash,
            "projection_hash": match.projection_hash,
        }
        reconstructed = (
            PostgresStrategyCenterEvaluatorRepository
            ._frozen_candidate_from_row(
                row,
                surface_kind="qualified_match",
            )
        )
        self.assertEqual(reconstructed, match)

    def test_upsert_matched_at_uses_frozen_confirmation_time(self) -> None:
        item = evaluation_input()
        revised = replace(
            item,
            stock_signals=(
                replace(
                    item.stock_signals[0],
                    event_time="2026-07-22T09:30:00+08:00",
                ),
            ),
            parent_executed_events=tuple(
                replace(
                    event,
                    event_time="2026-07-22T09:31:00+08:00",
                )
                for event in item.parent_executed_events
            ),
        )
        plan = build_worker_plan(
            snapshot(
                revised,
                evaluation_time="2026-07-22T09:31:00+08:00",
            ),
            evaluator_run_id="strategy-center-confirmation-matched-at",
        )
        work = plan.work_plans[0]
        match = work.matches[0]
        self.assertEqual(
            match.confluence["confirmation_time"],
            "2026-07-22T09:31:00+08:00",
        )

        class Cursor:
            def __init__(self) -> None:
                self.calls = []

            def execute(self, query, params) -> None:
                self.calls.append((query, dict(params)))

            def fetchone(self):
                return {"strategy_match_projection_id": 901}

        cursor = Cursor()
        repository = object.__new__(PostgresStrategyCenterEvaluatorRepository)
        projection_id = repository._upsert_match(
            cursor,
            plan,
            work.selection,
            match,
            None,
        )
        self.assertEqual(projection_id, 901)
        self.assertEqual(
            cursor.calls[0][1]["matched_at"],
            "2026-07-22T09:31:00+08:00",
        )
        self.assertNotEqual(
            cursor.calls[0][1]["matched_at"],
            match.state_timeline[0]["event_time"],
        )

        update_cursor = Cursor()
        repository._upsert_match(
            update_cursor,
            plan,
            work.selection,
            match,
            {
                "strategy_match_projection_id": 901,
                "matched_at": "2026-07-22T09:31:00+08:00",
            },
        )
        update_sql = " ".join(update_cursor.calls[0][0].lower().split())
        self.assertTrue(update_sql.startswith("update n6_strategy_match_projection"))
        self.assertNotIn("matched_at =", update_sql)

        mismatch_cursor = Cursor()
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "strategy_projection_matched_at_mismatch",
        ):
            repository._upsert_match(
                mismatch_cursor,
                plan,
                work.selection,
                match,
                {
                    "strategy_match_projection_id": 901,
                    "matched_at": "2026-07-22T09:30:00+08:00",
                },
            )
        self.assertEqual(mismatch_cursor.calls, [])

    def test_invalid_confirmation_time_fails_before_projection_write(self) -> None:
        plan = build_worker_plan(
            snapshot(),
            evaluator_run_id="strategy-center-invalid-confirmation",
        )
        work = plan.work_plans[0]
        match = work.matches[0]

        class Cursor:
            def __init__(self) -> None:
                self.calls = []

            def execute(self, query, params) -> None:
                self.calls.append((query, params))

            def fetchone(self):
                return {"strategy_match_projection_id": 902}

        valid_audit = dict(match.confluence)
        invalid_values = (
            None,
            "",
            "not-a-timestamp",
            "2026-07-22T09:40:00",
            "2026-07-21T09:40:00+08:00",
            "2026-07-22T12:00:00+08:00",
        )
        repository = object.__new__(PostgresStrategyCenterEvaluatorRepository)
        for value in invalid_values:
            with self.subTest(value=value):
                audit = dict(valid_audit)
                if value is None:
                    audit.pop("confirmation_time", None)
                else:
                    audit["confirmation_time"] = value
                invalid_match = replace(
                    match,
                    confluence=audit,
                )
                cursor = Cursor()
                with self.assertRaisesRegex(
                    StrategyCenterWorkerBlocked,
                    "strategy_match_confirmation_time_invalid",
                ):
                    repository._upsert_match(
                        cursor,
                        plan,
                        work.selection,
                        invalid_match,
                        None,
                    )
                self.assertEqual(cursor.calls, [])

    def test_observation_observed_at_mismatch_fails_before_any_sql(self) -> None:
        item = evaluation_input()
        weak_input = replace(
            item,
            stock_signals=(
                replace(
                    item.stock_signals[0],
                    event_time="2026-07-22T10:03:00+08:00",
                ),
            ),
        )
        plan = build_worker_plan(
            snapshot(
                weak_input,
                evaluation_time="2026-07-22T10:03:00+08:00",
            ),
            evaluator_run_id="strategy-center-weak-observed-at-guard",
        )
        work = plan.work_plans[0]
        observation = work.observations[0]

        class Cursor:
            def __init__(self) -> None:
                self.calls = []

            def execute(self, query, params) -> None:
                self.calls.append((query, params))

            def fetchone(self):
                return {"strategy_observation_projection_id": 902}

        cursor = Cursor()
        repository = object.__new__(PostgresStrategyCenterEvaluatorRepository)
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "strategy_observation_observed_at_mismatch",
        ):
            repository._upsert_observation(
                cursor,
                plan,
                work.selection,
                observation,
                {
                    "strategy_observation_projection_id": 902,
                    "observed_at": "2026-07-22T10:02:00+08:00",
                },
            )
        self.assertEqual(cursor.calls, [])

    def test_dry_run_never_commits(self) -> None:
        repository = FakeRepository(snapshot())
        result = run_strategy_center_once(
            repository=repository,
            trade_date=TRADE_DATE,
            evaluator_run_id="strategy-center-20260722-dry",
        )
        self.assertEqual(result["status"], "dry_run")
        self.assertFalse(result["write_called"])
        self.assertEqual(result["evaluation_time"], snapshot().evaluation_time)
        self.assertEqual(repository.commits, [])

    def test_execute_requires_runtime_authorization_then_commits_exact_plan(self) -> None:
        repository = FakeRepository(snapshot(scope=BOUNDED_SCOPE))
        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked, "runtime_authorization_required"
        ):
            run_strategy_center_once(
                repository=repository,
                trade_date=TRADE_DATE,
                evaluator_run_id="strategy-center-20260722-exec",
                execute=True,
                scope=BOUNDED_SCOPE,
            )
        self.assertEqual(repository.loads, [])
        self.assertEqual(repository.commits, [])
        result = run_strategy_center_once(
            repository=repository,
            trade_date=TRADE_DATE,
            evaluator_run_id="strategy-center-20260722-exec",
            execute=True,
            runtime_authorized=True,
            scope=BOUNDED_SCOPE,
            evaluation_time=EVALUATION_TIME,
        )
        self.assertTrue(result["write_called"])
        self.assertEqual(
            repository.loads,
            [(TRADE_DATE, BOUNDED_SCOPE, EVALUATION_TIME)],
        )
        self.assertEqual(len(repository.commits), 1)
        self.assertEqual(
            repository.commits[0].snapshot_hash,
            snapshot(scope=BOUNDED_SCOPE).snapshot_hash,
        )

    def test_execute_rejects_unbounded_targets_before_load_or_commit(self) -> None:
        class NeverLoadedRepository:
            def __init__(self) -> None:
                self.load_count = 0
                self.commit_count = 0

            def load_snapshot(self, *_args, **_kwargs):
                self.load_count += 1
                raise AssertionError("unbounded execute must not load")

            def commit_plan(self, _plan):
                self.commit_count += 1
                raise AssertionError("unbounded execute must not commit")

        for selection_revision_ids in (None, [9]):
            repository = NeverLoadedRepository()
            with self.subTest(
                selection_revision_ids=selection_revision_ids
            ), self.assertRaisesRegex(
                StrategyCenterWorkerBlocked,
                "strategy_evaluator_execute_scope_invalid",
            ):
                run_strategy_center_once(
                    repository=repository,
                    trade_date=TRADE_DATE,
                    evaluator_run_id="strategy-center-unbounded-execute",
                    execute=True,
                    runtime_authorized=True,
                    selection_revision_ids=selection_revision_ids,
                )
            self.assertEqual(repository.load_count, 0)
            self.assertEqual(repository.commit_count, 0)

    def test_missing_canonical_dto_fails_closed(self) -> None:
        plan = build_worker_plan(
            snapshot(evaluation_input(canonical_signal=False)),
            evaluator_run_id="strategy-center-20260722-missing",
        )
        self.assertEqual(plan.work_plans[0].matches, ())

    def test_parent_late_arrival_replay_converges(self) -> None:
        item = evaluation_input()
        before = replace(item, parent_executed_events=())
        before_plan = build_worker_plan(
            snapshot(before), evaluator_run_id="strategy-center-20260722-before"
        )
        after_plan = build_worker_plan(
            snapshot(item), evaluator_run_id="strategy-center-20260722-after"
        )
        self.assertEqual(before_plan.work_plans[0].matches, ())
        self.assertEqual(len(after_plan.work_plans[0].matches), 1)

    def test_worker_source_has_cas_lock_and_only_n6_strategy_writes(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "src/ashare_v3/user/strategy_center_worker.py"
        ).read_text(encoding="utf-8")
        for required in (
            "app_signal_item(dict(row))",
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ",
            "pg_try_advisory_xact_lock",
            "strategy_worker_snapshot_cas_mismatch",
            "INSERT INTO n6_strategy_match_projection",
            "INSERT INTO n6_strategy_match_change",
            "DELETE FROM n6_strategy_match_projection",
            "UPDATE n6_user_strategy_selection_revision",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "common_action_event",
            "common_event_outbox",
            "common_event_inbox",
            "n6_virtual_trade_proposal",
            "n6_virtual_order",
            "n6_virtual_trade ",
            "execute_proposal",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn(
            'if selection.selection_status == "active":\n'
            "                    self._insert_change(",
            source,
        )
        self.assertIn('change_type="reset"', source)
        self.assertIn(
            'f"{plan.evaluator_run_id}|{projection_id}|"', source
        )
        self.assertIn(
            'f"{plan.evaluator_run_id}|{plan.snapshot_hash}"', source
        )
        self.assertIn(
            "to_date(%(trade_date)s, 'YYYYMMDD'),\n"
            "                  %(stock_identity_key)s",
            source,
        )
        self.assertIn(
            "%(state_timeline_json)s, %(mapping_quality)s,\n"
            "                  to_date(%(membership_source_trade_date)s, 'YYYYMMDD')",
            source,
        )

    def test_worker_environment_is_exact_service_and_rejects_secret_overrides(self) -> None:
        good = {
            "PGSERVICE": "n6_strategy_worker",
            "PGSERVICEFILE": "/private/config/pg_service.conf",
            "PGPASSFILE": "/private/config/worker.pgpass",
        }
        validate_worker_environment(good)
        with self.assertRaises(ValueError):
            validate_worker_environment({**good, "PGSERVICE": "ashare_v3_owner"})
        with self.assertRaises(ValueError):
            validate_worker_environment({**good, "PGPASSWORD": "pollution"})
        with self.assertRaises(ValueError):
            validate_worker_environment({**good, "DATABASE_URL": "tempting"})

    def test_database_timeouts_are_explicit_and_fail_closed(self) -> None:
        self.assertEqual(DATABASE_LOCK_TIMEOUT_MS, 5_000)
        self.assertEqual(DATABASE_STATEMENT_TIMEOUT_MS, 30_000)
        for options in (
            READ_ONLY_CONNECTION_OPTIONS,
            WRITE_CONNECTION_OPTIONS,
        ):
            self.assertIn("lock_timeout=5000", options)
            self.assertIn("statement_timeout=30000", options)
        self.assertIn(
            "default_transaction_read_only=on",
            READ_ONLY_CONNECTION_OPTIONS,
        )

        class QueryCanceled(Exception):
            sqlstate = "57014"

        with self.assertRaisesRegex(
            StrategyCenterWorkerBlocked,
            "strategy_worker_database_timeout",
        ):
            _raise_database_timeout(QueryCanceled())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
