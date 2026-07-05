"""Dry-run stock ingestion pipeline.

This module wires raw stock rows into standardized v3 rows and quality gates.
It deliberately does not call external services, connect PostgreSQL, or write
files; callers inject a source object that supplies raw rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from ashare_v3.ingestion.common import (
    QualityGateResult,
    make_source_batch_id,
    require_yyyymmdd,
    stable_raw_hash,
)
from ashare_v3.ingestion.stock import (
    gate_identity_key_coverage,
    gate_no_board_codes_in_stock,
    gate_official_daily_proof,
    gate_stock_universe_alignment,
    normalize_stock_daily_bar_row,
    normalize_stock_daily_basic_row,
    normalize_stock_identity_row,
)


class StockRawSource(Protocol):
    """Interface for stock raw data providers."""

    def fetch_stock_basic(self, *, asof_date: str) -> Sequence[Mapping[str, Any]]:
        """Return raw stock identity rows."""

    def fetch_stock_daily_qfq(self, *, start_date: str, end_date: str) -> Sequence[Mapping[str, Any]]:
        """Return raw qfq stock daily bar rows."""

    def fetch_stock_daily_basic(self, *, start_date: str, end_date: str) -> Sequence[Mapping[str, Any]]:
        """Return raw Tushare daily_basic rows."""

    def fetch_stock_official_daily_proof_keys(self, *, start_date: str, end_date: str) -> set[tuple[str, str]]:
        """Return `(ts_code, trade_date)` keys that passed official daily proof."""


@dataclass(frozen=True)
class StockIngestionDryRun:
    start_date: str
    end_date: str
    source_version: str
    batches: dict[str, str]
    raw_hashes: dict[str, str]
    stock_identity_rows: list[dict[str, Any]]
    stock_daily_bar_rows: list[dict[str, Any]]
    stock_daily_basic_rows: list[dict[str, Any]]
    quality_gates: list[QualityGateResult]

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.quality_gates)

    def summary(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "source_version": self.source_version,
            "batches": self.batches,
            "raw_hashes": self.raw_hashes,
            "row_counts": {
                "stock_identity": len(self.stock_identity_rows),
                "stock_daily_bar_fact": len(self.stock_daily_bar_rows),
                "stock_daily_basic": len(self.stock_daily_basic_rows),
            },
            "quality_gates": [
                {
                    "gate_name": gate.gate_name,
                    "status": gate.status,
                    "severity": gate.severity,
                    "expected_value": gate.expected_value,
                    "actual_value": gate.actual_value,
                    "details": dict(gate.details or {}),
                }
                for gate in self.quality_gates
            ],
            "passed": self.passed,
            "will_connect_database": False,
            "will_write_data_files": False,
        }


def run_stock_ingestion_dry_run(
    source: StockRawSource,
    *,
    start_date: str,
    end_date: str,
    version: str = "v1",
) -> StockIngestionDryRun:
    require_yyyymmdd(start_date, "start_date")
    require_yyyymmdd(end_date, "end_date")
    if start_date > end_date:
        raise ValueError("start_date must be <= end_date")

    period = f"{start_date}_{end_date}"
    batches = {
        "stock_identity": make_source_batch_id("stock_identity", end_date, version),
        "stock_daily_bar_fact": make_source_batch_id("stock_daily", period, version),
        "stock_daily_basic": make_source_batch_id("stock_daily_basic", period, version),
    }
    source_versions = {
        "stock_identity": batches["stock_identity"],
        "stock_daily_bar_fact": make_source_batch_id("stock_daily", period, version),
        "stock_daily_basic": make_source_batch_id("stock_daily_basic", period, version),
    }

    raw_identity = list(source.fetch_stock_basic(asof_date=end_date))
    raw_daily_qfq = list(source.fetch_stock_daily_qfq(start_date=start_date, end_date=end_date))
    raw_daily_basic = list(source.fetch_stock_daily_basic(start_date=start_date, end_date=end_date))
    proof_keys = source.fetch_stock_official_daily_proof_keys(start_date=start_date, end_date=end_date)

    stock_identity_rows = [
        normalize_stock_identity_row(
            row,
            source="tushare.stock_basic",
            source_batch_id=batches["stock_identity"],
            source_version=source_versions["stock_identity"],
        )
        for row in raw_identity
    ]
    stock_daily_bar_rows = [
        normalize_stock_daily_bar_row(
            row,
            source="tushare.pro_bar",
            source_batch_id=batches["stock_daily_bar_fact"],
            source_version=source_versions["stock_daily_bar_fact"],
            official_daily_proof=(str(row.get("ts_code")), str(row.get("trade_date"))) in proof_keys,
        )
        for row in raw_daily_qfq
    ]
    stock_daily_basic_rows = [
        normalize_stock_daily_basic_row(
            row,
            source="tushare.daily_basic",
            source_batch_id=batches["stock_daily_basic"],
            source_version=source_versions["stock_daily_basic"],
        )
        for row in raw_daily_basic
    ]

    quality_gates = [
        gate_identity_key_coverage(stock_identity_rows),
        gate_identity_key_coverage(stock_daily_bar_rows),
        gate_identity_key_coverage(stock_daily_basic_rows),
        gate_no_board_codes_in_stock(stock_identity_rows),
        gate_no_board_codes_in_stock(stock_daily_bar_rows),
        gate_no_board_codes_in_stock(stock_daily_basic_rows),
        gate_official_daily_proof(stock_daily_bar_rows),
        gate_stock_universe_alignment(stock_daily_bar_rows, stock_identity_rows),
        gate_stock_universe_alignment(stock_daily_basic_rows, stock_identity_rows),
    ]

    return StockIngestionDryRun(
        start_date=start_date,
        end_date=end_date,
        source_version=version,
        batches=batches,
        raw_hashes={
            "stock_identity": stable_raw_hash(raw_identity),
            "stock_daily_bar_fact": stable_raw_hash(raw_daily_qfq),
            "stock_daily_basic": stable_raw_hash(raw_daily_basic),
        },
        stock_identity_rows=stock_identity_rows,
        stock_daily_bar_rows=stock_daily_bar_rows,
        stock_daily_basic_rows=stock_daily_basic_rows,
        quality_gates=quality_gates,
    )
