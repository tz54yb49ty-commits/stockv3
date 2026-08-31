"""Completion-marker driven daily-bar gap fill for the Windows N1 Fastlane."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from typing import Any

from .windows_n1_bootstrap import BootstrapResult
from .windows_n1_postgres import WindowsN1PostgresRepository
from .windows_n1_production import load_tq_scopes, persist_daily_bars_batched
from .windows_n1_sources import LocalTradeCalendarProvider, TQWindowsSource


DAILY_CUTOFF = time(16, 30)


@dataclass(frozen=True)
class GapDateResult:
    trade_date: str
    source_version: str
    before_counts: dict[str, dict[str, int]]
    after_counts: dict[str, dict[str, int]]
    written_rows: dict[str, int]
    batch_counts: dict[str, int]
    source_counts: dict[str, dict[str, int]]


@dataclass(frozen=True)
class RecentGapFillResult:
    result: str
    last_complete_date: str | None
    gap_dates: tuple[str, ...]
    dates: tuple[GapDateResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def at_or_after_daily_cutoff(now: datetime) -> bool:
    return now.time() >= DAILY_CUTOFF


def resolve_daily_source_trade_date(
    requested: str | None, *, today: date,
) -> str:
    """Resolve one daily source date without permitting future execution."""
    if requested is None:
        return today.strftime("%Y%m%d")
    try:
        parsed = datetime.strptime(requested, "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError("source_trade_date must use YYYYMMDD") from exc
    if parsed > today:
        raise ValueError("source_trade_date cannot be in the future")
    return parsed.strftime("%Y%m%d")


def daily_cutoff_is_required(source_trade_date: str, *, today: date) -> bool:
    """Only today's daily run is subject to the 16:30 wall-clock gate."""
    return source_trade_date == today.strftime("%Y%m%d")


def calendar_date_is_open(
    calendar: LocalTradeCalendarProvider, trade_date: str,
) -> bool:
    calendar.health()
    rows = calendar.fetch(trade_date, trade_date)
    if len(rows) != 1 or str(rows[0].get("cal_date") or "") != trade_date:
        raise RuntimeError("local trade-calendar did not return the requested date")
    return str(rows[0].get("is_open") or "0") == "1"


def _open_gap_dates(
    calendar: LocalTradeCalendarProvider,
    *,
    last_complete_date: str,
    today: str,
) -> tuple[str, ...]:
    rows = calendar.fetch(last_complete_date, today)
    return tuple(
        str(row["cal_date"])
        for row in rows
        if last_complete_date < str(row.get("cal_date") or "") < today
        and str(row.get("is_open") or "0") == "1"
    )


def run_recent_daily_gap_fill(
    *,
    today: str,
    run_id: str,
    calendar: LocalTradeCalendarProvider,
    tq: TQWindowsSource,
    repository: WindowsN1PostgresRepository,
) -> RecentGapFillResult:
    last_complete_date = repository.latest_fastlane_complete_date(today)
    if last_complete_date is None:
        return RecentGapFillResult(
            result="NO_FASTLANE_COMPLETION_MARKER",
            last_complete_date=None,
            gap_dates=(),
            dates=(),
        )
    gap_dates = _open_gap_dates(
        calendar,
        last_complete_date=last_complete_date,
        today=today,
    )
    if not gap_dates:
        return RecentGapFillResult(
            result="NO_RECENT_DAILY_GAP",
            last_complete_date=last_complete_date,
            gap_dates=(),
            dates=(),
        )
    scopes = load_tq_scopes(tq)
    results: list[GapDateResult] = []
    for trade_date in gap_dates:
        before_counts = repository.daily_bar_counts(trade_date)
        source_version = f"windows_n1_{trade_date}_{trade_date}_v1"
        gap_result = BootstrapResult(run_id=f"{run_id}_{trade_date}")
        batch_result = persist_daily_bars_batched(
            start_date=trade_date,
            end_date=trade_date,
            source_version=source_version,
            run_id=f"{run_id}_{trade_date}",
            scopes=scopes,
            tq=tq,
            repository=repository,
            result=gap_result,
        )
        after_counts = repository.daily_bar_counts(trade_date)
        results.append(GapDateResult(
            trade_date=trade_date,
            source_version=source_version,
            before_counts=before_counts,
            after_counts=after_counts,
            written_rows={
                key: int(value)
                for key, value in batch_result["row_counts"].items()
            },
            batch_counts={
                key: int(value)
                for key, value in batch_result["batch_counts"].items()
            },
            source_counts=batch_result["source_counts"],
        ))
    return RecentGapFillResult(
        result="RECENT_DAILY_GAP_FILL_COMPLETE",
        last_complete_date=last_complete_date,
        gap_dates=gap_dates,
        dates=tuple(results),
    )


# Preserve the previous internal import while replacing coverage scanning with
# explicit completion-marker gap filling.
run_recent_stock_daily_gap_fill = run_recent_daily_gap_fill
