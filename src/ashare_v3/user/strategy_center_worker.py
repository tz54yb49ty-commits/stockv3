from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Mapping, Protocol, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ashare_v3.user.strategy_center import (
    ALLOWED_DIRECTIONS,
    ALLOWED_PACKAGES,
    APPROVED_PACKAGE_POLICY_HASHES_BY_VERSION,
    APPROVED_PACKAGE_POLICY_PAYLOADS_BY_VERSION,
    MembershipRow,
    MembershipSnapshotAuthority,
    PACKAGE_1,
    PACKAGE_2,
    ParentExecutedEvent,
    ScopeRow,
    StockSignalEvent,
    StrategyMatch,
    StrategyObservation,
    STRATEGY_VERSION_V1,
    STRATEGY_VERSION_V2,
    evaluate_strategy_center_versioned,
)
from ashare_v3.user.projection_plan import source_trade_date_for_event
from ashare_v3.user.strategy_center_repository import (
    N6StrategyCenterReadRepository,
)
from ashare_v3.web.n6_app_v1 import app_signal_item
from ashare_v3.web.n6_user_app import PostgresN6UserRepository


ADVISORY_LOCK_KEY = 586673704836777312
ADVISORY_LOCK_SQL = "SELECT pg_try_advisory_xact_lock(%s::bigint) AS acquired"
DATABASE_LOCK_TIMEOUT_MS = 5_000
DATABASE_STATEMENT_TIMEOUT_MS = 30_000
DATABASE_TIMEOUT_SQLSTATES = frozenset({"55P03", "57014"})
READ_ONLY_CONNECTION_OPTIONS = (
    "-c default_transaction_read_only=on "
    f"-c lock_timeout={DATABASE_LOCK_TIMEOUT_MS} "
    f"-c statement_timeout={DATABASE_STATEMENT_TIMEOUT_MS}"
)
WRITE_CONNECTION_OPTIONS = (
    f"-c lock_timeout={DATABASE_LOCK_TIMEOUT_MS} "
    f"-c statement_timeout={DATABASE_STATEMENT_TIMEOUT_MS}"
)
EVALUATOR_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,160}$")
PACKAGE_AUTHORITY_PATTERN = re.compile(
    r"^(package_[12])\|(v[12])\|([0-9a-f]{64})$"
)
SHANGHAI_TIMEZONE = timezone(timedelta(hours=8))
MEMBERSHIP_RELATION_BY_KIND = {
    "index": "v_n6_index_membership_fact",
    "board": "v_n6_board_membership_fact",
}


def _valid_trade_date(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{8}", value):
        return False
    try:
        return datetime.strptime(value, "%Y%m%d").strftime("%Y%m%d") == value
    except ValueError:
        return False


class StrategyCenterWorkerBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class N6DisplayBatchAuthority:
    asset_kind: str
    source_trade_date: str
    for_trade_date: str
    source_run_id: str
    row_count: int

    def __post_init__(self) -> None:
        if (
            self.asset_kind not in {"stock", "index", "board"}
            or not _valid_trade_date(self.source_trade_date)
            or not _valid_trade_date(self.for_trade_date)
            or not self.source_run_id
            or isinstance(self.row_count, bool)
            or not isinstance(self.row_count, int)
            or self.row_count <= 0
            or self.source_trade_date > self.for_trade_date
        ):
            raise ValueError("n6_display_batch_authority_invalid")


@dataclass(frozen=True)
class N6TradeDateAuthority:
    trade_date: str
    batches: tuple[N6DisplayBatchAuthority, ...]

    def __post_init__(self) -> None:
        if (
            not _valid_trade_date(self.trade_date)
            or tuple(item.asset_kind for item in self.batches)
            != ("stock", "index", "board")
            or any(
                item.for_trade_date != self.trade_date
                for item in self.batches
            )
        ):
            raise ValueError("n6_trade_date_authority_invalid")

    @property
    def membership_asof_upper_bound(self) -> str:
        return max(item.source_trade_date for item in self.batches)


def _raise_database_timeout(error: psycopg.Error) -> None:
    if getattr(error, "sqlstate", None) in DATABASE_TIMEOUT_SQLSTATES:
        raise StrategyCenterWorkerBlocked(
            "strategy_worker_database_timeout"
        ) from error


@dataclass(frozen=True)
class StrategyEvaluatorScope:
    principal_id: int
    user_id: int
    selection_revision_id: int

    def __post_init__(self) -> None:
        for value in (
            self.principal_id,
            self.user_id,
            self.selection_revision_id,
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("strategy_evaluator_scope_positive_integer_required")


@dataclass(frozen=True)
class SelectionWorkItem:
    selection_revision_id: int
    principal_id: int
    principal_type: str
    user_id: int
    revision_no: int
    selection_status: str
    replay_status: str
    previous_revision_id: int | None
    active_revision_id: int | None
    selected_package_keys: tuple[str, ...]
    selected_package_versions: tuple[str, ...] = ()
    selected_package_statuses: tuple[str, ...] = ()
    effective_trade_date: str = ""
    selection_immutable_authority: str = ""
    selected_package_authority: tuple[str, ...] = ()
    selected_package_rule_authority: tuple[str, ...] = ()
    selection_lifecycle_authority: str = ""
    active_revision_authority: str = ""

    @property
    def strategy_version(self) -> str:
        versions = set(self.selected_package_versions)
        if versions == {"v1"}:
            return STRATEGY_VERSION_V1
        if versions == {"v2"}:
            return STRATEGY_VERSION_V2
        raise StrategyCenterWorkerBlocked("selected_package_version_mixed")


@dataclass(frozen=True)
class EvaluationInput:
    selection: SelectionWorkItem
    scope_rows: tuple[ScopeRow, ...]
    stock_signals: tuple[StockSignalEvent, ...]
    index_memberships: tuple[MembershipRow, ...]
    board_memberships: tuple[MembershipRow, ...]
    parent_executed_events: tuple[ParentExecutedEvent, ...]
    membership_authorities: tuple[MembershipSnapshotAuthority, ...] = ()
    frozen_matches: tuple[StrategyMatch, ...] = ()
    frozen_observations: tuple[StrategyObservation, ...] = ()
    evaluator_scope: StrategyEvaluatorScope | None = None


@dataclass(frozen=True)
class WorkerSnapshot:
    trade_date: str
    evaluation_time: str
    inputs: tuple[EvaluationInput, ...]
    snapshot_hash: str
    evaluator_scope: StrategyEvaluatorScope | None = None
    selection_revision_ids: tuple[int, ...] | None = None
    selection_cas_hash: str = ""
    trade_date_authority: N6TradeDateAuthority | None = None
    source_watermarks: dict[str, Any] | None = None


@dataclass(frozen=True)
class AutoEvaluationState:
    trade_date: str
    pending_revision_ids: tuple[int, ...]
    source_watermarks: dict[str, Any]
    source_fingerprint: str
    pending_scopes: tuple[StrategyEvaluatorScope, ...] = ()
    active_scopes: tuple[StrategyEvaluatorScope, ...] = ()
    replay_pending_active_scopes: tuple[StrategyEvaluatorScope, ...] = ()
    trade_date_authority: N6TradeDateAuthority | None = None


@dataclass(frozen=True)
class WorkPlan:
    selection: SelectionWorkItem
    matches: tuple[StrategyMatch, ...]
    observations: tuple[StrategyObservation, ...]


@dataclass(frozen=True)
class WorkerPlan:
    trade_date: str
    evaluation_time: str
    evaluator_run_id: str
    snapshot_hash: str
    work_plans: tuple[WorkPlan, ...]
    plan_hash: str
    evaluator_scope: StrategyEvaluatorScope | None = None
    selection_revision_ids: tuple[int, ...] | None = None
    input_watermark: str = ""
    selection_cas_watermark: str = ""
    trade_date_authority: N6TradeDateAuthority | None = None
    source_watermarks: dict[str, Any] | None = None


class StrategyCenterEvaluatorRepository(Protocol):
    def load_snapshot(
        self,
        trade_date: str,
        *,
        scope: StrategyEvaluatorScope | None = None,
        selection_revision_ids: Sequence[int] | None = None,
        evaluation_time: str | None = None,
    ) -> WorkerSnapshot: ...

    def commit_plan(self, plan: WorkerPlan) -> Mapping[str, Any]: ...


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _selection_revision_ids(
    values: Sequence[int] | None,
) -> tuple[int, ...] | None:
    if values is None:
        return None
    if any(isinstance(value, bool) for value in values):
        raise ValueError("invalid_selection_revision_ids")
    normalized = tuple(sorted({int(value) for value in values}))
    if any(value <= 0 for value in normalized):
        raise ValueError("invalid_selection_revision_ids")
    return normalized


def _evaluation_selection_authority(
    selection: SelectionWorkItem,
) -> dict[str, Any]:
    """Return immutable selection inputs, excluding activation lifecycle state."""
    return {
        "selection_revision_id": selection.selection_revision_id,
        "principal_id": selection.principal_id,
        "principal_type": selection.principal_type,
        "user_id": selection.user_id,
        "revision_no": selection.revision_no,
        "previous_revision_id": selection.previous_revision_id,
        "selected_package_keys": selection.selected_package_keys,
        "selected_package_versions": selection.selected_package_versions,
        "selected_package_statuses": selection.selected_package_statuses,
        "effective_trade_date": selection.effective_trade_date,
        "selection_immutable_authority": selection.selection_immutable_authority,
        "selected_package_authority": selection.selected_package_authority,
        "selected_package_rule_authority": (
            selection.selected_package_rule_authority
        ),
    }


def _evaluation_input_authority(item: EvaluationInput) -> dict[str, Any]:
    value = asdict(item)
    value["selection"] = _evaluation_selection_authority(item.selection)
    return value


def selection_cas_hash(inputs: Sequence[EvaluationInput]) -> str:
    """Freeze mutable target/predecessor lifecycle separately from inputs."""
    return _selection_cas_hash(
        tuple(item.selection for item in inputs)
    )


def _selection_cas_hash(
    selections: Sequence[SelectionWorkItem],
) -> str:
    return _hash([asdict(selection) for selection in selections])


def _validate_selected_package_authority(
    selection: SelectionWorkItem,
) -> None:
    packages = selection.selected_package_keys
    versions = selection.selected_package_versions
    statuses = selection.selected_package_statuses
    authorities = selection.selected_package_authority
    rule_authorities = selection.selected_package_rule_authority
    if selection.selection_status == "pending" and (
        selection.previous_revision_id is None
        or selection.active_revision_id is None
        or selection.previous_revision_id != selection.active_revision_id
    ):
        raise StrategyCenterWorkerBlocked(
            "pending_selection_predecessor_invalid"
        )
    if (
        not packages
        or len(set(packages)) != len(packages)
        or any(package not in ALLOWED_PACKAGES for package in packages)
        or len(versions) != len(packages)
        or len(statuses) != len(packages)
        or len(authorities) != len(packages)
        or len(rule_authorities) != len(packages)
    ):
        raise StrategyCenterWorkerBlocked("selected_package_authority_invalid")

    authority_packages: set[str] = set()
    selected_versions: set[str] = set()
    for package, version, status, authority, rule_authority in zip(
        packages, versions, statuses, authorities, rule_authorities
    ):
        match = PACKAGE_AUTHORITY_PATTERN.fullmatch(authority)
        try:
            rule_payload = json.loads(rule_authority)
        except (TypeError, ValueError):
            rule_payload = None
        if (
            match is None
            or match.group(1) != package
            or match.group(2) != version
            or match.group(1) in authority_packages
            or match.group(3)
            != APPROVED_PACKAGE_POLICY_HASHES_BY_VERSION.get(
                (package, version)
            )
            or rule_payload
            != APPROVED_PACKAGE_POLICY_PAYLOADS_BY_VERSION.get(
                (package, version)
            )
            or rule_authority != _canonical_json(rule_payload)
            or (
                version == "v1"
                and status not in {"active", "grandfathered"}
            )
            or (
                version == "v2"
                and status not in {"active", "selectable"}
            )
        ):
            raise StrategyCenterWorkerBlocked(
                "selected_package_authority_invalid"
            )
        authority_packages.add(match.group(1))
        selected_versions.add(version)
    if authority_packages != set(packages):
        raise StrategyCenterWorkerBlocked("selected_package_authority_invalid")
    if len(selected_versions) != 1:
        raise StrategyCenterWorkerBlocked("selected_package_version_mixed")


def _validated_evaluation_time(value: object, trade_date: str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise StrategyCenterWorkerBlocked(
                "strategy_evaluation_time_authority_invalid"
            )
        authority = value.isoformat()
    elif isinstance(value, str):
        authority = value
    else:
        raise StrategyCenterWorkerBlocked(
            "strategy_evaluation_time_authority_invalid"
        )
    try:
        parsed = datetime.fromisoformat(authority.replace("Z", "+00:00"))
    except ValueError as error:
        raise StrategyCenterWorkerBlocked(
            "strategy_evaluation_time_authority_invalid"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StrategyCenterWorkerBlocked(
            "strategy_evaluation_time_authority_invalid"
        )
    if parsed.utcoffset() != SHANGHAI_TIMEZONE.utcoffset(None):
        raise StrategyCenterWorkerBlocked(
            "strategy_evaluation_time_authority_invalid"
        )
    if parsed.astimezone(SHANGHAI_TIMEZONE).strftime("%Y%m%d") != trade_date:
        raise StrategyCenterWorkerBlocked(
            "strategy_evaluation_time_authority_invalid"
        )
    return authority


def _same_aware_instant(left: object, right: object) -> bool:
    try:
        left_time = datetime.fromisoformat(str(left).replace("Z", "+00:00"))
        right_time = datetime.fromisoformat(str(right).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if (
        left_time.tzinfo is None
        or left_time.utcoffset() is None
        or right_time.tzinfo is None
        or right_time.utcoffset() is None
    ):
        return False
    return left_time.astimezone(timezone.utc) == right_time.astimezone(
        timezone.utc
    )


def _v2_standard_event_authority(
    row: Mapping[str, Any],
    *,
    canonical_signal: Mapping[str, Any] | None = None,
) -> tuple[str, str]:
    source_time = str(row.get("source_event_time") or "")
    projection_time = str(row.get("projection_event_time") or "")
    source_direction = str(row.get("source_direction") or "")
    projection_direction = str(row.get("projection_direction") or "")
    if (
        row.get("source_layer") != "N5_action"
        or not _same_aware_instant(source_time, projection_time)
        or source_direction not in ALLOWED_DIRECTIONS
        or projection_direction != source_direction
        or (
            canonical_signal is not None
            and str(canonical_signal.get("direction") or "")
            != source_direction
        )
    ):
        raise StrategyCenterWorkerBlocked(
            "n5_standard_event_authority_invalid"
        )
    return source_time, source_direction


def snapshot_hash(
    trade_date: str,
    inputs: Sequence[EvaluationInput],
    *,
    evaluation_time: str,
    scope: StrategyEvaluatorScope | None = None,
    selection_revision_ids: tuple[int, ...] | None = None,
    trade_date_authority: N6TradeDateAuthority | None = None,
    source_watermarks: Mapping[str, Any] | None = None,
) -> str:
    evaluation_time = _validated_evaluation_time(evaluation_time, trade_date)
    return _hash(
        {
            "trade_date": trade_date,
            "evaluation_time": evaluation_time,
            "evaluator_scope": asdict(scope) if scope is not None else None,
            "selection_revision_ids": selection_revision_ids,
            "trade_date_authority": (
                asdict(trade_date_authority)
                if trade_date_authority is not None
                else None
            ),
            "source_watermarks": (
                dict(source_watermarks)
                if source_watermarks is not None
                else None
            ),
            "inputs": [_evaluation_input_authority(item) for item in inputs],
        }
    )


def _validate_bounded_inputs(
    scope: StrategyEvaluatorScope | None,
    inputs: Sequence[EvaluationInput],
    selection_revision_ids: tuple[int, ...] | None = None,
) -> None:
    if scope is not None and selection_revision_ids is not None:
        raise StrategyCenterWorkerBlocked("strategy_evaluator_target_conflict")
    if scope is None:
        if any(item.evaluator_scope is not None for item in inputs):
            raise StrategyCenterWorkerBlocked("strategy_evaluator_scope_mismatch")
        if selection_revision_ids is not None and tuple(
            sorted(item.selection.selection_revision_id for item in inputs)
        ) != selection_revision_ids:
            raise StrategyCenterWorkerBlocked(
                "strategy_selection_authority_incomplete"
            )
        return
    if len(inputs) != 1:
        raise StrategyCenterWorkerBlocked("bounded_scope_work_item_count_invalid")
    item = inputs[0]
    if item.evaluator_scope != scope or (
        item.selection.principal_id != scope.principal_id
        or item.selection.user_id != scope.user_id
        or item.selection.selection_revision_id != scope.selection_revision_id
    ):
        raise StrategyCenterWorkerBlocked("bounded_scope_work_item_mismatch")


def _plan_body(
    *,
    trade_date: str,
    evaluation_time: str,
    evaluator_run_id: str,
    snapshot_hash_value: str,
    scope: StrategyEvaluatorScope | None,
    selection_revision_ids: tuple[int, ...] | None,
    work_plans: Sequence[WorkPlan],
    trade_date_authority: N6TradeDateAuthority | None = None,
    source_watermarks: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "evaluation_time": evaluation_time,
        "evaluator_run_id": evaluator_run_id,
        "snapshot_hash": snapshot_hash_value,
        "evaluator_scope": asdict(scope) if scope is not None else None,
        "selection_revision_ids": selection_revision_ids,
        "trade_date_authority": (
            asdict(trade_date_authority)
            if trade_date_authority is not None
            else None
        ),
        "source_watermarks": (
            dict(source_watermarks)
            if source_watermarks is not None
            else None
        ),
        "work_plans": [
            {
                "selection": _evaluation_selection_authority(item.selection),
                "matches": [match.as_payload() for match in item.matches],
                "observations": [
                    observation.as_payload()
                    for observation in item.observations
                ],
            }
            for item in work_plans
        ],
    }


def _validate_surface_partition(work_plan: WorkPlan) -> None:
    match_keys = {
        (
            item.stock_identity_key,
            item.action_episode_key,
            item.coherence_episode_key,
        )
        for item in work_plan.matches
    }
    observation_keys = {
        (
            item.stock_identity_key,
            item.action_episode_key,
            item.coherence_episode_key,
        )
        for item in work_plan.observations
    }
    if (
        len(match_keys) != len(work_plan.matches)
        or len(observation_keys) != len(work_plan.observations)
        or match_keys & observation_keys
    ):
        raise StrategyCenterWorkerBlocked(
            "strategy_surface_partition_invalid"
        )


def _reviewed_natural_event_group_count(item: EvaluationInput) -> int:
    if item.selection.strategy_version != STRATEGY_VERSION_V2:
        return 0
    parent_keys = {
        asset_kind: {
            event.identity_key
            for event in item.parent_executed_events
            if event.asset_kind == asset_kind
        }
        for asset_kind in ("index", "board")
    }
    board_by_stock: dict[str, set[str]] = {}
    index_by_stock: dict[str, set[str]] = {}
    for membership in item.board_memberships:
        board_by_stock.setdefault(
            membership.stock_identity_key, set()
        ).add(membership.parent_identity_key)
    for membership in item.index_memberships:
        index_by_stock.setdefault(
            membership.stock_identity_key, set()
        ).add(membership.parent_identity_key)
    count = 0
    for stock in item.stock_signals:
        has_board = bool(
            board_by_stock.get(stock.identity_key, set())
            & parent_keys.get("board", set())
        )
        has_index = bool(
            index_by_stock.get(stock.identity_key, set())
            & parent_keys.get("index", set())
        )
        if (
            PACKAGE_1 in item.selection.selected_package_keys
            and has_board
            and has_index
        ) or (
            PACKAGE_2 in item.selection.selected_package_keys
            and has_board
        ):
            count += 1
    return count


def build_worker_plan(
    snapshot: WorkerSnapshot, *, evaluator_run_id: str
) -> WorkerPlan:
    if not EVALUATOR_RUN_ID_PATTERN.fullmatch(evaluator_run_id):
        raise ValueError("invalid_evaluator_run_id")
    evaluation_time = _validated_evaluation_time(
        snapshot.evaluation_time, snapshot.trade_date
    )
    _validate_bounded_inputs(
        snapshot.evaluator_scope,
        snapshot.inputs,
        snapshot.selection_revision_ids,
    )
    for item in snapshot.inputs:
        _validate_selected_package_authority(item.selection)
    if snapshot.snapshot_hash != snapshot_hash(
        snapshot.trade_date,
        snapshot.inputs,
        evaluation_time=evaluation_time,
        scope=snapshot.evaluator_scope,
        selection_revision_ids=snapshot.selection_revision_ids,
        trade_date_authority=snapshot.trade_date_authority,
        source_watermarks=snapshot.source_watermarks,
    ):
        raise StrategyCenterWorkerBlocked("strategy_worker_snapshot_invalid")
    work_plans_list: list[WorkPlan] = []
    for item in snapshot.inputs:
        evaluated = evaluate_strategy_center_versioned(
            strategy_version=item.selection.strategy_version,
            trade_date=snapshot.trade_date,
            selected_package_keys=item.selection.selected_package_keys,
            stock_signals=item.stock_signals,
            scope_rows=item.scope_rows,
            index_memberships=item.index_memberships,
            board_memberships=item.board_memberships,
            parent_executed_events=item.parent_executed_events,
            membership_authorities=item.membership_authorities or None,
            evaluation_time=evaluation_time,
            frozen_matches=item.frozen_matches,
            frozen_observations=item.frozen_observations,
        )
        work_plan = WorkPlan(
            selection=item.selection,
            matches=evaluated.matches,
            observations=evaluated.observations,
        )
        _validate_surface_partition(work_plan)
        work_plans_list.append(work_plan)
    work_plans = tuple(work_plans_list)
    plan_body = _plan_body(
        trade_date=snapshot.trade_date,
        evaluation_time=evaluation_time,
        evaluator_run_id=evaluator_run_id,
        snapshot_hash_value=snapshot.snapshot_hash,
        scope=snapshot.evaluator_scope,
        selection_revision_ids=snapshot.selection_revision_ids,
        work_plans=work_plans,
        trade_date_authority=snapshot.trade_date_authority,
        source_watermarks=snapshot.source_watermarks,
    )
    return WorkerPlan(
        trade_date=snapshot.trade_date,
        evaluation_time=evaluation_time,
        evaluator_run_id=evaluator_run_id,
        snapshot_hash=snapshot.snapshot_hash,
        work_plans=work_plans,
        plan_hash=_hash(plan_body),
        evaluator_scope=snapshot.evaluator_scope,
        selection_revision_ids=snapshot.selection_revision_ids,
        input_watermark=snapshot.snapshot_hash,
        selection_cas_watermark=snapshot.selection_cas_hash,
        trade_date_authority=snapshot.trade_date_authority,
        source_watermarks=snapshot.source_watermarks,
    )


def run_strategy_center_once(
    *,
    repository: StrategyCenterEvaluatorRepository,
    trade_date: str,
    evaluator_run_id: str,
    execute: bool = False,
    runtime_authorized: bool = False,
    scope: StrategyEvaluatorScope | None = None,
    selection_revision_ids: Sequence[int] | None = None,
    evaluation_time: str | None = None,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9]{8}", trade_date):
        raise ValueError("invalid_trade_date")
    if scope is not None and not isinstance(scope, StrategyEvaluatorScope):
        raise ValueError("invalid_strategy_evaluator_scope")
    normalized_revision_ids = _selection_revision_ids(selection_revision_ids)
    if execute and not runtime_authorized:
        raise StrategyCenterWorkerBlocked("runtime_authorization_required")
    if execute and (scope is None or normalized_revision_ids is not None):
        raise StrategyCenterWorkerBlocked(
            "strategy_evaluator_execute_scope_invalid"
        )
    if scope is not None and normalized_revision_ids is not None:
        raise ValueError("strategy_evaluator_target_conflict")
    if execute and evaluation_time is None:
        raise StrategyCenterWorkerBlocked(
            "strategy_evaluation_time_required_for_execute"
        )
    if evaluation_time is not None:
        evaluation_time = _validated_evaluation_time(evaluation_time, trade_date)
    load_kwargs: dict[str, Any] = {"scope": scope}
    if normalized_revision_ids is not None:
        load_kwargs["selection_revision_ids"] = normalized_revision_ids
    if evaluation_time is not None:
        load_kwargs["evaluation_time"] = evaluation_time
    snapshot = repository.load_snapshot(trade_date, **load_kwargs)
    if snapshot.evaluator_scope != scope:
        raise StrategyCenterWorkerBlocked("strategy_evaluator_scope_mismatch")
    if snapshot.selection_revision_ids != normalized_revision_ids:
        raise StrategyCenterWorkerBlocked(
            "strategy_selection_revision_scope_mismatch"
        )
    if evaluation_time is not None and snapshot.evaluation_time != evaluation_time:
        raise StrategyCenterWorkerBlocked(
            "strategy_evaluation_time_input_mismatch"
        )
    plan = build_worker_plan(snapshot, evaluator_run_id=evaluator_run_id)
    natural_event_group_counts = {
        item.selection.selection_revision_id: (
            _reviewed_natural_event_group_count(item)
        )
        for item in snapshot.inputs
    }
    pending_v2_without_natural_events = tuple(
        item.selection.selection_revision_id
        for item in snapshot.inputs
        if item.selection.selection_status == "pending"
        and item.selection.strategy_version == STRATEGY_VERSION_V2
        and natural_event_group_counts[
            item.selection.selection_revision_id
        ]
        == 0
    )
    if execute and pending_v2_without_natural_events:
        raise StrategyCenterWorkerBlocked(
            "reviewed_n6_natural_event_group_missing"
        )
    summary = {
        "ok": True,
        "status": "dry_run" if not execute else "committed",
        "trade_date": trade_date,
        "evaluation_time": plan.evaluation_time,
        "evaluator_run_id": evaluator_run_id,
        "snapshot_hash": snapshot.snapshot_hash,
        "input_watermark": plan.input_watermark,
        "plan_hash": plan.plan_hash,
        "selection_cas_watermark": plan.selection_cas_watermark,
        "trade_date_authority": (
            asdict(plan.trade_date_authority)
            if plan.trade_date_authority is not None
            else None
        ),
        "source_watermarks": plan.source_watermarks,
        "reviewed_natural_event_group_counts": (
            natural_event_group_counts
        ),
        "pending_v2_without_natural_events": list(
            pending_v2_without_natural_events
        ),
        "ready_for_execute": not pending_v2_without_natural_events,
        "work_item_count": len(plan.work_plans),
        "match_count": sum(len(item.matches) for item in plan.work_plans),
        "observation_count": sum(
            len(item.observations) for item in plan.work_plans
        ),
        "weak_observation_count": sum(
            sum(
                observation.observation_reason == "weak_span"
                for observation in item.observations
            )
            for item in plan.work_plans
        ),
        "stale_observation_count": sum(
            sum(
                observation.observation_reason
                == "stale_after_confirmation"
                for observation in item.observations
            )
            for item in plan.work_plans
        ),
        "write_called": False,
        "display_only": True,
        "scope_mode": (
            "single_user_revision"
            if scope
            else (
                "selection_revision_set"
                if normalized_revision_ids is not None
                else "all_users"
            )
        ),
        "selection_revision_ids": (
            list(normalized_revision_ids)
            if normalized_revision_ids is not None
            else None
        ),
    }
    if scope is not None:
        summary.update(asdict(scope))
    if not execute:
        return summary
    commit_result = dict(repository.commit_plan(plan))
    summary["write_called"] = True
    summary["commit"] = commit_result
    return summary


WORK_ITEMS_SQL = """
WITH ranked_revision AS (
  SELECT revision.*,
         row_number() OVER (
           PARTITION BY revision.principal_id,
                        revision.principal_type,
                        revision.user_id
           ORDER BY
             CASE revision.selection_status WHEN 'pending' THEN 0 ELSE 1 END,
             revision.revision_no DESC
         ) AS revision_rank
  FROM n6_user_strategy_selection_revision revision
  JOIN n6_principal principal
    ON principal.principal_id = revision.principal_id
   AND principal.principal_type = revision.principal_type
   AND principal.owner_user_id = revision.user_id
   AND principal.principal_status = 'active'
  JOIN user_account account
    ON account.user_id = revision.user_id
   AND account.status = 'active'
  WHERE revision.selection_status IN ('pending', 'active')
    AND revision.effective_trade_date <= to_date(%(trade_date)s, 'YYYYMMDD')
), target_revision AS (
  SELECT revision.*
  FROM ranked_revision revision
  WHERE revision.revision_rank = 1
    AND (
      %(scope_mode)s = 'all_users'
      OR (
        %(scope_mode)s = 'single_user_revision'
        AND revision.principal_id = %(principal_id)s
        AND revision.user_id = %(user_id)s
        AND revision.selection_revision_id = %(selection_revision_id)s
      )
      OR (
        %(scope_mode)s = 'selection_revision_set'
        AND revision.selection_revision_id = ANY(
              %(selection_revision_ids)s::bigint[]
            )
      )
    )
)
SELECT target.selection_revision_id,
       target.principal_id,
       target.principal_type,
       target.user_id,
       target.revision_no,
       target.selection_status,
       target.replay_status,
       target.previous_revision_id,
       to_char(target.effective_trade_date, 'YYYYMMDD')
         AS effective_trade_date,
       (
         SELECT active.selection_revision_id
         FROM n6_user_strategy_selection_revision active
         WHERE active.principal_id = target.principal_id
           AND active.principal_type = target.principal_type
           AND active.user_id = target.user_id
           AND active.selection_status = 'active'
       ) AS active_revision_id,
       pg_catalog.min(pg_catalog.to_jsonb(target)::text)
         AS selection_lifecycle_authority,
       pg_catalog.min((
         pg_catalog.to_jsonb(target) - ARRAY[
           'selection_status', 'replay_status', 'activated_at',
           'superseded_at'
         ]::text[]
       )::text) AS selection_immutable_authority,
       (
         SELECT pg_catalog.to_jsonb(active)::text
         FROM n6_user_strategy_selection_revision active
         WHERE active.principal_id = target.principal_id
           AND active.principal_type = target.principal_type
           AND active.user_id = target.user_id
           AND active.selection_status = 'active'
       ) AS active_revision_authority,
       array_agg(item.package_key ORDER BY item.package_key)
         AS selected_package_keys,
       array_agg(item.package_version ORDER BY item.package_key)
         AS selected_package_versions,
       array_agg(catalog.package_status ORDER BY item.package_key)
         AS selected_package_statuses,
       array_agg(
         item.package_key || '|' || item.package_version || '|' ||
         catalog.policy_hash
         ORDER BY item.package_key, item.package_version
       ) AS selected_package_authority,
       array_agg(
         catalog.rule_json
         ORDER BY item.package_key, item.package_version
       ) AS selected_package_rule_authority
FROM target_revision target
JOIN n6_user_strategy_selection_item item
  ON item.selection_revision_id = target.selection_revision_id
JOIN n6_strategy_package_catalog catalog
 ON catalog.package_key = item.package_key
 AND catalog.package_version = item.package_version
 AND catalog.package_status IN ('active', 'selectable', 'grandfathered')
GROUP BY target.selection_revision_id,
         target.principal_id,
         target.principal_type,
         target.user_id,
         target.revision_no,
         target.selection_status,
         target.replay_status,
         target.previous_revision_id,
         target.effective_trade_date
HAVING count(*) > 0
   AND count(*) = (
     SELECT count(*)
     FROM n6_user_strategy_selection_item authority_item
     WHERE authority_item.selection_revision_id = target.selection_revision_id
   )
ORDER BY target.principal_id, target.user_id
"""


N6_TRADE_DATE_AUTHORITY_SQL = """
WITH stock_latest AS (
  SELECT max(for_trade_date) AS for_trade_date
  FROM v_n6_stock_condition_display_basis
), stock_batch AS (
  SELECT 'stock'::text AS asset_kind,
         min(source_trade_date::text) AS source_trade_date,
         min(approved.for_trade_date::text) AS for_trade_date,
         min(run_id::text) AS source_run_id,
         count(*)::bigint AS row_count
  FROM v_n6_stock_condition_display_basis approved
  JOIN stock_latest latest
    ON latest.for_trade_date = approved.for_trade_date
  HAVING count(*) > 0
     AND count(approved.source_trade_date) = count(*)
     AND count(approved.for_trade_date) = count(*)
     AND count(approved.run_id) = count(*)
     AND count(DISTINCT (
       approved.source_trade_date::text,
       approved.for_trade_date::text,
       approved.run_id::text
     )) = 1
), index_latest AS (
  SELECT max(for_trade_date) AS for_trade_date
  FROM v_n6_index_condition_display_basis
), index_batch AS (
  SELECT 'index'::text AS asset_kind,
         min(source_trade_date::text) AS source_trade_date,
         min(approved.for_trade_date::text) AS for_trade_date,
         min(run_id::text) AS source_run_id,
         count(*)::bigint AS row_count
  FROM v_n6_index_condition_display_basis approved
  JOIN index_latest latest
    ON latest.for_trade_date = approved.for_trade_date
  HAVING count(*) > 0
     AND count(approved.source_trade_date) = count(*)
     AND count(approved.for_trade_date) = count(*)
     AND count(approved.run_id) = count(*)
     AND count(DISTINCT (
       approved.source_trade_date::text,
       approved.for_trade_date::text,
       approved.run_id::text
     )) = 1
), board_latest AS (
  SELECT max(for_trade_date) AS for_trade_date
  FROM v_n6_board_condition_display_basis
), board_batch AS (
  SELECT 'board'::text AS asset_kind,
         min(source_trade_date::text) AS source_trade_date,
         min(approved.for_trade_date::text) AS for_trade_date,
         min(run_id::text) AS source_run_id,
         count(*)::bigint AS row_count
  FROM v_n6_board_condition_display_basis approved
  JOIN board_latest latest
    ON latest.for_trade_date = approved.for_trade_date
  HAVING count(*) > 0
     AND count(approved.source_trade_date) = count(*)
     AND count(approved.for_trade_date) = count(*)
     AND count(approved.run_id) = count(*)
     AND count(DISTINCT (
       approved.source_trade_date::text,
       approved.for_trade_date::text,
       approved.run_id::text
     )) = 1
)
SELECT asset_kind,
       source_trade_date,
       for_trade_date,
       source_run_id,
       row_count
FROM (
  SELECT * FROM stock_batch
  UNION ALL
  SELECT * FROM index_batch
  UNION ALL
  SELECT * FROM board_batch
) authority
ORDER BY CASE asset_kind
           WHEN 'stock' THEN 1
           WHEN 'index' THEN 2
           WHEN 'board' THEN 3
         END
"""

# Compatibility alias for callers importing the previous constant. Its
# authority is now exclusively the reviewed N6 display-view consensus.
AUTO_TRADE_DATE_SQL = N6_TRADE_DATE_AUTHORITY_SQL


AUTO_SOURCE_WATERMARKS_SQL = """
WITH projection_source AS (
  SELECT count(*)::bigint AS projection_count,
         count(DISTINCT r.user_projection_run_id)::bigint AS projection_run_count,
         max(p.user_signal_projection_id)::text AS max_projection_id,
         max(p.updated_at)::text AS max_projection_updated_at,
         max(r.updated_at)::text AS max_projection_run_updated_at
  FROM user_signal_projection p
  JOIN user_projection_run r
    ON r.user_projection_run_id = p.user_projection_run_id
   AND r.status IN ('passed', 'ready')
  WHERE p.user_id = ANY(%(signal_source_user_ids)s::bigint[])
    AND p.for_trade_date = pg_catalog.to_date(%(trade_date)s, 'YYYYMMDD')
    AND p.projection_status = 'visible'
    AND p.asset_kind IN ('stock', 'index', 'board')
    AND p.action_state IN ('eligible', 'executed')
), card_source AS (
  SELECT count(*)::bigint AS card_count,
         count(DISTINCT c.user_projection_run_id)::bigint AS card_run_count,
         max(c.user_signal_card_id)::text AS max_card_id,
         max(c.updated_at)::text AS max_card_updated_at
  FROM user_signal_card c
  JOIN user_signal_projection p
    ON p.user_signal_projection_id = c.user_signal_projection_id
   AND p.user_projection_run_id = c.user_projection_run_id
   AND p.user_id = c.user_id
  JOIN user_projection_run r
    ON r.user_projection_run_id = p.user_projection_run_id
   AND r.status IN ('passed', 'ready')
  WHERE p.user_id = ANY(%(signal_source_user_ids)s::bigint[])
    AND p.for_trade_date = pg_catalog.to_date(%(trade_date)s, 'YYYYMMDD')
    AND p.projection_status = 'visible'
    AND p.asset_kind IN ('stock', 'index', 'board')
    AND p.action_state IN ('eligible', 'executed')
), monitor_source AS (
  SELECT count(*)::bigint AS row_count,
         max(monitor_id)::text AS max_id,
         max(updated_at)::text AS max_updated_at,
         max(valid_source_run_id)::text AS max_source_run_id
  FROM user_monitor_stock
  WHERE status = 'active'
    AND valid_for_trade_date::text = %(trade_date)s
), realtime_source AS (
  SELECT count(*)::bigint AS row_count,
         max(realtime_scope_id)::text AS max_id,
         max(updated_at)::text AS max_updated_at
  FROM user_realtime_monitor_scope
  WHERE asset_kind = 'stock'
    AND status = 'active'
), position_source AS (
  SELECT count(*)::bigint AS row_count,
         max(p.virtual_position_id)::text AS max_id,
         max(GREATEST(p.updated_at, a.updated_at))::text AS max_updated_at
  FROM n6_virtual_account a
  JOIN n6_virtual_position p
    ON p.virtual_account_id = a.virtual_account_id
   AND p.principal_id = a.principal_id
   AND p.principal_type = a.principal_type
  WHERE a.virtual_account_status = 'active'
    AND p.asset_kind = 'stock'
    AND p.position_status = 'open_virtual'
    AND p.quantity > 0
), index_membership_source AS (
  SELECT count(*)::bigint AS row_count,
         max(trade_date)::text AS selected_membership_trade_date,
         max(created_at)::text AS max_created_at,
         max(source_batch_id)::text AS max_source_batch_id,
         max(source_version)::text AS max_source_version
  FROM v_n6_index_membership_fact membership
  WHERE membership.trade_date <= %(membership_asof_upper_bound)s
), board_membership_source AS (
  SELECT count(*)::bigint AS row_count,
         max(trade_date)::text AS selected_membership_trade_date,
         max(created_at)::text AS max_created_at,
         max(source_batch_id)::text AS max_source_batch_id,
         max(source_version)::text AS max_source_version
  FROM v_n6_board_membership_fact membership
  WHERE membership.trade_date <= %(membership_asof_upper_bound)s
    AND membership.board_type IN (
      'tdx_industry', 'tdx_concept', 'tdx_region'
    )
)
SELECT pg_catalog.jsonb_build_object(
         'projection', pg_catalog.to_jsonb(projection_source),
         'signal_card', pg_catalog.to_jsonb(card_source),
         'monitor_stock', pg_catalog.to_jsonb(monitor_source),
         'realtime_stock', pg_catalog.to_jsonb(realtime_source),
         'virtual_position', pg_catalog.to_jsonb(position_source),
         'index_membership', pg_catalog.to_jsonb(index_membership_source),
         'board_membership', pg_catalog.to_jsonb(board_membership_source)
       ) AS source_watermarks
FROM projection_source,
     card_source,
     monitor_source,
     realtime_source,
     position_source,
     index_membership_source,
     board_membership_source
"""


AUTO_EVALUATION_SCOPES_SQL = """
WITH ranked_revision AS (
  SELECT revision.*,
         pg_catalog.row_number() OVER (
           PARTITION BY revision.principal_id,
                        revision.principal_type,
                        revision.user_id
           ORDER BY
             CASE revision.selection_status WHEN 'pending' THEN 0 ELSE 1 END,
             revision.revision_no DESC
         ) AS revision_rank
  FROM n6_user_strategy_selection_revision revision
  JOIN n6_principal principal
    ON principal.principal_id = revision.principal_id
   AND principal.principal_type = revision.principal_type
   AND principal.owner_user_id = revision.user_id
   AND principal.principal_status = 'active'
  JOIN user_account account
    ON account.user_id = revision.user_id
   AND account.status = 'active'
  WHERE revision.selection_status IN ('pending', 'active')
    AND revision.effective_trade_date <= pg_catalog.to_date(
          %(trade_date)s, 'YYYYMMDD'
        )
)
SELECT revision.selection_revision_id,
       revision.principal_id,
       revision.user_id,
       revision.selection_status,
       revision.replay_status
FROM ranked_revision revision
WHERE revision.revision_rank = 1
  AND (
    revision.selection_status = 'active'
    OR (
      revision.selection_status = 'pending'
      AND revision.replay_status IN ('pending', 'running', 'failed')
    )
  )
ORDER BY CASE revision.selection_status WHEN 'pending' THEN 0 ELSE 1 END,
         revision.selection_revision_id,
         revision.principal_id,
         revision.user_id
"""


def n6_trade_date_authority(
    rows: Sequence[Mapping[str, Any]],
) -> N6TradeDateAuthority:
    try:
        batches = tuple(
            N6DisplayBatchAuthority(
                asset_kind=str(row.get("asset_kind") or ""),
                source_trade_date=str(row.get("source_trade_date") or ""),
                for_trade_date=str(row.get("for_trade_date") or ""),
                source_run_id=str(row.get("source_run_id") or ""),
                row_count=int(row.get("row_count") or 0),
            )
            for row in rows
        )
        trade_dates = {item.for_trade_date for item in batches}
        if len(trade_dates) != 1:
            raise ValueError("n6_trade_date_consensus_missing")
        return N6TradeDateAuthority(
            trade_date=next(iter(trade_dates)),
            batches=batches,
        )
    except (TypeError, ValueError) as error:
        raise StrategyCenterWorkerBlocked(
            "n6_trade_date_authority_invalid"
        ) from error


class PostgresStrategyCenterEvaluatorRepository:
    def __init__(
        self,
        dsn: str,
        *,
        signal_source_user_id: int | None = None,
    ) -> None:
        if signal_source_user_id is not None and (
            isinstance(signal_source_user_id, bool)
            or not isinstance(signal_source_user_id, int)
            or signal_source_user_id <= 0
        ):
            raise ValueError("invalid_signal_source_user_id")
        self.dsn = dsn
        self.signal_source_user_id = signal_source_user_id
        self._web_repository = PostgresN6UserRepository(dsn)

    @staticmethod
    def _load_n6_trade_date_authority(
        cur: Any,
    ) -> N6TradeDateAuthority:
        cur.execute(N6_TRADE_DATE_AUTHORITY_SQL)
        return n6_trade_date_authority(
            tuple(dict(row) for row in cur.fetchall())
        )

    def _load_source_watermarks(
        self,
        cur: Any,
        *,
        authority: N6TradeDateAuthority,
        signal_source_user_ids: Sequence[int] | None = None,
    ) -> dict[str, Any]:
        normalized_user_ids = tuple(
            sorted(
                {
                    int(value)
                    for value in (
                        signal_source_user_ids
                        if signal_source_user_ids is not None
                        else (self.signal_source_user_id,)
                    )
                    if value is not None
                }
            )
        )
        if not normalized_user_ids or any(
            value <= 0 for value in normalized_user_ids
        ):
            raise StrategyCenterWorkerBlocked(
                "signal_source_user_authority_missing"
            )
        cur.execute(
            AUTO_SOURCE_WATERMARKS_SQL,
            {
                "trade_date": authority.trade_date,
                "signal_source_user_ids": list(normalized_user_ids),
                "membership_asof_upper_bound": (
                    authority.membership_asof_upper_bound
                ),
            },
        )
        raw_watermarks = (cur.fetchone() or {}).get("source_watermarks")
        if isinstance(raw_watermarks, str):
            try:
                raw_watermarks = json.loads(raw_watermarks)
            except json.JSONDecodeError as exc:
                raise StrategyCenterWorkerBlocked(
                    "auto_source_watermarks_invalid"
                ) from exc
        if not isinstance(raw_watermarks, Mapping):
            raise StrategyCenterWorkerBlocked(
                "auto_source_watermarks_invalid"
            )
        return {
            "signal_source_user_ids": normalized_user_ids,
            **dict(raw_watermarks),
        }

    def load_auto_evaluation_state(self) -> AutoEvaluationState:
        if self.signal_source_user_id is None:
            raise StrategyCenterWorkerBlocked(
                "auto_signal_source_user_authority_missing"
            )
        try:
            with psycopg.connect(
                self.dsn,
                row_factory=dict_row,
                connect_timeout=10,
                autocommit=False,
                options=READ_ONLY_CONNECTION_OPTIONS,
            ) as conn:
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                    )
                    authority = self._load_n6_trade_date_authority(cur)
                    trade_date = authority.trade_date
                    source_watermarks = self._load_source_watermarks(
                        cur, authority=authority
                    )
                    cur.execute(
                        AUTO_EVALUATION_SCOPES_SQL,
                        {"trade_date": trade_date},
                    )
                    scope_rows = [dict(row) for row in cur.fetchall()]
        except psycopg.Error as error:
            _raise_database_timeout(error)
            raise
        pending_scopes = tuple(
            StrategyEvaluatorScope(
                principal_id=int(row["principal_id"]),
                user_id=int(row["user_id"]),
                selection_revision_id=int(row["selection_revision_id"]),
            )
            for row in scope_rows
            if str(row.get("selection_status") or "") == "pending"
        )
        active_scopes = tuple(
            StrategyEvaluatorScope(
                principal_id=int(row["principal_id"]),
                user_id=int(row["user_id"]),
                selection_revision_id=int(row["selection_revision_id"]),
            )
            for row in scope_rows
            if str(row.get("selection_status") or "") == "active"
        )
        replay_pending_active_scopes = tuple(
            StrategyEvaluatorScope(
                principal_id=int(row["principal_id"]),
                user_id=int(row["user_id"]),
                selection_revision_id=int(row["selection_revision_id"]),
            )
            for row in scope_rows
            if (
                str(row.get("selection_status") or "") == "active"
                and str(row.get("replay_status") or "") != "passed"
            )
        )
        pending_revision_ids = tuple(
            scope.selection_revision_id for scope in pending_scopes
        )
        if (
            tuple(sorted(set(pending_revision_ids))) != pending_revision_ids
            or len(set(pending_scopes + active_scopes))
            != len(pending_scopes) + len(active_scopes)
            or not set(replay_pending_active_scopes).issubset(
                set(active_scopes)
            )
            or any(
                str(row.get("selection_status") or "")
                not in {"pending", "active"}
                for row in scope_rows
            )
        ):
            raise StrategyCenterWorkerBlocked(
                "auto_evaluation_scope_authority_invalid"
            )
        return AutoEvaluationState(
            trade_date=trade_date,
            pending_revision_ids=pending_revision_ids,
            source_watermarks=source_watermarks,
            source_fingerprint=_hash(
                {
                    "trade_date": trade_date,
                    "trade_date_authority": asdict(authority),
                    "source_watermarks": source_watermarks,
                }
            ),
            pending_scopes=pending_scopes,
            active_scopes=active_scopes,
            replay_pending_active_scopes=replay_pending_active_scopes,
            trade_date_authority=authority,
        )

    def mark_pending_replay_status(
        self, revision_ids: Sequence[int], status: str
    ) -> tuple[int, ...]:
        normalized_ids = _selection_revision_ids(revision_ids)
        assert normalized_ids is not None
        if status not in {"pending", "running", "failed"}:
            raise ValueError("invalid_pending_replay_status")
        if not normalized_ids:
            return ()
        try:
            with psycopg.connect(
                self.dsn,
                row_factory=dict_row,
                connect_timeout=10,
                autocommit=False,
                options=WRITE_CONNECTION_OPTIONS,
            ) as conn:
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE n6_user_strategy_selection_revision
                        SET replay_status = %(status)s
                        WHERE selection_revision_id = ANY(
                                %(selection_revision_ids)s::bigint[]
                              )
                          AND selection_status = 'pending'
                          AND (
                            (
                              %(status)s = 'running'
                              AND replay_status IN ('pending', 'running', 'failed')
                            )
                            OR (
                              %(status)s = 'failed'
                              AND replay_status IN ('pending', 'running', 'failed')
                            )
                            OR (
                              %(status)s = 'pending'
                              AND replay_status IN ('running', 'failed')
                            )
                          )
                        RETURNING selection_revision_id
                        """,
                        {
                            "selection_revision_ids": list(normalized_ids),
                            "status": status,
                        },
                    )
                    updated_ids = tuple(
                        sorted(
                            int(row["selection_revision_id"])
                            for row in cur.fetchall()
                        )
                    )
                    if updated_ids != normalized_ids:
                        raise StrategyCenterWorkerBlocked(
                            "pending_replay_status_cas_failed"
                        )
        except psycopg.Error as error:
            _raise_database_timeout(error)
            raise
        return updated_ids

    def load_snapshot(
        self,
        trade_date: str,
        *,
        scope: StrategyEvaluatorScope | None = None,
        selection_revision_ids: Sequence[int] | None = None,
        evaluation_time: str | None = None,
    ) -> WorkerSnapshot:
        normalized_ids = _selection_revision_ids(selection_revision_ids)
        if scope is not None and normalized_ids is not None:
            raise ValueError("strategy_evaluator_target_conflict")
        try:
            with psycopg.connect(
                self.dsn,
                row_factory=dict_row,
                connect_timeout=10,
                autocommit=False,
                options=READ_ONLY_CONNECTION_OPTIONS,
            ) as conn:
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(
                        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                    )
                    return self._load_snapshot(
                        cur,
                        trade_date,
                        scope=scope,
                        selection_revision_ids=normalized_ids,
                        evaluation_time=evaluation_time,
                    )
        except psycopg.Error as error:
            _raise_database_timeout(error)
            raise

    def _load_snapshot(
        self,
        cur: Any,
        trade_date: str,
        *,
        scope: StrategyEvaluatorScope | None = None,
        selection_revision_ids: tuple[int, ...] | None = None,
        evaluation_time: str | None = None,
    ) -> WorkerSnapshot:
        if scope is not None and selection_revision_ids is not None:
            raise ValueError("strategy_evaluator_target_conflict")
        authority = self._load_n6_trade_date_authority(cur)
        if trade_date != authority.trade_date:
            raise StrategyCenterWorkerBlocked(
                "n6_trade_date_authority_mismatch"
            )
        cur.execute(
            """
            SELECT pg_catalog.transaction_timestamp() AS evaluation_time
            """
        )
        trade_date_authority = cur.fetchone() or {}
        evaluation_time = _validated_evaluation_time(
            evaluation_time
            if evaluation_time is not None
            else trade_date_authority.get("evaluation_time"),
            trade_date,
        )

        work_item_params = self._scope_params(
            trade_date,
            scope,
            selection_revision_ids,
        )
        work_item_params.setdefault("selection_revision_ids", None)
        cur.execute(WORK_ITEMS_SQL, work_item_params)
        work_items = [
            self._work_item(dict(row), trade_date=trade_date, scope=scope)
            for row in cur.fetchall()
        ]
        if scope is not None and len(work_items) != 1:
            raise StrategyCenterWorkerBlocked(
                "bounded_scope_selection_authority_invalid"
            )
        coverage_sql = """
            SELECT count(*)::int AS count
            FROM n6_principal principal
            JOIN user_account account
              ON account.user_id = principal.owner_user_id
             AND account.status = 'active'
            WHERE principal.principal_status = 'active'
              AND principal.principal_type IN ('admin', 'human_user')
        """
        if scope is not None:
            coverage_sql += """
              AND principal.principal_id = %(principal_id)s
              AND principal.owner_user_id = %(user_id)s
            """
            cur.execute(coverage_sql, work_item_params)
        elif selection_revision_ids is None:
            cur.execute(coverage_sql)
        if selection_revision_ids is not None:
            actual_revision_ids = tuple(
                sorted(item.selection_revision_id for item in work_items)
            )
            if actual_revision_ids != selection_revision_ids:
                raise StrategyCenterWorkerBlocked(
                    "strategy_selection_authority_incomplete"
                )
        else:
            expected = int((cur.fetchone() or {}).get("count") or 0)
            if scope is not None and expected != 1:
                raise StrategyCenterWorkerBlocked(
                    "bounded_scope_principal_authority_invalid"
                )
            if expected != len(work_items):
                raise StrategyCenterWorkerBlocked(
                    "strategy_selection_authority_incomplete"
                )

        source_watermarks = self._load_source_watermarks(
            cur,
            authority=authority,
            signal_source_user_ids=tuple(
                self._signal_source_user_id_for(item)
                for item in work_items
            ),
        )
        inputs = tuple(
            self._load_evaluation_input(
                cur, trade_date, item, evaluator_scope=scope
            )
            for item in work_items
        )
        _validate_bounded_inputs(scope, inputs, selection_revision_ids)
        return WorkerSnapshot(
            trade_date=trade_date,
            evaluation_time=evaluation_time,
            inputs=inputs,
            snapshot_hash=snapshot_hash(
                trade_date,
                inputs,
                evaluation_time=evaluation_time,
                scope=scope,
                selection_revision_ids=selection_revision_ids,
                trade_date_authority=authority,
                source_watermarks=source_watermarks,
            ),
            evaluator_scope=scope,
            selection_revision_ids=selection_revision_ids,
            selection_cas_hash=selection_cas_hash(inputs),
            trade_date_authority=authority,
            source_watermarks=source_watermarks,
        )

    @staticmethod
    def _scope_params(
        trade_date: str,
        scope: StrategyEvaluatorScope | None,
        selection_revision_ids: tuple[int, ...] | None = None,
    ) -> dict[str, Any]:
        scope_mode = (
            "single_user_revision"
            if scope is not None
            else (
                "selection_revision_set"
                if selection_revision_ids is not None
                else "all_users"
            )
        )
        params = {
            "trade_date": trade_date,
            "scope_mode": scope_mode,
            "principal_id": scope.principal_id if scope else None,
            "user_id": scope.user_id if scope else None,
            "selection_revision_id": (
                scope.selection_revision_id if scope else None
            ),
        }
        if selection_revision_ids is not None:
            params["selection_revision_ids"] = list(selection_revision_ids)
        return params

    @staticmethod
    def _work_item(
        row: Mapping[str, Any],
        *,
        trade_date: str,
        scope: StrategyEvaluatorScope | None,
    ) -> SelectionWorkItem:
        packages = tuple(
            str(value) for value in (row.get("selected_package_keys") or [])
        )
        selection_status = str(row.get("selection_status") or "")
        if selection_status not in ("active", "pending"):
            raise StrategyCenterWorkerBlocked("selection_revision_status_invalid")
        effective_trade_date = str(row.get("effective_trade_date") or "")
        if (
            not re.fullmatch(r"[0-9]{8}", effective_trade_date)
            or effective_trade_date > trade_date
        ):
            raise StrategyCenterWorkerBlocked(
                "selection_effective_trade_date_invalid"
            )
        result = SelectionWorkItem(
            selection_revision_id=int(row["selection_revision_id"]),
            principal_id=int(row["principal_id"]),
            principal_type=str(row["principal_type"]),
            user_id=int(row["user_id"]),
            revision_no=int(row["revision_no"]),
            selection_status=selection_status,
            replay_status=str(row["replay_status"]),
            previous_revision_id=(
                int(row["previous_revision_id"])
                if row.get("previous_revision_id") is not None
                else None
            ),
            active_revision_id=(
                int(row["active_revision_id"])
                if row.get("active_revision_id") is not None
                else None
            ),
            selected_package_keys=packages,
            selected_package_versions=tuple(
                str(value)
                for value in (row.get("selected_package_versions") or ())
            ),
            selected_package_statuses=tuple(
                str(value)
                for value in (row.get("selected_package_statuses") or ())
            ),
            effective_trade_date=effective_trade_date,
            selection_immutable_authority=str(
                row.get("selection_immutable_authority") or ""
            ),
            selected_package_authority=tuple(
                str(value)
                for value in (row.get("selected_package_authority") or ())
            ),
            selected_package_rule_authority=tuple(
                _canonical_json(value)
                for value in (
                    row.get("selected_package_rule_authority") or ()
                )
            ),
            selection_lifecycle_authority=str(
                row.get("selection_lifecycle_authority") or ""
            ),
            active_revision_authority=str(
                row.get("active_revision_authority") or ""
            ),
        )
        if scope is not None and (
            result.principal_id != scope.principal_id
            or result.user_id != scope.user_id
            or result.selection_revision_id != scope.selection_revision_id
        ):
            raise StrategyCenterWorkerBlocked("bounded_scope_work_item_mismatch")
        _validate_selected_package_authority(result)
        return result

    def _stock_effective_monitor_scope_cte(self) -> str:
        """Build the stock /signals scope for the evaluator trade date."""
        web = self._web_repository
        scope_selects = [
            web._app_v1_effective_monitor_scope_select(
                asset_kind="stock",
                table_name="user_monitor_stock",
                view_name="v_n6_stock_condition_display_basis",
            )
        ]
        if web._app_v2_relation_exists("user_realtime_monitor_scope"):
            scope_selects.append(web._app_v1_realtime_scope_select())
        capabilities = web._app_v1_signal_schema_capabilities()
        if {"n6_virtual_account", "n6_virtual_position"}.issubset(
            capabilities
        ):
            scope_selects.append(web._app_v1_holding_scope_select())
        scope_body = "\nUNION ALL\n".join(scope_selects)
        result = f"""
        current_stock_approved_batch AS MATERIALIZED (
          SELECT min(approved.source_trade_date::text) AS source_trade_date,
                 min(approved.for_trade_date::text) AS for_trade_date,
                 min(approved.run_id::text) AS source_run_id
          FROM v_n6_stock_condition_display_basis approved
          WHERE approved.for_trade_date::text = %(trade_date)s
          HAVING count(*) > 0
             AND count(approved.source_trade_date) = count(*)
             AND count(approved.for_trade_date) = count(*)
             AND count(approved.run_id) = count(*)
             AND count(DISTINCT (
               approved.source_trade_date::text,
               approved.for_trade_date::text,
               approved.run_id::text
             )) = 1
        ),
        {web._app_v1_principal_monitor_cte(
            asset_kind="stock",
            table_name="user_monitor_stock",
            include_expired=False,
        )},
        effective_monitor_scope AS (
          {scope_body}
        )
        """
        if getattr(self, "signal_source_user_id", None) is not None:
            return result.replace(
                "%(user_id)s",
                "%(scope_user_id)s",
            )
        return result

    def _signal_source_user_id_for(
        self, selection: SelectionWorkItem
    ) -> int:
        return (
            getattr(self, "signal_source_user_id", None)
            or selection.user_id
        )

    def _canonical_stock_projection_ids(
        self,
        cur: Any,
        *,
        selection: SelectionWorkItem,
        trade_date: str,
    ) -> list[int]:
        scope_cte = self._stock_effective_monitor_scope_cte()
        scope_join = self._web_repository._app_v1_effective_monitor_scope_join()
        cur.execute(
            f"""
            WITH {scope_cte}
            SELECT p.user_signal_projection_id
            FROM user_signal_projection p
            JOIN user_projection_run r
              ON r.user_projection_run_id = p.user_projection_run_id
             AND r.status IN ('passed', 'ready')
            {scope_join}
            WHERE p.user_id = %(user_id)s
              AND p.projection_status = 'visible'
              AND p.asset_kind = 'stock'
              AND p.action_state IN ('eligible', 'executed')
              AND p.for_trade_date = pg_catalog.to_date(
                    %(trade_date)s, 'YYYYMMDD'
                  )
            ORDER BY p.user_signal_projection_id
            """,
            {
                "principal_id": selection.principal_id,
                "principal_type": selection.principal_type,
                "user_id": self._signal_source_user_id_for(selection),
                "scope_user_id": selection.user_id,
                "trade_date": trade_date,
            },
        )
        projection_ids = [
            int(row["user_signal_projection_id"]) for row in cur.fetchall()
        ]
        if (
            any(value <= 0 for value in projection_ids)
            or len(projection_ids) != len(set(projection_ids))
        ):
            raise StrategyCenterWorkerBlocked(
                "canonical_signal_projection_id_authority_invalid"
            )
        return projection_ids

    def _load_evaluation_input(
        self,
        cur: Any,
        trade_date: str,
        selection: SelectionWorkItem,
        *,
        evaluator_scope: StrategyEvaluatorScope | None = None,
    ) -> EvaluationInput:
        scope_dicts = N6StrategyCenterReadRepository.fetch_scope_rows(
            cur,
            principal_id=selection.principal_id,
            principal_type=selection.principal_type,
            user_id=selection.user_id,
            trade_date=trade_date,
        )
        scope_rows = tuple(ScopeRow(**row) for row in scope_dicts)
        stock_projection_ids = self._canonical_stock_projection_ids(
            cur,
            selection=selection,
            trade_date=trade_date,
        )
        parent_projection_ids = (
            N6StrategyCenterReadRepository.fetch_parent_executed_signal_ids(
                cur,
                user_id=self._signal_source_user_id_for(selection),
                trade_date=trade_date,
            )
        )
        authority_projection_ids = sorted(
            set(stock_projection_ids) | set(parent_projection_ids)
        )
        authority_rows = N6StrategyCenterReadRepository.fetch_signal_authority_rows(
            cur,
            user_id=self._signal_source_user_id_for(selection),
            trade_date=trade_date,
            projection_ids=authority_projection_ids,
        )
        returned_authority_ids = [
            int(row["user_signal_projection_id"]) for row in authority_rows
        ]
        if returned_authority_ids != authority_projection_ids:
            raise StrategyCenterWorkerBlocked(
                "signal_authority_projection_set_changed"
            )
        canonical = self._canonical_signal_items(
            cur,
            selection=selection,
            trade_date=trade_date,
            projection_ids=stock_projection_ids,
        )
        stock_projection_id_set = set(stock_projection_ids)
        parent_projection_id_set = set(parent_projection_ids)
        stock_signals_list: list[StockSignalEvent] = []
        for row in authority_rows:
            projection_id = int(row["user_signal_projection_id"])
            if (
                row.get("asset_kind") != "stock"
                or not row.get("action_episode_key")
                or projection_id not in stock_projection_id_set
                or projection_id not in canonical
            ):
                continue
            signal = canonical[projection_id]
            if selection.strategy_version == STRATEGY_VERSION_V2:
                event_time, _direction = _v2_standard_event_authority(
                    row, canonical_signal=signal
                )
            else:
                event_time = str(
                    row.get("projection_event_time")
                    or row.get("source_event_time")
                    or ""
                )
            stock_signals_list.append(
                StockSignalEvent(
                    user_signal_projection_id=projection_id,
                    trade_date=str(row.get("trade_date") or ""),
                    identity_key=str(row.get("identity_key") or ""),
                    code=str(row.get("code") or ""),
                    name=str(row.get("name") or ""),
                    event_id=str(row.get("event_id") or ""),
                    event_type=str(row.get("event_type") or ""),
                    action_state=str(row.get("action_state") or ""),
                    event_time=event_time,
                    action_episode_key=str(
                        row.get("action_episode_key") or ""
                    ),
                    source_run_id=str(row.get("source_run_id") or ""),
                    event_schema_version=str(
                        row.get("event_schema_version") or ""
                    ),
                    signal=signal,
                )
            )
        stock_signals = tuple(stock_signals_list)
        parent_authority_rows = tuple(
            row
            for row in authority_rows
            if int(row["user_signal_projection_id"])
            in parent_projection_id_set
            and row.get("asset_kind") in ("index", "board")
            and row.get("action_state") == "executed"
        )
        parent_events_list: list[ParentExecutedEvent] = []
        for row in parent_authority_rows:
            if selection.strategy_version == STRATEGY_VERSION_V2:
                event_time, direction = _v2_standard_event_authority(row)
            else:
                event_time = str(
                    row.get("projection_event_time")
                    or row.get("source_event_time")
                    or ""
                )
                direction = str(
                    row.get("projection_direction")
                    or row.get("source_direction")
                    or ""
                )
            parent_events_list.append(
                ParentExecutedEvent(
                    trade_date=str(row.get("trade_date") or ""),
                    asset_kind=str(row.get("asset_kind") or ""),
                    identity_key=str(row.get("identity_key") or ""),
                    code=str(row.get("code") or ""),
                    name=str(row.get("name") or ""),
                    event_id=str(row.get("event_id") or ""),
                    event_type=str(row.get("event_type") or ""),
                    action_state=str(row.get("action_state") or ""),
                    event_time=event_time,
                    source_run_id=str(row.get("source_run_id") or ""),
                    event_schema_version=str(
                        row.get("event_schema_version") or ""
                    ),
                    direction=direction,
                    user_signal_projection_id=int(
                        row["user_signal_projection_id"]
                    ),
                )
            )
        parent_events = tuple(parent_events_list)
        membership_authorities = self._membership_authorities(
            cur, trade_date=trade_date, stock_signals=stock_signals
        )
        rows_by_kind: dict[str, list[dict[str, Any]]] = {
            "index": [],
            "board": [],
        }
        fetch_by_kind = {
            "index": N6StrategyCenterReadRepository.fetch_index_membership_rows,
            "board": N6StrategyCenterReadRepository.fetch_board_membership_rows,
        }
        for membership_kind in ("index", "board"):
            selected_dates = sorted(
                {
                    authority.selected_membership_trade_date
                    for authority in membership_authorities
                    if authority.membership_kind == membership_kind
                    and authority.quality_status == "passed"
                }
            )
            for selected_date in selected_dates:
                selected_stock_keys = sorted(
                    {
                        authority.stock_identity_key
                        for authority in membership_authorities
                        if authority.membership_kind == membership_kind
                        and authority.selected_membership_trade_date == selected_date
                        and authority.quality_status == "passed"
                    }
                )
                rows_by_kind[membership_kind].extend(
                    fetch_by_kind[membership_kind](
                        cur,
                        trade_date=selected_date,
                        stock_identity_keys=selected_stock_keys,
                    )
                )
        frozen_matches: tuple[StrategyMatch, ...] = ()
        frozen_observations: tuple[StrategyObservation, ...] = ()
        if selection.strategy_version == STRATEGY_VERSION_V2:
            frozen_matches, frozen_observations = (
                self._load_frozen_v2_surfaces(
                    cur,
                    selection=selection,
                    trade_date=trade_date,
                )
            )
        return EvaluationInput(
            selection=selection,
            scope_rows=scope_rows,
            stock_signals=stock_signals,
            index_memberships=tuple(
                MembershipRow(**row) for row in rows_by_kind["index"]
            ),
            board_memberships=tuple(
                MembershipRow(**row) for row in rows_by_kind["board"]
            ),
            parent_executed_events=parent_events,
            membership_authorities=membership_authorities,
            frozen_matches=frozen_matches,
            frozen_observations=frozen_observations,
            evaluator_scope=evaluator_scope,
        )

    @staticmethod
    def _frozen_candidate_from_row(
        row: Mapping[str, Any],
        *,
        surface_kind: str,
    ) -> StrategyMatch:
        confluence = row.get("confluence_json")
        if not isinstance(confluence, Mapping):
            raise StrategyCenterWorkerBlocked(
                "frozen_coherence_episode_authority_invalid"
            )
        requested_source_trade_date = str(
            confluence.get("requested_source_trade_date") or ""
        )
        membership_source_trade_date = str(
            confluence.get("membership_source_trade_date")
            or row.get("membership_source_trade_date")
            or ""
        )
        membership_provenance_value = confluence.get(
            "membership_provenance"
        )
        if (
            surface_kind not in {"qualified_match", "observation"}
            or not re.fullmatch(r"[0-9]{8}", requested_source_trade_date)
            or not re.fullmatch(r"[0-9]{8}", membership_source_trade_date)
            or not isinstance(membership_provenance_value, list)
            or not all(
                isinstance(item, Mapping)
                for item in membership_provenance_value
            )
        ):
            raise StrategyCenterWorkerBlocked(
                "frozen_coherence_episode_authority_invalid"
            )
        package_field = (
            "matched_packages"
            if surface_kind == "qualified_match"
            else "observed_packages"
        )
        board_field = (
            "matched_boards_json"
            if surface_kind == "qualified_match"
            else "observed_boards_json"
        )
        hash_field = (
            "projection_hash"
            if surface_kind == "qualified_match"
            else "observation_hash"
        )
        provisional = StrategyMatch(
            trade_date=str(row.get("trade_date") or ""),
            stock_identity_key=str(row.get("stock_identity_key") or ""),
            action_episode_key=str(row.get("action_episode_key") or ""),
            coherence_episode_key=str(
                row.get("coherence_episode_key") or ""
            ),
            action_state=str(row.get("action_state") or ""),
            source_signal_projection_id=int(
                row.get("source_signal_projection_id") or 0
            ),
            source_event_ids=tuple(row.get("source_event_ids") or ()),
            matched_packages=tuple(row.get(package_field) or ()),
            scope_sources=tuple(row.get("scope_sources") or ()),
            indices=tuple(
                dict(item) for item in (row.get("indices_json") or ())
            ),
            matched_boards=tuple(
                dict(item) for item in (row.get(board_field) or ())
            ),
            signal=dict(row.get("signal_json") or {}),
            confluence=dict(confluence),
            state_timeline=tuple(
                dict(item)
                for item in (row.get("state_timeline_json") or ())
            ),
            mapping_quality=str(row.get("mapping_quality") or ""),
            requested_source_trade_date=requested_source_trade_date,
            membership_source_trade_date=membership_source_trade_date,
            membership_provenance=tuple(
                dict(item) for item in membership_provenance_value
            ),
            evaluator_policy_hash=str(
                row.get("evaluator_policy_hash") or ""
            ),
            projection_hash="",
        )
        payload = provisional.as_payload()
        payload.pop("surface_kind", None)
        payload.pop("projection_hash", None)
        calculated_hash = _hash(payload)
        if surface_kind == "qualified_match":
            if str(row.get(hash_field) or "") != calculated_hash:
                raise StrategyCenterWorkerBlocked(
                    "frozen_coherence_episode_hash_invalid"
                )
            return StrategyMatch(
                **{
                    **asdict(provisional),
                    "projection_hash": calculated_hash,
                }
            )
        observation_kind = str(row.get("observation_kind") or "")
        calculated_observation = StrategyObservation.from_candidate(
            provisional,
            observation_reason=observation_kind,
        )
        if (
            str(row.get(hash_field) or "")
            != calculated_observation.observation_hash
        ):
            raise StrategyCenterWorkerBlocked(
                "frozen_coherence_episode_hash_invalid"
            )
        return provisional

    def _load_frozen_v2_surfaces(
        self,
        cur: Any,
        *,
        selection: SelectionWorkItem,
        trade_date: str,
    ) -> tuple[tuple[StrategyMatch, ...], tuple[StrategyObservation, ...]]:
        params = self._selection_params(selection, trade_date)
        cur.execute(
            """
            SELECT pg_catalog.to_char(trade_date, 'YYYYMMDD') AS trade_date,
                   stock_identity_key, action_episode_key,
                   coherence_episode_key, action_state,
                   source_signal_projection_id, source_event_ids,
                   matched_packages, scope_sources, indices_json,
                   matched_boards_json, signal_json, state_timeline_json,
                   mapping_quality,
                   pg_catalog.to_char(
                     membership_source_trade_date, 'YYYYMMDD'
                   ) AS membership_source_trade_date,
                   confluence_json, evaluator_policy_hash, projection_hash
            FROM n6_strategy_match_projection
            WHERE selection_revision_id = %(selection_revision_id)s
              AND principal_id = %(principal_id)s
              AND principal_type = %(principal_type)s
              AND user_id = %(user_id)s
              AND trade_date = to_date(%(trade_date)s, 'YYYYMMDD')
              AND strategy_version = 'v2'
            ORDER BY stock_identity_key, action_episode_key,
                     coherence_episode_key
            """,
            params,
        )
        matches = tuple(
            self._frozen_candidate_from_row(
                dict(row), surface_kind="qualified_match"
            )
            for row in cur.fetchall()
        )
        cur.execute(
            """
            SELECT pg_catalog.to_char(trade_date, 'YYYYMMDD') AS trade_date,
                   stock_identity_key, action_episode_key,
                   coherence_episode_key, action_state,
                   source_signal_projection_id, source_event_ids,
                   observed_packages, scope_sources, indices_json,
                   observed_boards_json, signal_json, state_timeline_json,
                   mapping_quality,
                   pg_catalog.to_char(
                     membership_source_trade_date, 'YYYYMMDD'
                   ) AS membership_source_trade_date,
                   confluence_json, evaluator_policy_hash,
                   observation_hash, observation_kind
            FROM n6_strategy_observation_projection
            WHERE selection_revision_id = %(selection_revision_id)s
              AND principal_id = %(principal_id)s
              AND principal_type = %(principal_type)s
              AND user_id = %(user_id)s
              AND trade_date = to_date(%(trade_date)s, 'YYYYMMDD')
              AND strategy_version = 'v2'
            ORDER BY stock_identity_key, action_episode_key,
                     coherence_episode_key, observation_kind
            """,
            params,
        )
        observations: list[StrategyObservation] = []
        for row in cur.fetchall():
            row_value = dict(row)
            candidate = self._frozen_candidate_from_row(
                row_value, surface_kind="observation"
            )
            observations.append(
                StrategyObservation.from_candidate(
                    candidate,
                    observation_reason=str(
                        row_value.get("observation_kind") or ""
                    ),
                )
            )
        match_keys = {
            (
                match.stock_identity_key,
                match.action_episode_key,
                match.coherence_episode_key,
            )
            for match in matches
        }
        observation_keys = {
            (
                observation.stock_identity_key,
                observation.action_episode_key,
                observation.coherence_episode_key,
            )
            for observation in observations
        }
        if (
            match_keys & observation_keys
            or len(observation_keys) != len(observations)
        ):
            raise StrategyCenterWorkerBlocked(
                "frozen_coherence_surface_overlap"
            )
        return matches, tuple(observations)

    def _membership_authorities(
        self,
        cur: Any,
        *,
        trade_date: str,
        stock_signals: Sequence[StockSignalEvent],
    ) -> tuple[MembershipSnapshotAuthority, ...]:
        snapshot_cache: dict[tuple[str, str], dict[str, str]] = {}
        authorities: set[MembershipSnapshotAuthority] = set()
        for event in stock_signals:
            requested = source_trade_date_for_event(event)
            source_date_status = self._source_trade_date_status(requested, trade_date)
            for membership_kind in ("index", "board"):
                if source_date_status != "passed":
                    snapshot = {
                        "selected_membership_trade_date": "",
                        "source_version": "",
                        "source_batch_id": "",
                        "provenance_status": "unavailable",
                        "quality_status": source_date_status,
                    }
                else:
                    key = (membership_kind, str(requested))
                    snapshot = snapshot_cache.get(key)
                    if snapshot is None:
                        snapshot = self._membership_snapshot_authority(
                            cur,
                            membership_kind=membership_kind,
                            requested_source_trade_date=str(requested),
                        )
                        snapshot_cache[key] = snapshot
                authorities.add(
                    MembershipSnapshotAuthority(
                        stock_identity_key=event.identity_key,
                        action_episode_key=event.action_episode_key,
                        membership_kind=membership_kind,
                        requested_source_trade_date=str(requested or ""),
                        **snapshot,
                    )
                )
        return tuple(
            sorted(
                authorities,
                key=lambda item: (
                    item.stock_identity_key,
                    item.action_episode_key,
                    item.requested_source_trade_date,
                    item.membership_kind,
                ),
            )
        )

    @staticmethod
    def _source_trade_date_status(value: str | None, trade_date: str) -> str:
        if not value:
            return "source_trade_date_missing"
        try:
            parsed = datetime.strptime(value, "%Y%m%d")
        except ValueError:
            return "source_trade_date_invalid"
        if parsed.strftime("%Y%m%d") != value:
            return "source_trade_date_invalid"
        if value > trade_date:
            return "source_trade_date_future"
        return "passed"

    @staticmethod
    def _membership_snapshot_authority(
        cur: Any,
        *,
        membership_kind: str,
        requested_source_trade_date: str,
    ) -> dict[str, str]:
        relation = MEMBERSHIP_RELATION_BY_KIND[membership_kind]
        cur.execute(
            f"""
            WITH selected_snapshot AS (
              SELECT max(membership.trade_date) AS membership_trade_date
              FROM {relation} membership
              WHERE membership.trade_date <= %(requested_source_trade_date)s
            )
            SELECT selected.membership_trade_date::text
                     AS selected_membership_trade_date,
                   min(membership.source_version::text) AS source_version,
                   min(membership.source_batch_id::text) AS source_batch_id,
                   count(DISTINCT membership.source_version)::int
                     AS source_version_count,
                   count(DISTINCT membership.source_batch_id)::int
                     AS source_batch_id_count
            FROM selected_snapshot selected
            LEFT JOIN {relation} membership
              ON membership.trade_date = selected.membership_trade_date
            GROUP BY selected.membership_trade_date
            """,
            {"requested_source_trade_date": requested_source_trade_date},
        )
        row = dict(cur.fetchone() or {})
        selected_date = str(row.get("selected_membership_trade_date") or "")
        source_version = str(row.get("source_version") or "")
        source_batch_id = str(row.get("source_batch_id") or "")
        if not selected_date:
            return {
                "selected_membership_trade_date": "",
                "source_version": "",
                "source_batch_id": "",
                "provenance_status": "unavailable",
                "quality_status": "membership_snapshot_missing",
            }
        if (
            int(row.get("source_version_count") or 0) != 1
            or int(row.get("source_batch_id_count") or 0) != 1
            or not source_version
            or not source_batch_id
        ):
            return {
                "selected_membership_trade_date": selected_date,
                "source_version": source_version,
                "source_batch_id": source_batch_id,
                "provenance_status": "ambiguous",
                "quality_status": "membership_provenance_invalid",
            }
        return {
            "selected_membership_trade_date": selected_date,
            "source_version": source_version,
            "source_batch_id": source_batch_id,
            "provenance_status": "authoritative_as_of",
            "quality_status": "passed",
        }

    def _canonical_signal_items(
        self,
        cur: Any,
        *,
        selection: SelectionWorkItem,
        trade_date: str,
        projection_ids: list[int],
    ) -> dict[int, dict[str, Any]]:
        if not projection_ids:
            return {}
        scope_cte = self._stock_effective_monitor_scope_cte()
        select_list = self._web_repository._app_v1_signal_select_list()
        scope_join = self._web_repository._app_v1_effective_monitor_scope_join()
        cur.execute(
            f"""
            WITH {scope_cte}
            SELECT {select_list}
            FROM user_signal_projection p
            JOIN user_projection_run r
              ON r.user_projection_run_id = p.user_projection_run_id
             AND r.status IN ('passed', 'ready')
            LEFT JOIN user_signal_card c
              ON c.user_signal_projection_id = p.user_signal_projection_id
             AND c.user_projection_run_id = p.user_projection_run_id
             AND c.user_id = p.user_id
            {scope_join}
            WHERE p.user_id = %(user_id)s
              AND p.asset_kind = 'stock'
              AND p.for_trade_date = pg_catalog.to_date(
                    %(trade_date)s, 'YYYYMMDD'
                  )
              AND p.user_signal_projection_id = ANY(%(projection_ids)s)
            ORDER BY p.user_signal_projection_id
            """,
            {
                "principal_id": selection.principal_id,
                "principal_type": selection.principal_type,
                "user_id": self._signal_source_user_id_for(selection),
                "scope_user_id": selection.user_id,
                "trade_date": trade_date,
                "projection_ids": projection_ids,
            },
        )
        result: dict[int, dict[str, Any]] = {}
        returned_rows = [dict(row) for row in cur.fetchall()]
        for row in returned_rows:
            item = app_signal_item(dict(row))
            if not self._canonical_signal_dto_valid(item):
                raise StrategyCenterWorkerBlocked("canonical_signal_dto_incomplete")
            result[int(row["user_signal_projection_id"])] = item
        requested_ids = set(projection_ids)
        returned_ids = set(result)
        if (
            not returned_ids.issubset(requested_ids)
            or len(returned_rows) != len(result)
        ):
            raise StrategyCenterWorkerBlocked("canonical_signal_dto_incomplete")
        missing_ids = sorted(requested_ids - returned_ids)
        if missing_ids:
            self._assert_canonical_scope_omissions(
                cur,
                selection=selection,
                trade_date=trade_date,
                projection_ids=missing_ids,
                scope_cte=scope_cte,
            )
        return result

    @staticmethod
    def _canonical_signal_dto_valid(item: Mapping[str, Any]) -> bool:
        projection_id = str(item.get("user_signal_projection_id") or "").strip()
        required_text = (
            "identity_key",
            "display_code",
            "display_name",
            "event_type",
            "trade_date",
            "source_run_id",
            "projection_run_id",
        )
        return (
            projection_id.isdigit()
            and int(projection_id) > 0
            and item.get("asset_kind") in ("stock", "index", "board")
            and item.get("direction") in ("buy", "sell")
            and item.get("action_state") in ("eligible", "executed")
            and all(
                str(item.get(field) or "").strip() not in ("", "—")
                for field in required_text
            )
        )

    def _assert_canonical_scope_omissions(
        self,
        cur: Any,
        *,
        selection: SelectionWorkItem,
        trade_date: str,
        projection_ids: list[int],
        scope_cte: str,
    ) -> None:
        """Allow only signals excluded by the formal /signals scope join."""
        message_trade_date_expr = self._web_repository._app_v1_trade_date_expr()
        cur.execute(
            f"""
            WITH {scope_cte},
            missing_projection AS MATERIALIZED (
              SELECT p.*
              FROM user_signal_projection p
              WHERE p.user_id = %(user_id)s
                AND p.asset_kind = 'stock'
                AND p.for_trade_date = pg_catalog.to_date(
                      %(trade_date)s, 'YYYYMMDD'
                    )
                AND p.user_signal_projection_id = ANY(%(projection_ids)s)
            )
            SELECT p.user_signal_projection_id,
                   run.status IN ('passed', 'ready') AS projection_run_ready,
                   count(effective_monitor_scope.monitor_id) > 0
                     AS exact_scope_match
            FROM missing_projection p
            LEFT JOIN user_projection_run run
              ON run.user_projection_run_id = p.user_projection_run_id
            LEFT JOIN effective_monitor_scope
              ON effective_monitor_scope.asset_kind = p.asset_kind
             AND effective_monitor_scope.identity_key = p.identity_key
             AND effective_monitor_scope.direction = p.direction
             AND effective_monitor_scope.valid_for_trade_date =
                 ({message_trade_date_expr})
            GROUP BY p.user_signal_projection_id, run.status
            ORDER BY p.user_signal_projection_id
            """,
            {
                "principal_id": selection.principal_id,
                "principal_type": selection.principal_type,
                "user_id": self._signal_source_user_id_for(selection),
                "scope_user_id": selection.user_id,
                "trade_date": trade_date,
                "projection_ids": projection_ids,
            },
        )
        rows = [dict(row) for row in cur.fetchall()]
        if len(rows) != len(projection_ids) or any(
            not bool(row.get("projection_run_ready"))
            or bool(row.get("exact_scope_match"))
            for row in rows
        ):
            raise StrategyCenterWorkerBlocked("canonical_signal_dto_incomplete")

    def commit_plan(self, plan: WorkerPlan) -> Mapping[str, Any]:
        self._validate_plan_integrity(plan)
        try:
            with psycopg.connect(
                self.dsn,
                row_factory=dict_row,
                connect_timeout=10,
                autocommit=False,
                options=WRITE_CONNECTION_OPTIONS,
            ) as conn:
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                    cur.execute(ADVISORY_LOCK_SQL, (ADVISORY_LOCK_KEY,))
                    lock_row = cur.fetchone() or {}
                    if not bool(lock_row.get("acquired")):
                        raise StrategyCenterWorkerBlocked(
                            "strategy_worker_lock_not_acquired"
                        )
                    current = self._load_snapshot(
                        cur,
                        plan.trade_date,
                        scope=plan.evaluator_scope,
                        selection_revision_ids=plan.selection_revision_ids,
                        evaluation_time=plan.evaluation_time,
                    )
                    current_input_watermark = snapshot_hash(
                        current.trade_date,
                        current.inputs,
                        evaluation_time=plan.evaluation_time,
                        scope=current.evaluator_scope,
                        selection_revision_ids=current.selection_revision_ids,
                        trade_date_authority=current.trade_date_authority,
                        source_watermarks=current.source_watermarks,
                    )
                    if current_input_watermark != plan.input_watermark:
                        raise StrategyCenterWorkerBlocked(
                            "strategy_worker_snapshot_cas_mismatch"
                        )
                    if (
                        current.selection_cas_hash
                        != plan.selection_cas_watermark
                    ):
                        raise StrategyCenterWorkerBlocked(
                            "strategy_selection_lifecycle_cas_mismatch"
                        )
                    result = self._apply_plan(cur, plan)
            return result
        except psycopg.Error as error:
            _raise_database_timeout(error)
            raise

    def commit_frozen_replay(self, plan: WorkerPlan) -> Mapping[str, Any]:
        """Replay exactly one already-frozen plan without reloading inputs.

        This path is deliberately narrower than ``commit_plan``: it is only
        for the bounded canary's same-input idempotency proof.  It verifies
        the exact selection is still active, then applies the immutable plan;
        it never re-reads reviewed projections, cards, memberships, or other
        evaluator inputs that may legitimately advance while the canary runs.
        """
        self._validate_plan_integrity(plan)
        if plan.evaluator_scope is None or len(plan.work_plans) != 1:
            raise StrategyCenterWorkerBlocked(
                "strategy_frozen_replay_scope_required"
            )
        selection = plan.work_plans[0].selection
        self._assert_selection_scope(selection, plan.evaluator_scope)
        try:
            with psycopg.connect(
                self.dsn,
                row_factory=dict_row,
                connect_timeout=10,
                autocommit=False,
                options=WRITE_CONNECTION_OPTIONS,
            ) as conn:
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                    cur.execute(ADVISORY_LOCK_SQL, (ADVISORY_LOCK_KEY,))
                    lock_row = cur.fetchone() or {}
                    if not bool(lock_row.get("acquired")):
                        raise StrategyCenterWorkerBlocked(
                            "strategy_worker_lock_not_acquired"
                        )
                    cur.execute(
                        """
                        SELECT selection_status
                        FROM n6_user_strategy_selection_revision
                        WHERE selection_revision_id = %(selection_revision_id)s
                          AND principal_id = %(principal_id)s
                          AND principal_type = %(principal_type)s
                          AND user_id = %(user_id)s
                        FOR UPDATE
                        """,
                        self._selection_params(selection, plan.trade_date),
                    )
                    row = cur.fetchone()
                    if row is None or str(row["selection_status"]) != "active":
                        raise StrategyCenterWorkerBlocked(
                            "strategy_frozen_replay_selection_not_active"
                        )
                    return self._apply_plan(cur, plan)
        except psycopg.Error as error:
            _raise_database_timeout(error)
            raise

    @staticmethod
    def _validate_plan_integrity(plan: WorkerPlan) -> None:
        _validated_evaluation_time(plan.evaluation_time, plan.trade_date)
        if plan.input_watermark != plan.snapshot_hash:
            raise StrategyCenterWorkerBlocked("strategy_worker_plan_scope_invalid")
        if plan.selection_cas_watermark != _selection_cas_hash(
            tuple(item.selection for item in plan.work_plans)
        ):
            raise StrategyCenterWorkerBlocked(
                "strategy_worker_plan_scope_invalid"
            )
        if _hash(
            _plan_body(
                trade_date=plan.trade_date,
                evaluation_time=plan.evaluation_time,
                evaluator_run_id=plan.evaluator_run_id,
                snapshot_hash_value=plan.snapshot_hash,
                scope=plan.evaluator_scope,
                selection_revision_ids=plan.selection_revision_ids,
                work_plans=plan.work_plans,
                trade_date_authority=plan.trade_date_authority,
                source_watermarks=plan.source_watermarks,
            )
        ) != plan.plan_hash:
            raise StrategyCenterWorkerBlocked("strategy_worker_plan_scope_invalid")
        for work_plan in plan.work_plans:
            _validate_surface_partition(work_plan)
        if (
            plan.evaluator_scope is not None
            and plan.selection_revision_ids is not None
        ):
            raise StrategyCenterWorkerBlocked(
                "strategy_evaluator_target_conflict"
            )
        if plan.evaluator_scope is not None:
            if len(plan.work_plans) != 1:
                raise StrategyCenterWorkerBlocked(
                    "bounded_scope_work_item_count_invalid"
                )
            selection = plan.work_plans[0].selection
            if (
                selection.principal_id != plan.evaluator_scope.principal_id
                or selection.user_id != plan.evaluator_scope.user_id
                or selection.selection_revision_id
                != plan.evaluator_scope.selection_revision_id
            ):
                raise StrategyCenterWorkerBlocked(
                    "bounded_scope_work_item_mismatch"
                )
        if plan.selection_revision_ids is not None and tuple(
            sorted(
                work.selection.selection_revision_id
                for work in plan.work_plans
            )
        ) != plan.selection_revision_ids:
            raise StrategyCenterWorkerBlocked(
                "strategy_selection_authority_incomplete"
            )

    def _apply_plan(self, cur: Any, plan: WorkerPlan) -> dict[str, Any]:
        counts = {
            "upsert": 0,
            "remove": 0,
            "reset": 0,
            "unchanged": 0,
            "observation_upsert": 0,
            "observation_remove": 0,
            "observation_unchanged": 0,
        }
        for work in plan.work_plans:
            selection = work.selection
            self._assert_selection_scope(selection, plan.evaluator_scope)
            cur.execute(
                """
                SELECT strategy_match_projection_id,
                       stock_identity_key,
                       action_episode_key,
                       strategy_version,
                       coherence_episode_key,
                       projection_hash,
                       matched_at
                FROM n6_strategy_match_projection
                WHERE selection_revision_id = %(selection_revision_id)s
                  AND principal_id = %(principal_id)s
                  AND principal_type = %(principal_type)s
                  AND user_id = %(user_id)s
                  AND trade_date = to_date(%(trade_date)s, 'YYYYMMDD')
                FOR UPDATE
                """,
                self._selection_params(selection, plan.trade_date),
            )
            existing = {
                (
                    str(row["stock_identity_key"]),
                    str(row["action_episode_key"]),
                    str(row.get("coherence_episode_key") or ""),
                ): dict(row)
                for row in cur.fetchall()
            }
            matched_keys: set[tuple[str, str, str]] = set()
            for match in work.matches:
                persisted_coherence_key = (
                    match.coherence_episode_key
                    if selection.strategy_version == STRATEGY_VERSION_V2
                    else ""
                )
                key = (
                    match.stock_identity_key,
                    match.action_episode_key,
                    persisted_coherence_key,
                )
                matched_keys.add(key)
                old = existing.get(key)
                confirmation_time = (
                    self._validated_match_confirmation_time(
                        match, plan.trade_date
                    )
                    if selection.strategy_version == STRATEGY_VERSION_V2
                    else plan.evaluation_time
                )
                if (
                    old is not None
                    and selection.strategy_version == STRATEGY_VERSION_V2
                ):
                    self._assert_existing_matched_at(
                        old, confirmation_time
                    )
                if old and old.get("projection_hash") == match.projection_hash:
                    counts["unchanged"] += 1
                    continue
                projection_id = self._upsert_match(
                    cur, plan, selection, match, old
                )
                if selection.selection_status == "active":
                    self._insert_change(
                        cur,
                        selection=selection,
                        trade_date=plan.trade_date,
                        change_type="upsert",
                        projection_id=projection_id,
                        source_event_id=self._current_event_id(match),
                        payload={
                            "strategy_match_projection_id": projection_id,
                            "evaluator_run_id": plan.evaluator_run_id,
                            **match.as_payload(),
                        },
                        dedup_suffix=(
                            f"{plan.evaluator_run_id}|{projection_id}|"
                            f"{match.projection_hash}"
                        ),
                    )
                counts["upsert"] += 1
            for key, old in existing.items():
                if key in matched_keys:
                    continue
                projection_id = int(old["strategy_match_projection_id"])
                payload = {
                    "strategy_match_projection_id": projection_id,
                    "trade_date": plan.trade_date,
                    "stock_identity_key": key[0],
                    "action_episode_key": key[1],
                    "coherence_episode_key": key[2] or None,
                    "selection_revision_id": selection.selection_revision_id,
                    "prior_projection_hash": str(old["projection_hash"]),
                    "evaluator_run_id": plan.evaluator_run_id,
                }
                self._insert_change(
                    cur,
                    selection=selection,
                    trade_date=plan.trade_date,
                    change_type="remove",
                    projection_id=projection_id,
                    source_event_id=None,
                    payload=payload,
                    dedup_suffix=(
                        f"{plan.evaluator_run_id}|{projection_id}|"
                        f"{old['projection_hash']}"
                    ),
                )
                cur.execute(
                    """
                    DELETE FROM n6_strategy_match_projection
                    WHERE strategy_match_projection_id = %(projection_id)s
                      AND selection_revision_id = %(selection_revision_id)s
                      AND principal_id = %(principal_id)s
                      AND principal_type = %(principal_type)s
                      AND user_id = %(user_id)s
                      AND trade_date = to_date(%(trade_date)s, 'YYYYMMDD')
                    """,
                    {
                        "projection_id": projection_id,
                        **self._selection_params(selection, plan.trade_date),
                    },
                )
                counts["remove"] += 1

            cur.execute(
                """
                SELECT strategy_observation_projection_id,
                       stock_identity_key,
                       action_episode_key,
                       coherence_episode_key,
                       observation_kind,
                       observation_hash,
                       observed_at
                FROM n6_strategy_observation_projection
                WHERE selection_revision_id = %(selection_revision_id)s
                  AND principal_id = %(principal_id)s
                  AND principal_type = %(principal_type)s
                  AND user_id = %(user_id)s
                  AND trade_date = to_date(%(trade_date)s, 'YYYYMMDD')
                FOR UPDATE
                """,
                self._selection_params(selection, plan.trade_date),
            )
            existing_observations = {
                (
                    str(row["stock_identity_key"]),
                    str(row["action_episode_key"]),
                    str(row["coherence_episode_key"]),
                    str(row["observation_kind"]),
                ): dict(row)
                for row in cur.fetchall()
            }
            observed_keys: set[tuple[str, str, str, str]] = set()
            for observation in work.observations:
                key = (
                    observation.stock_identity_key,
                    observation.action_episode_key,
                    observation.coherence_episode_key,
                    observation.observation_reason,
                )
                observed_keys.add(key)
                old_observation = existing_observations.get(key)
                confirmation_time = self._validated_match_confirmation_time(
                    observation, plan.trade_date
                )
                if old_observation is not None:
                    self._assert_existing_observed_at(
                        old_observation, confirmation_time
                    )
                if (
                    old_observation
                    and old_observation.get("observation_hash")
                    == observation.observation_hash
                ):
                    counts["observation_unchanged"] += 1
                    continue
                observation_id = self._upsert_observation(
                    cur,
                    plan,
                    selection,
                    observation,
                    old_observation,
                )
                if selection.selection_status == "active":
                    self._insert_change(
                        cur,
                        selection=selection,
                        trade_date=plan.trade_date,
                        change_type="upsert",
                        surface_kind="observation",
                        projection_id=None,
                        observation_id=observation_id,
                        source_event_id=self._current_observation_event_id(
                            observation
                        ),
                        payload={
                            "strategy_observation_projection_id": observation_id,
                            "evaluator_run_id": plan.evaluator_run_id,
                            **observation.as_payload(),
                        },
                        dedup_suffix=(
                            f"{plan.evaluator_run_id}|{observation_id}|"
                            f"{observation.observation_hash}"
                        ),
                    )
                counts["observation_upsert"] += 1
            for key, old_observation in existing_observations.items():
                if key in observed_keys:
                    continue
                observation_id = int(
                    old_observation["strategy_observation_projection_id"]
                )
                payload = {
                    "strategy_observation_projection_id": observation_id,
                    "trade_date": plan.trade_date,
                    "stock_identity_key": key[0],
                    "action_episode_key": key[1],
                    "coherence_episode_key": key[2],
                    "observation_reason": key[3],
                    "selection_revision_id": selection.selection_revision_id,
                    "prior_observation_hash": str(
                        old_observation["observation_hash"]
                    ),
                    "evaluator_run_id": plan.evaluator_run_id,
                }
                self._insert_change(
                    cur,
                    selection=selection,
                    trade_date=plan.trade_date,
                    change_type="remove",
                    surface_kind="observation",
                    projection_id=None,
                    observation_id=observation_id,
                    source_event_id=None,
                    payload=payload,
                    dedup_suffix=(
                        f"{plan.evaluator_run_id}|{observation_id}|"
                        f"{old_observation['observation_hash']}"
                    ),
                )
                cur.execute(
                    """
                    DELETE FROM n6_strategy_observation_projection
                    WHERE strategy_observation_projection_id =
                          %(observation_id)s
                      AND selection_revision_id = %(selection_revision_id)s
                      AND principal_id = %(principal_id)s
                      AND principal_type = %(principal_type)s
                      AND user_id = %(user_id)s
                      AND trade_date = to_date(%(trade_date)s, 'YYYYMMDD')
                    """,
                    {
                        "observation_id": observation_id,
                        **self._selection_params(selection, plan.trade_date),
                    },
                )
                if cur.rowcount != 1:
                    raise StrategyCenterWorkerBlocked(
                        "strategy_observation_remove_failed"
                    )
                counts["observation_remove"] += 1
            if selection.selection_status == "pending":
                self._activate_pending(
                    cur, selection, evaluator_scope=plan.evaluator_scope
                )
                reset_payload = {
                    "trade_date": plan.trade_date,
                    "selection_revision_id": selection.selection_revision_id,
                    "revision_no": selection.revision_no,
                    "selected_package_keys": list(selection.selected_package_keys),
                    "evaluator_run_id": plan.evaluator_run_id,
                    "snapshot_hash": plan.snapshot_hash,
                }
                self._insert_change(
                    cur,
                    selection=selection,
                    trade_date=plan.trade_date,
                    change_type="reset",
                    projection_id=None,
                    source_event_id=None,
                    payload=reset_payload,
                    dedup_suffix=(
                        f"{plan.evaluator_run_id}|{plan.snapshot_hash}"
                    ),
                )
                counts["reset"] += 1
            elif selection.replay_status != "passed":
                cur.execute(
                    """
                    UPDATE n6_user_strategy_selection_revision
                    SET replay_status = 'passed'
                    WHERE selection_revision_id = %(selection_revision_id)s
                      AND principal_id = %(principal_id)s
                      AND principal_type = %(principal_type)s
                      AND user_id = %(user_id)s
                      AND selection_status = 'active'
                    """,
                    self._selection_params(selection, plan.trade_date),
                )
        return {"committed": True, **counts}

    @staticmethod
    def _assert_selection_scope(
        selection: SelectionWorkItem,
        scope: StrategyEvaluatorScope | None,
    ) -> None:
        if scope is not None and (
            selection.principal_id != scope.principal_id
            or selection.user_id != scope.user_id
            or selection.selection_revision_id != scope.selection_revision_id
        ):
            raise StrategyCenterWorkerBlocked("bounded_scope_work_item_mismatch")

    @staticmethod
    def _selection_params(
        selection: SelectionWorkItem, trade_date: str
    ) -> dict[str, Any]:
        return {
            "selection_revision_id": selection.selection_revision_id,
            "principal_id": selection.principal_id,
            "principal_type": selection.principal_type,
            "user_id": selection.user_id,
            "trade_date": trade_date,
        }

    @staticmethod
    def _validated_match_confirmation_time(
        match: StrategyMatch | StrategyObservation, trade_date: str
    ) -> str:
        audit = match.confluence
        if not isinstance(audit, Mapping):
            raise StrategyCenterWorkerBlocked(
                "strategy_match_confirmation_time_invalid"
            )
        value = audit.get("confirmation_time")
        if not isinstance(value, str) or not value.strip():
            raise StrategyCenterWorkerBlocked(
                "strategy_match_confirmation_time_invalid"
            )
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise StrategyCenterWorkerBlocked(
                "strategy_match_confirmation_time_invalid"
            ) from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise StrategyCenterWorkerBlocked(
                "strategy_match_confirmation_time_invalid"
            )
        local = parsed.astimezone(SHANGHAI_TIMEZONE)
        if local.strftime("%Y%m%d") != trade_date:
            raise StrategyCenterWorkerBlocked(
                "strategy_match_confirmation_time_invalid"
            )
        clock_seconds = (
            local.hour * 3600
            + local.minute * 60
            + local.second
            + local.microsecond / 1_000_000
        )
        in_morning = (
            9 * 3600 + 30 * 60
            <= clock_seconds
            <= 11 * 3600 + 30 * 60
        )
        in_afternoon = 13 * 3600 <= clock_seconds <= 15 * 3600
        if not (in_morning or in_afternoon):
            raise StrategyCenterWorkerBlocked(
                "strategy_match_confirmation_time_invalid"
            )
        return value

    @staticmethod
    def _assert_existing_matched_at(
        old: Mapping[str, Any], confirmation_time: str
    ) -> None:
        value = old.get("matched_at")
        if isinstance(value, datetime):
            existing = value
        elif isinstance(value, str):
            try:
                existing = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as error:
                raise StrategyCenterWorkerBlocked(
                    "strategy_projection_matched_at_mismatch"
                ) from error
        else:
            raise StrategyCenterWorkerBlocked(
                "strategy_projection_matched_at_mismatch"
            )
        expected = datetime.fromisoformat(
            confirmation_time.replace("Z", "+00:00")
        )
        if (
            existing.tzinfo is None
            or existing.utcoffset() is None
            or existing.astimezone(timezone.utc)
            != expected.astimezone(timezone.utc)
        ):
            raise StrategyCenterWorkerBlocked(
                "strategy_projection_matched_at_mismatch"
            )

    @staticmethod
    def _assert_existing_observed_at(
        old: Mapping[str, Any], confirmation_time: str
    ) -> None:
        value = old.get("observed_at")
        if isinstance(value, datetime):
            existing = value
        elif isinstance(value, str):
            try:
                existing = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as error:
                raise StrategyCenterWorkerBlocked(
                    "strategy_observation_observed_at_mismatch"
                ) from error
        else:
            raise StrategyCenterWorkerBlocked(
                "strategy_observation_observed_at_mismatch"
            )
        expected = datetime.fromisoformat(
            confirmation_time.replace("Z", "+00:00")
        )
        if (
            existing.tzinfo is None
            or existing.utcoffset() is None
            or existing.astimezone(timezone.utc)
            != expected.astimezone(timezone.utc)
        ):
            raise StrategyCenterWorkerBlocked(
                "strategy_observation_observed_at_mismatch"
            )

    def _upsert_observation(
        self,
        cur: Any,
        plan: WorkerPlan,
        selection: SelectionWorkItem,
        observation: StrategyObservation,
        old: Mapping[str, Any] | None,
    ) -> int:
        confirmation_time = self._validated_match_confirmation_time(
            observation, plan.trade_date
        )
        if old is not None:
            self._assert_existing_observed_at(old, confirmation_time)
        params = {
            **self._selection_params(selection, plan.trade_date),
            "stock_identity_key": observation.stock_identity_key,
            "action_episode_key": observation.action_episode_key,
            "coherence_episode_key": observation.coherence_episode_key,
            "action_state": observation.action_state,
            "source_signal_projection_id": (
                observation.source_signal_projection_id
            ),
            "source_event_ids": list(observation.source_event_ids),
            "observed_packages": list(observation.observed_packages),
            "scope_sources": list(observation.scope_sources),
            "indices_json": Jsonb(list(observation.indices)),
            "observed_boards_json": Jsonb(list(observation.observed_boards)),
            "signal_json": Jsonb(dict(observation.signal)),
            "strategy_version": "v2",
            "direction": str(observation.confluence["direction"]),
            "coherence_level": str(
                observation.confluence["coherence_level"]
            ),
            "freshness_status": str(
                observation.confluence["freshness_status"]
            ),
            "qualification_status": "observation_only",
            "confluence_json": Jsonb(dict(observation.confluence)),
            "package_evidence_json": Jsonb(
                list(observation.confluence["package_evidence"])
            ),
            "state_timeline_json": Jsonb(list(observation.state_timeline)),
            "mapping_quality": observation.mapping_quality,
            "membership_source_trade_date": (
                observation.membership_source_trade_date
            ),
            "evaluator_policy_hash": observation.evaluator_policy_hash,
            "observation_hash": observation.observation_hash,
            "observation_kind": observation.observation_reason,
            "observed_at": confirmation_time,
        }
        if old is None:
            cur.execute(
                """
                INSERT INTO n6_strategy_observation_projection (
                  selection_revision_id, principal_id, principal_type, user_id,
                  trade_date, stock_identity_key, action_episode_key,
                  coherence_episode_key,
                  action_state, source_signal_projection_id, source_event_ids,
                  observed_packages, scope_sources, indices_json,
                  observed_boards_json, signal_json, state_timeline_json,
                  mapping_quality, membership_source_trade_date,
                  strategy_version, direction, coherence_level,
                  freshness_status, qualification_status, confluence_json,
                  package_evidence_json, evaluator_policy_hash,
                  observation_hash, observation_kind, observed_at
                ) VALUES (
                  %(selection_revision_id)s, %(principal_id)s,
                  %(principal_type)s, %(user_id)s,
                  to_date(%(trade_date)s, 'YYYYMMDD'),
                  %(stock_identity_key)s, %(action_episode_key)s,
                  %(coherence_episode_key)s,
                  %(action_state)s, %(source_signal_projection_id)s,
                  %(source_event_ids)s, %(observed_packages)s, %(scope_sources)s,
                  %(indices_json)s, %(observed_boards_json)s, %(signal_json)s,
                  %(state_timeline_json)s, %(mapping_quality)s,
                  to_date(%(membership_source_trade_date)s, 'YYYYMMDD'),
                  %(strategy_version)s, %(direction)s, %(coherence_level)s,
                  %(freshness_status)s, %(qualification_status)s,
                  %(confluence_json)s, %(package_evidence_json)s,
                  %(evaluator_policy_hash)s, %(observation_hash)s,
                  %(observation_kind)s,
                  %(observed_at)s::timestamptz
                )
                RETURNING strategy_observation_projection_id
                """,
                params,
            )
        else:
            params["observation_id"] = int(
                old["strategy_observation_projection_id"]
            )
            cur.execute(
                """
                UPDATE n6_strategy_observation_projection
                SET action_state = %(action_state)s,
                    source_signal_projection_id = %(source_signal_projection_id)s,
                    source_event_ids = %(source_event_ids)s,
                    observed_packages = %(observed_packages)s,
                    scope_sources = %(scope_sources)s,
                    indices_json = %(indices_json)s,
                    observed_boards_json = %(observed_boards_json)s,
                    signal_json = %(signal_json)s,
                    strategy_version = %(strategy_version)s,
                    direction = %(direction)s,
                    coherence_level = %(coherence_level)s,
                    freshness_status = %(freshness_status)s,
                    qualification_status = %(qualification_status)s,
                    confluence_json = %(confluence_json)s,
                    package_evidence_json = %(package_evidence_json)s,
                    state_timeline_json = %(state_timeline_json)s,
                    mapping_quality = %(mapping_quality)s,
                    membership_source_trade_date = to_date(
                      %(membership_source_trade_date)s, 'YYYYMMDD'
                    ),
                    evaluator_policy_hash = %(evaluator_policy_hash)s,
                    observation_hash = %(observation_hash)s,
                    observation_kind = %(observation_kind)s,
                    updated_at = pg_catalog.clock_timestamp()
                WHERE strategy_observation_projection_id =
                      %(observation_id)s
                  AND selection_revision_id = %(selection_revision_id)s
                  AND principal_id = %(principal_id)s
                  AND principal_type = %(principal_type)s
                  AND user_id = %(user_id)s
                  AND trade_date = to_date(%(trade_date)s, 'YYYYMMDD')
                RETURNING strategy_observation_projection_id
                """,
                params,
            )
        row = cur.fetchone()
        if not row:
            raise StrategyCenterWorkerBlocked(
                "strategy_observation_upsert_failed"
            )
        return int(row["strategy_observation_projection_id"])

    def _upsert_match(
        self,
        cur: Any,
        plan: WorkerPlan,
        selection: SelectionWorkItem,
        match: StrategyMatch,
        old: Mapping[str, Any] | None,
    ) -> int:
        is_v2 = selection.strategy_version == STRATEGY_VERSION_V2
        confirmation_time = (
            self._validated_match_confirmation_time(match, plan.trade_date)
            if is_v2
            else plan.evaluation_time
        )
        if old is not None and is_v2:
            self._assert_existing_matched_at(old, confirmation_time)
        params = {
            **self._selection_params(selection, plan.trade_date),
            "stock_identity_key": match.stock_identity_key,
            "action_episode_key": match.action_episode_key,
            "strategy_version": "v2" if is_v2 else "v1",
            "coherence_episode_key": (
                match.coherence_episode_key if is_v2 else None
            ),
            "direction": (
                str(match.confluence["direction"]) if is_v2 else None
            ),
            "coherence_level": (
                str(match.confluence["coherence_level"]) if is_v2 else None
            ),
            "freshness_status": (
                str(match.confluence["freshness_status"]) if is_v2 else None
            ),
            "confluence_json": (
                Jsonb(dict(match.confluence)) if is_v2 else None
            ),
            "package_evidence_json": (
                Jsonb(list(match.confluence["package_evidence"]))
                if is_v2
                else None
            ),
            "action_state": match.action_state,
            "source_signal_projection_id": match.source_signal_projection_id,
            "source_event_ids": list(match.source_event_ids),
            "matched_packages": list(match.matched_packages),
            "scope_sources": list(match.scope_sources),
            "indices_json": Jsonb(list(match.indices)),
            "matched_boards_json": Jsonb(list(match.matched_boards)),
            "signal_json": Jsonb(dict(match.signal)),
            "state_timeline_json": Jsonb(list(match.state_timeline)),
            "mapping_quality": match.mapping_quality,
            "membership_source_trade_date": match.membership_source_trade_date,
            "evaluator_policy_hash": match.evaluator_policy_hash,
            "projection_hash": match.projection_hash,
            "matched_at": confirmation_time,
        }
        if old is None:
            cur.execute(
                """
                INSERT INTO n6_strategy_match_projection (
                  selection_revision_id, principal_id, principal_type, user_id,
                  trade_date, stock_identity_key, action_episode_key,
                  strategy_version, coherence_episode_key, direction,
                  coherence_level, freshness_status, confluence_json,
                  package_evidence_json,
                  action_state, source_signal_projection_id, source_event_ids,
                  matched_packages, scope_sources, indices_json,
                  matched_boards_json, signal_json, state_timeline_json,
                  mapping_quality, membership_source_trade_date,
                  evaluator_policy_hash, projection_hash, matched_at
                ) VALUES (
                  %(selection_revision_id)s, %(principal_id)s,
                  %(principal_type)s, %(user_id)s,
                  to_date(%(trade_date)s, 'YYYYMMDD'),
                  %(stock_identity_key)s, %(action_episode_key)s,
                  %(strategy_version)s, %(coherence_episode_key)s,
                  %(direction)s, %(coherence_level)s, %(freshness_status)s,
                  %(confluence_json)s, %(package_evidence_json)s,
                  %(action_state)s, %(source_signal_projection_id)s,
                  %(source_event_ids)s, %(matched_packages)s, %(scope_sources)s,
                  %(indices_json)s, %(matched_boards_json)s, %(signal_json)s,
                  %(state_timeline_json)s, %(mapping_quality)s,
                  to_date(%(membership_source_trade_date)s, 'YYYYMMDD'),
                  %(evaluator_policy_hash)s, %(projection_hash)s,
                  %(matched_at)s::timestamptz
                )
                RETURNING strategy_match_projection_id
                """,
                params,
            )
        else:
            params["projection_id"] = int(old["strategy_match_projection_id"])
            cur.execute(
                """
                UPDATE n6_strategy_match_projection
                SET strategy_version = %(strategy_version)s,
                    coherence_episode_key = %(coherence_episode_key)s,
                    direction = %(direction)s,
                    coherence_level = %(coherence_level)s,
                    freshness_status = %(freshness_status)s,
                    confluence_json = %(confluence_json)s,
                    package_evidence_json = %(package_evidence_json)s,
                    action_state = %(action_state)s,
                    source_signal_projection_id = %(source_signal_projection_id)s,
                    source_event_ids = %(source_event_ids)s,
                    matched_packages = %(matched_packages)s,
                    scope_sources = %(scope_sources)s,
                    indices_json = %(indices_json)s,
                    matched_boards_json = %(matched_boards_json)s,
                    signal_json = %(signal_json)s,
                    state_timeline_json = %(state_timeline_json)s,
                    mapping_quality = %(mapping_quality)s,
                    membership_source_trade_date = to_date(
                      %(membership_source_trade_date)s, 'YYYYMMDD'
                    ),
                    evaluator_policy_hash = %(evaluator_policy_hash)s,
                    projection_hash = %(projection_hash)s,
                    updated_at = pg_catalog.clock_timestamp()
                WHERE strategy_match_projection_id = %(projection_id)s
                  AND selection_revision_id = %(selection_revision_id)s
                  AND principal_id = %(principal_id)s
                  AND principal_type = %(principal_type)s
                  AND user_id = %(user_id)s
                  AND trade_date = to_date(%(trade_date)s, 'YYYYMMDD')
                RETURNING strategy_match_projection_id
                """,
                params,
            )
        row = cur.fetchone()
        if not row:
            raise StrategyCenterWorkerBlocked("strategy_projection_upsert_failed")
        return int(row["strategy_match_projection_id"])

    @staticmethod
    def _current_event_id(match: StrategyMatch) -> str:
        for item in reversed(match.state_timeline):
            if int(item["source_signal_projection_id"]) == match.source_signal_projection_id:
                return str(item["event_id"])
        raise StrategyCenterWorkerBlocked("current_signal_event_provenance_missing")

    @staticmethod
    def _current_observation_event_id(
        observation: StrategyObservation,
    ) -> str:
        for item in reversed(observation.state_timeline):
            if (
                int(item["source_signal_projection_id"])
                == observation.source_signal_projection_id
            ):
                return str(item["event_id"])
        raise StrategyCenterWorkerBlocked(
            "current_signal_event_provenance_missing"
        )

    def _insert_change(
        self,
        cur: Any,
        *,
        selection: SelectionWorkItem,
        trade_date: str,
        change_type: str,
        projection_id: int | None,
        source_event_id: str | None,
        payload: Mapping[str, Any],
        dedup_suffix: str,
        surface_kind: str = "qualified_match",
        observation_id: int | None = None,
    ) -> None:
        if surface_kind not in {"qualified_match", "observation"}:
            raise StrategyCenterWorkerBlocked(
                "strategy_change_surface_kind_invalid"
            )
        if (surface_kind == "qualified_match") != (observation_id is None):
            raise StrategyCenterWorkerBlocked(
                "strategy_change_surface_authority_invalid"
            )
        if surface_kind == "observation" and projection_id is not None:
            raise StrategyCenterWorkerBlocked(
                "strategy_change_surface_authority_invalid"
            )
        payload_hash = _hash(payload)
        dedup_key = (
            f"strategy-center|{change_type}|{selection.selection_revision_id}|"
            f"{trade_date}|{dedup_suffix}"
        )
        cur.execute(
            """
            INSERT INTO n6_strategy_match_change (
              strategy_match_projection_id,
              strategy_observation_projection_id, surface_kind,
              selection_revision_id,
              principal_id, principal_type, user_id, trade_date, change_type,
              dedup_key, source_event_id, payload_json, payload_hash
            ) VALUES (
              %(projection_id)s, %(observation_id)s, %(surface_kind)s,
              %(selection_revision_id)s,
              %(principal_id)s, %(principal_type)s, %(user_id)s,
              to_date(%(trade_date)s, 'YYYYMMDD'), %(change_type)s,
              %(dedup_key)s, %(source_event_id)s, %(payload_json)s,
              %(payload_hash)s
            )
            ON CONFLICT (principal_id, principal_type, user_id, dedup_key)
            DO NOTHING
            """,
            {
                "projection_id": projection_id,
                "observation_id": observation_id,
                "surface_kind": surface_kind,
                "selection_revision_id": selection.selection_revision_id,
                "principal_id": selection.principal_id,
                "principal_type": selection.principal_type,
                "user_id": selection.user_id,
                "trade_date": trade_date,
                "change_type": change_type,
                "dedup_key": dedup_key,
                "source_event_id": source_event_id,
                "payload_json": Jsonb(dict(payload)),
                "payload_hash": payload_hash,
            },
        )

    @staticmethod
    def _activate_pending(
        cur: Any,
        selection: SelectionWorkItem,
        *,
        evaluator_scope: StrategyEvaluatorScope | None = None,
    ) -> None:
        PostgresStrategyCenterEvaluatorRepository._assert_selection_scope(
            selection, evaluator_scope
        )
        if selection.active_revision_id is not None:
            cur.execute(
                """
                UPDATE n6_user_strategy_selection_revision
                SET selection_status = 'superseded',
                    superseded_at = pg_catalog.clock_timestamp()
                WHERE selection_revision_id = %(active_revision_id)s
                  AND principal_id = %(principal_id)s
                  AND principal_type = %(principal_type)s
                  AND user_id = %(user_id)s
                  AND selection_status = 'active'
                """,
                asdict(selection),
            )
            if cur.rowcount != 1:
                raise StrategyCenterWorkerBlocked(
                    "active_selection_supersession_cas_failed"
                )
        cur.execute(
            """
            UPDATE n6_user_strategy_selection_revision
            SET selection_status = 'active',
                replay_status = 'passed',
                activated_at = COALESCE(
                  activated_at, pg_catalog.clock_timestamp()
                )
            WHERE selection_revision_id = %(selection_revision_id)s
              AND principal_id = %(principal_id)s
              AND principal_type = %(principal_type)s
              AND user_id = %(user_id)s
              AND selection_status = 'pending'
            """,
            asdict(selection),
        )
        if cur.rowcount != 1:
            raise StrategyCenterWorkerBlocked("pending_selection_activation_cas_failed")
