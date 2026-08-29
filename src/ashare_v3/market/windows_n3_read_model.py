"""Read-only N2 input adapter for the Windows N3 memory runtime."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from types import MappingProxyType
from typing import Any

from ashare_v3.market.windows_n3_memory import AverageAmountBaseline
from ashare_v3.market.windows_n3_snapshot import (
    BoardSnapshotRequest,
    IndexSnapshotRequest,
    StockSnapshotRequest,
)


PERIODS = ("Y", "Q", "M", "W", "D")
HIGHER_PERIODS = ("W", "M", "Q", "Y")
WINDOWS_TQ_DAILY_AMOUNT_TO_YUAN = Decimal("10000")


class ActiveN2RunUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class N2PeriodRuntimeBaseline:
    period: str
    grade: str | None
    transition: str | None
    previous_entity_high: Decimal | None
    previous_entity_low: Decimal | None
    previous_amount_baseline: Decimal | None
    completed_amount_sum: Decimal | None
    completed_trade_days: int | None
    period_key: str | None = None


@dataclass(frozen=True, slots=True)
class N2ObjectRuntimeInput:
    asset_kind: str
    identity_key: str
    exchange: str
    code: str
    name: str
    periods: Mapping[str, N2PeriodRuntimeBaseline]
    basis_trade_date: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "periods", MappingProxyType(dict(self.periods)))

    def higher_amount_baselines(self) -> Mapping[str, AverageAmountBaseline]:
        values: dict[str, AverageAmountBaseline] = {}
        for period in HIGHER_PERIODS:
            item = self.periods.get(period)
            if (
                item is None
                or item.completed_amount_sum is None
                or item.completed_trade_days is None
            ):
                continue
            values[period] = AverageAmountBaseline(
                item.completed_amount_sum,
                item.completed_trade_days,
            )
        return MappingProxyType(values)


@dataclass(frozen=True, slots=True)
class N3ActiveReadModel:
    run_id: str
    source_trade_date: str
    for_trade_date: str
    stock: tuple[N2ObjectRuntimeInput, ...]
    index: tuple[N2ObjectRuntimeInput, ...]
    board: tuple[N2ObjectRuntimeInput, ...]

    def stock_requests(self) -> tuple[StockSnapshotRequest, ...]:
        return tuple(
            StockSnapshotRequest(row.identity_key, row.exchange, row.code, row.name)
            for row in self.stock
        )

    def index_requests(self) -> tuple[IndexSnapshotRequest, ...]:
        return tuple(
            IndexSnapshotRequest(row.identity_key, row.exchange, row.code, row.name)
            for row in self.index
        )

    def board_requests(self) -> tuple[BoardSnapshotRequest, ...]:
        return tuple(
            BoardSnapshotRequest(row.identity_key, row.exchange, row.code, row.name)
            for row in self.board
        )

    def higher_amount_baselines(self, asset_kind: str) -> Mapping[str, Mapping[str, AverageAmountBaseline]]:
        rows = getattr(self, asset_kind)
        return MappingProxyType(
            {row.identity_key: row.higher_amount_baselines() for row in rows}
        )


class WindowsN3ReadOnlyRepository:
    def __init__(
        self,
        dsn: str,
        *,
        connect: Callable[[str], Any] | None = None,
    ) -> None:
        self.dsn = dsn
        self._connect = connect or _connect_read_only

    def is_open_trade_date(self, trade_date: str) -> bool:
        connection = self._connect(self.dsn)
        try:
            row = _fetchone(
                connection,
                "SELECT is_open FROM common_trade_calendar WHERE trade_date = %s",
                (trade_date,),
            )
            return bool(row and _value(row, "is_open", 0))
        finally:
            connection.close()

    def load_active(self, for_trade_date: str) -> N3ActiveReadModel:
        connection = self._connect(self.dsn)
        try:
            runs = _fetchall(
                connection,
                """
                SELECT run_id, source_trade_date, for_trade_date
                FROM common_condition_run
                WHERE for_trade_date = %s AND status = 'passed_active'
                ORDER BY finished_at DESC NULLS LAST, created_at DESC
                """,
                (for_trade_date,),
            )
            if not runs:
                raise ActiveN2RunUnavailable(
                    f"no passed_active N2 run for {for_trade_date}"
                )
            if len(runs) != 1:
                raise ActiveN2RunUnavailable(
                    f"conflicting passed_active N2 runs for {for_trade_date}: {len(runs)}"
                )
            run = runs[0]
            run_id = str(_value(run, "run_id", 0))
            source_trade_date = str(_value(run, "source_trade_date", 1))
            stock = self._load_asset(connection, "stock", run_id, source_trade_date, for_trade_date)
            index = self._load_asset(connection, "index", run_id, source_trade_date, for_trade_date)
            board = self._load_asset(connection, "board", run_id, source_trade_date, for_trade_date)
            return N3ActiveReadModel(
                run_id=run_id,
                source_trade_date=source_trade_date,
                for_trade_date=for_trade_date,
                stock=stock,
                index=index,
                board=board,
            )
        finally:
            connection.close()

    def _load_asset(
        self,
        connection: Any,
        asset_kind: str,
        run_id: str,
        source_trade_date: str,
        for_trade_date: str,
    ) -> tuple[N2ObjectRuntimeInput, ...]:
        identity_column = f"{asset_kind}_identity_key"
        table = f"{asset_kind}_condition_basis"
        code_column = "board_code" if asset_kind == "board" else "code"
        name_column = "board_name" if asset_kind == "board" else "name"
        exchange_expression = "'SH'" if asset_kind == "board" else "exchange"
        query = f"""
            SELECT DISTINCT ON ({identity_column})
                   {identity_column} AS identity_key,
                   {exchange_expression} AS exchange,
                   {code_column} AS code,
                   {name_column} AS name,
                   period_key_d AS basis_trade_date,
                   period_grade_y, period_grade_q, period_grade_m,
                   period_grade_w, period_grade_d,
                   period_transition_y, period_transition_q, period_transition_m,
                   period_transition_w, period_transition_d,
                   period_trigger_baseline_json,
                   period_key_y, period_key_q, period_key_m, period_key_w, period_key_d
            FROM {table}
            WHERE run_id = %s
            ORDER BY {identity_column}, updated_at DESC, created_at DESC
        """
        rows = _fetchall(connection, query, (run_id,))
        return tuple(
            _runtime_input(asset_kind, row, source_trade_date, for_trade_date)
            for row in rows
        )


def _runtime_input(asset_kind: str, row: Any, source_trade_date: str, for_trade_date: str) -> N2ObjectRuntimeInput:
    baseline = _json_object(_value(row, "period_trigger_baseline_json", 15))
    baseline_periods = baseline.get("periods")
    if not isinstance(baseline_periods, Mapping):
        baseline_periods = {}
    periods: dict[str, N2PeriodRuntimeBaseline] = {}
    for offset, period in enumerate(PERIODS):
        entry = baseline_periods.get(period)
        if not isinstance(entry, Mapping):
            entry = {}
        factor = WINDOWS_TQ_DAILY_AMOUNT_TO_YUAN
        source_key = _period_key(source_trade_date, period)
        for_key = _period_key(for_trade_date, period)
        stored_key = _optional_text(entry.get("period_key_current")) or _optional_text(
            _value(row, f"period_key_{period.lower()}", 16 + offset)
        )
        current_total = _decimal(entry.get("current_amount_total_seed"))
        current_days = _integer(entry.get("current_trade_days_seed"))
        current_average = _decimal(entry.get("current_amount_seed"))
        previous_average = _decimal(entry.get("previous_avg_amount")) or _decimal(
            entry.get("classification_previous_amount_baseline")
        )
        rollover = period in HIGHER_PERIODS and source_key != for_key
        if rollover:
            previous_average = current_average
            current_total = Decimal(0)
            current_days = 0
        periods[period] = N2PeriodRuntimeBaseline(
            period=period,
            grade=_optional_text(_value(row, f"period_grade_{period.lower()}", 5 + offset)),
            transition=_optional_text(_value(row, f"period_transition_{period.lower()}", 10 + offset)),
            previous_entity_high=_decimal(entry.get("trigger_previous_entity_high")),
            previous_entity_low=_decimal(entry.get("trigger_previous_entity_low")),
            previous_amount_baseline=previous_average * factor if previous_average is not None else None,
            completed_amount_sum=current_total * factor if current_total is not None else None,
            completed_trade_days=current_days,
            period_key=stored_key,
        )
    return N2ObjectRuntimeInput(
        asset_kind=asset_kind,
        identity_key=str(_value(row, "identity_key", 0)),
        exchange=str(_value(row, "exchange", 1)),
        code=str(_value(row, "code", 2)),
        name=str(_value(row, "name", 3)),
        basis_trade_date=_optional_text(_value(row, "basis_trade_date", 4)),
        periods=periods,
    )


def _connect_read_only(dsn: str) -> Any:
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(
        dsn,
        autocommit=True,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    )


def _fetchone(connection: Any, query: str, params: tuple[Any, ...]) -> Any:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchone()


def _fetchall(connection: Any, query: str, params: tuple[Any, ...]) -> list[Any]:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return list(cursor.fetchall())


def _value(row: Any, name: str, position: int) -> Any:
    if isinstance(row, Mapping):
        return row.get(name)
    return row[position]


def _json_object(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, Mapping):
            return parsed
    return {}


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _period_key(trade_date: str, period: str) -> str | None:
    try:
        value = datetime.strptime(trade_date, "%Y%m%d")
    except ValueError:
        return None
    if period == "W":
        year, week, _ = value.isocalendar()
        return f"{year}W{week:02d}"
    if period == "M":
        return value.strftime("%Y%m")
    if period == "Q":
        return f"{value.year}Q{(value.month - 1) // 3 + 1}"
    if period == "Y":
        return str(value.year)
    return trade_date
