"""Local REST calendar synchronization for the Windows N1 final gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .common_index import normalize_trade_calendar_rows
from .windows_n1_postgres import WindowsN1PostgresRepository, stable_rows_hash
from .windows_n1_sources import LOCAL_TRADE_CALENDAR_SOURCE, LocalTradeCalendarProvider


@dataclass(frozen=True)
class WindowsN1CalendarResult:
    result: str
    batch_id: str
    start_date: str
    end_date: str
    api_rows: int
    evidence: dict[str, Any]


def sync_local_trade_calendar(
    *, provider: LocalTradeCalendarProvider,
    repository: WindowsN1PostgresRepository,
    exchange: str = "SSE",
) -> WindowsN1CalendarResult:
    """Fetch completely, validate completely, then perform one atomic N1 write."""
    health = provider.health()
    available = provider.range(exchange)
    start_date = available["min"]
    end_date = available["max"]
    raw_rows = provider.fetch(start_date, end_date, exchange)
    raw_hash = stable_rows_hash(raw_rows)
    batch_id = f"local_trade_calendar_rest_{start_date}_{end_date}_{raw_hash[:16]}"
    rows = normalize_trade_calendar_rows(
        raw_rows,
        source=LOCAL_TRADE_CALENDAR_SOURCE,
        source_batch_id=batch_id,
        source_version=LOCAL_TRADE_CALENDAR_SOURCE,
    )
    if len(rows) != len(raw_rows):
        raise RuntimeError("local trade-calendar normalization changed row count")
    if rows[0]["trade_date"] != start_date or rows[-1]["trade_date"] != end_date:
        raise RuntimeError("local trade-calendar normalized range mismatch")

    before_downstream = repository.downstream_row_counts()
    with repository.connection.transaction():
        repository.persist_local_trade_calendar(
            rows=rows,
            batch_id=batch_id,
            start_date=start_date,
            end_date=end_date,
            exchange=exchange,
        )
        evidence = repository.assert_n1_final_ready_for_n2(
            start_date=start_date,
            end_date=end_date,
            expected_calendar_rows=len(rows),
            exchange=exchange,
        )
        after_downstream = repository.downstream_row_counts()
        if after_downstream != before_downstream:
            raise RuntimeError("N2-N6/downstream rows changed during calendar synchronization")
    evidence.update(
        {
            "calendar_health": health,
            "calendar_range": available,
            "downstream_before_counts": before_downstream,
            "downstream_after_counts": after_downstream,
            "downstream_delta": 0,
            "uses_rest_only": True,
            "trade_calendar_database_access": False,
        }
    )
    return WindowsN1CalendarResult(
        result="N1_FINAL_READY_FOR_N2",
        batch_id=batch_id,
        start_date=start_date,
        end_date=end_date,
        api_rows=len(rows),
        evidence=evidence,
    )
