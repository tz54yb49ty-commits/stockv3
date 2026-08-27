"""Production stage handlers for the Windows TQ/eltdx N1 bootstrap."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .windows_n1_bootstrap import BootstrapResult, WindowsN1BootstrapConfig, run_security_items
from .windows_n1_postgres import WindowsN1PostgresRepository, stable_rows_hash
from .windows_n1_sources import EltdxWindowsSource, TQWindowsSource, calculate_market_values, normalize_tq_daily_rows


MARKET_BOARD_TYPES = {"11": "tdx_industry", "12": "tdx_concept", "14": "tdx_region"}
MIN_DAILY_BASIC_MARKET_VALUE_COVERAGE = 0.90
TQ_DAILY_BATCH_SIZE = 100


def split_symbol(symbol: str) -> tuple[str, str]:
    code, separator, exchange = symbol.upper().partition(".")
    if not separator or exchange not in {"SH", "SZ", "BJ"} or len(code) != 6 or not code.isdigit():
        raise ValueError(f"invalid exchange-qualified symbol: {symbol}")
    return code, exchange


def normalize_eltdx_code(value: Any) -> str:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    return digits[-6:] if len(digits) >= 6 else digits.zfill(6)


def _value(row: dict[str, Any], *names: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None:
            return value
    return None


def chunked(values: Sequence[str], size: int = TQ_DAILY_BATCH_SIZE) -> tuple[tuple[str, ...], ...]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    return tuple(tuple(values[offset : offset + size]) for offset in range(0, len(values), size))


def load_tq_scopes(tq: TQWindowsSource) -> dict[str, list[dict[str, Any]]]:
    scopes = {market: [] for market in ("5", "9", "11", "12", "14")}
    for row in tq.fetch_market_members():
        market = str(row["market"])
        if market in scopes:
            scopes[market].append(row)
    empty = [market for market, rows in scopes.items() if not rows]
    if empty:
        raise RuntimeError(f"empty TQ market scopes: {empty}")
    return scopes


def finance_report_fingerprint(row: Mapping[str, Any]) -> str:
    normalized = dict(row)
    report_markers = {
        key: normalized.get(key)
        for key in (
            "report_period", "report_date", "end_date",
            "announcement_date", "ann_date", "publish_date",
            "updated_date", "updated_date_raw", "finance_info_raw",
        )
        if normalized.get(key) is not None
    }
    if report_markers:
        return stable_rows_hash([report_markers])
    return stable_rows_hash([{
        "total_revenue": _value(
            normalized, "operating_revenue_yuan", "zhu_ying_shou_ru",
            "zhu_ying_shou_ru_raw_float",
        ),
        "net_profit": _value(
            normalized, "net_profit_yuan", "jing_li_run", "jing_li_run_raw_float",
        ),
        "net_assets": _value(
            normalized, "net_assets_yuan", "jing_zi_chan", "jing_zi_chan_raw_float",
        ),
        "eps": _value(normalized, "eps", "eps_raw"),
        "bps": _value(
            normalized, "book_value_per_share", "mei_gu_jing_zi_chan_raw_float",
        ),
    }])


def persist_daily_bars_batched(
    *,
    start_date: str,
    end_date: str,
    source_version: str,
    run_id: str,
    scopes: Mapping[str, Sequence[Mapping[str, Any]]],
    tq: TQWindowsSource,
    repository: WindowsN1PostgresRepository,
    result: BootstrapResult,
    daily_by_stock: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    if start_date != end_date:
        raise RuntimeError("batched Fastlane daily bars require one trade date")
    row_counts = {
        "stock_daily_bar_fact": 0,
        "index_daily_bar_fact": 0,
        "board_daily_bar_fact": 0,
    }
    expected_keys: dict[str, set[tuple[str, str]]] = {
        table: set() for table in row_counts
    }
    batch_counts = {"requested": 0, "completed": 0, "empty": 0, "failed": 0}
    for market, asset_kind, table in (
        ("5", "stock", "stock_daily_bar_fact"),
        ("9", "index", "index_daily_bar_fact"),
        ("11", "board", "board_daily_bar_fact"),
        ("12", "board", "board_daily_bar_fact"),
        ("14", "board", "board_daily_bar_fact"),
    ):
        raw_by_symbol = {
            str(_value(dict(raw), "Code", "code")): dict(raw)
            for raw in scopes[market]
        }
        symbols = tuple(raw_by_symbol)
        for batch_number, symbol_batch in enumerate(chunked(symbols), start=1):
            batch_counts["requested"] += 1
            batch_id = f"{run_id}_daily_{market}_chunk_{batch_number:03d}"
            try:
                fetched = tq.fetch_daily_batch(
                    symbol_batch,
                    asset_kind=asset_kind,
                    start_date=start_date,
                    end_date=end_date,
                )
                rows: list[dict[str, Any]] = []
                for symbol in symbol_batch:
                    raw_scope = raw_by_symbol[symbol]
                    code, exchange = split_symbol(symbol)
                    name = str(_value(raw_scope, "Name", "name") or symbol)
                    bars = normalize_tq_daily_rows(fetched.get(symbol, []))
                    bars = [
                        bar for bar in bars
                        if start_date <= str(bar.get("trade_date") or "") <= end_date
                    ]
                    if asset_kind == "stock" and daily_by_stock is not None and bars:
                        daily_by_stock[symbol] = bars
                    for bar in bars:
                        common = {
                            **bar,
                            "source": "TQ_HTTP",
                            "source_batch_id": batch_id,
                            "source_version": source_version,
                        }
                        if asset_kind == "stock":
                            rows.append({
                                "stock_identity_key": f"stock:{exchange}:{code}",
                                "ts_code": symbol,
                                "code": code,
                                "exchange": exchange,
                                "name": name,
                                **common,
                                "adjust_type": "qfq",
                                "official_daily_proof": True,
                            })
                        elif asset_kind == "index":
                            common.pop("adj_factor", None)
                            rows.append({
                                "index_identity_key": f"index:{exchange}:{code}",
                                "code": code,
                                "exchange": exchange,
                                "name": name,
                                **common,
                            })
                        else:
                            common.pop("adj_factor", None)
                            rows.append({
                                "board_identity_key": f"board:TDX:{code}",
                                "board_code": code,
                                "board_name": name,
                                "board_type": MARKET_BOARD_TYPES[market],
                                **common,
                            })
                if rows:
                    identity_column = f"{asset_kind}_identity_key"
                    expected_keys[table].update(
                        (str(row[identity_column]), str(row["trade_date"]))
                        for row in rows
                    )
                    repository.persist_batch(
                        table=table,
                        rows=rows,
                        conflict_columns=(f"{asset_kind}_identity_key", "trade_date", "source_version"),
                        batch_id=batch_id,
                        trade_date=end_date,
                        data_domain=asset_kind,
                        data_type=table,
                        source_version=source_version,
                    )
                else:
                    batch_counts["empty"] += 1
                batch_counts["completed"] += 1
            except Exception as error:
                batch_counts["failed"] += 1
                result.security_failures.append({
                    "symbol": f"market:{market}:chunk:{batch_number:03d}",
                    "stage": f"daily_{market}_batch",
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "symbol_count": len(symbol_batch),
                    "other_security_rows_rolled_back": False,
                })
    if batch_counts["failed"]:
        raise RuntimeError(
            f"TQ daily batch failures: {batch_counts['failed']}/{batch_counts['requested']}"
        )
    if not any(row_counts.values()):
        row_counts = {
            table: len(keys) for table, keys in expected_keys.items()
        }
    if not any(row_counts.values()):
        raise RuntimeError("TQ daily batches returned no valid rows")
    source_counts = repository.daily_bar_source_counts(end_date, source_version)
    for asset_kind, table in (
        ("stock", "stock_daily_bar_fact"),
        ("index", "index_daily_bar_fact"),
        ("board", "board_daily_bar_fact"),
    ):
        expected = row_counts[table]
        actual = int(source_counts[asset_kind]["rows"])
        if actual != expected:
            raise RuntimeError(
                f"daily source row-count mismatch: {table} expected={expected} actual={actual}"
            )
    return {
        "row_counts": row_counts,
        "batch_counts": batch_counts,
        "source_counts": source_counts,
    }


@dataclass
class WindowsN1ProductionHandlers:
    config: WindowsN1BootstrapConfig
    tq: TQWindowsSource
    eltdx: EltdxWindowsSource
    repository: WindowsN1PostgresRepository
    daily_mode: bool = False
    scopes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    stock_names: dict[str, str] = field(default_factory=dict)
    daily_by_stock: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    finance_by_stock: dict[str, dict[str, Any]] = field(default_factory=dict)
    row_counts: dict[str, int] = field(default_factory=dict)
    before_n1: dict[str, int] = field(default_factory=dict)
    before_downstream: dict[str, int] = field(default_factory=dict)

    @property
    def version(self) -> str:
        return f"windows_n1_{self.config.start_date}_{self.config.end_date}_v1"

    def handlers(self):
        return {
            "schema": self.schema,
            "scope": self.scope,
            "identity_membership": self.identity_membership,
            "daily_bars": self.daily_bars,
            "eltdx_finance": self.eltdx_finance,
            "daily_basic": self.daily_basic,
            "activate_n1_sources": self.activate_n1_sources,
            "n1_data_ready": self.n1_data_ready,
        }

    def schema(self, _result: BootstrapResult) -> None:
        self.repository.verify_authority()
        self.before_n1 = self.repository.business_row_counts()
        self.before_downstream = self.repository.downstream_row_counts()

    def scope(self, _result: BootstrapResult) -> None:
        self.scopes = load_tq_scopes(self.tq)

    def _identity_rows(self, market: str, batch_id: str) -> tuple[str, list[dict[str, Any]]]:
        rows = []
        if market == "5":
            table = "stock_identity"
            for raw in self.scopes[market]:
                symbol = str(_value(raw, "Code", "code")); code, exchange = split_symbol(symbol)
                name = str(_value(raw, "Name", "name") or symbol)
                self.stock_names[symbol] = name
                rows.append({"stock_identity_key": f"stock:{exchange}:{code}", "ts_code": symbol, "code": code, "exchange": exchange, "name": name, "display_code": symbol, "area": None, "industry": None, "market": "A_STOCK", "listed_date": None, "delisted_date": None, "is_st": "ST" in name.upper(), "status": "active", "source": "TQ_HTTP", "source_batch_id": batch_id, "source_version": self.version, "raw_payload": raw})
        elif market == "9":
            table = "index_identity"
            for raw in self.scopes[market]:
                symbol = str(_value(raw, "Code", "code")); code, exchange = split_symbol(symbol)
                name = str(_value(raw, "Name", "name") or symbol)
                rows.append({"index_identity_key": f"index:{exchange}:{code}", "ts_code": symbol, "code": code, "exchange": exchange, "name": name, "source_namespace": "TQ", "publisher": None, "index_category": "tq_market_9", "base_date": None, "listed_date": None, "status": "active", "source": "TQ_HTTP", "source_batch_id": batch_id, "source_version": self.version, "raw_payload": raw})
        else:
            table = "board_identity"
            for raw in self.scopes[market]:
                symbol = str(_value(raw, "Code", "code")); code, _exchange = split_symbol(symbol)
                name = str(_value(raw, "Name", "name") or symbol)
                rows.append({"board_identity_key": f"board:TDX:{code}", "board_code": code, "board_name": name, "board_type": MARKET_BOARD_TYPES[market], "source_namespace": "TDX", "source_file": None, "status": "active", "source": "TQ_HTTP", "source_batch_id": batch_id, "source_version": self.version, "raw_payload": raw})
        return table, rows

    def identity_membership(self, result: BootstrapResult) -> None:
        for market in ("5", "9", "11", "12", "14"):
            batch_id = f"{result.run_id}_identity_{market}"
            table, rows = self._identity_rows(market, batch_id)
            conflicts = {"stock_identity": ("stock_identity_key",), "index_identity": ("index_identity_key",), "board_identity": ("board_identity_key",)}[table]
            self.repository.persist_batch(table=table, rows=rows, conflict_columns=conflicts, batch_id=batch_id, trade_date=self.config.end_date, data_domain="stock" if market == "5" else "index" if market == "9" else "board", data_type=table, source_version=self.version)
            self.row_counts[table] = self.row_counts.get(table, 0) + len(rows)
        stock_symbols = set(self.stock_names)
        for market in ("9", "11", "12", "14"):
            table = "index_membership_fact" if market == "9" else "board_membership_fact"
            rows = []
            for parent in self.scopes[market]:
                parent_symbol = str(_value(parent, "Code", "code")); parent_code, parent_exchange = split_symbol(parent_symbol)
                parent_name = str(_value(parent, "Name", "name") or parent_symbol)
                for member in self.tq.fetch_sector_members(parent_symbol):
                    member_symbol = str(_value(member, "Code", "code") or member)
                    if member_symbol not in stock_symbols:
                        continue
                    stock_code, stock_exchange = split_symbol(member_symbol)
                    common = {"trade_date": self.config.end_date, "stock_identity_key": f"stock:{stock_exchange}:{stock_code}", "stock_code": stock_code, "stock_name": self.stock_names[member_symbol], "source": "TQ_HTTP", "source_file": None, "source_version": self.version, "raw_payload": member}
                    if market == "9":
                        rows.append({**common, "index_identity_key": f"index:{parent_exchange}:{parent_code}", "index_code": parent_code, "index_name": parent_name})
                    else:
                        rows.append({**common, "board_identity_key": f"board:TDX:{parent_code}", "board_code": parent_code, "board_name": parent_name, "board_type": MARKET_BOARD_TYPES[market]})
            batch_id = f"{result.run_id}_membership_{market}"
            for row in rows: row["source_batch_id"] = batch_id
            conflicts = ("trade_date", "index_identity_key", "stock_identity_key", "source_version") if market == "9" else ("trade_date", "board_identity_key", "stock_identity_key", "source_version")
            self.repository.persist_batch(table=table, rows=rows, conflict_columns=conflicts, batch_id=batch_id, trade_date=self.config.end_date, data_domain="index" if market == "9" else "board", data_type=table, source_version=self.version)
            self.row_counts[table] = self.row_counts.get(table, 0) + len(rows)

    def daily_bars(self, result: BootstrapResult) -> None:
        if self.daily_mode:
            batch_result = persist_daily_bars_batched(
                start_date=self.config.start_date,
                end_date=self.config.end_date,
                source_version=self.version,
                run_id=result.run_id,
                scopes=self.scopes,
                tq=self.tq,
                repository=self.repository,
                result=result,
                daily_by_stock=self.daily_by_stock,
            )
            for table, count in batch_result["row_counts"].items():
                self.row_counts[table] = self.row_counts.get(table, 0) + int(count)
            result.evidence["daily_bar_batches"] = batch_result
            return
        for market, asset_kind, table in (("5", "stock", "stock_daily_bar_fact"), ("9", "index", "index_daily_bar_fact"), ("11", "board", "board_daily_bar_fact"), ("12", "board", "board_daily_bar_fact"), ("14", "board", "board_daily_bar_fact")):
            def worker(symbol: str) -> None:
                raw_scope = next(row for row in self.scopes[market] if str(_value(row, "Code", "code")) == symbol)
                code, exchange = split_symbol(symbol); name = str(_value(raw_scope, "Name", "name") or symbol)
                bars = normalize_tq_daily_rows(self.tq.fetch_daily(symbol, asset_kind=asset_kind, start_date=self.config.start_date, end_date=self.config.end_date))
                if not bars: raise RuntimeError("no valid daily bars")
                batch_id = f"{result.run_id}_daily_{market}_{code}"
                rows = []
                for bar in bars:
                    common = {**bar, "source": "TQ_HTTP", "source_batch_id": batch_id, "source_version": self.version}
                    if asset_kind == "stock":
                        rows.append({"stock_identity_key": f"stock:{exchange}:{code}", "ts_code": symbol, "code": code, "exchange": exchange, "name": name, **common, "adjust_type": "qfq", "official_daily_proof": True})
                    elif asset_kind == "index":
                        common.pop("adj_factor", None); rows.append({"index_identity_key": f"index:{exchange}:{code}", "code": code, "exchange": exchange, "name": name, **common})
                    else:
                        common.pop("adj_factor", None); rows.append({"board_identity_key": f"board:TDX:{code}", "board_code": code, "board_name": name, "board_type": MARKET_BOARD_TYPES[market], **common})
                conflicts = (f"{asset_kind}_identity_key", "trade_date", "source_version")
                self.repository.persist_batch(table=table, rows=rows, conflict_columns=conflicts, batch_id=batch_id, trade_date=self.config.end_date, data_domain=asset_kind, data_type=table, source_version=self.version)
                self.row_counts[table] = self.row_counts.get(table, 0) + len(rows)
                if asset_kind == "stock": self.daily_by_stock[symbol] = bars
            symbols = [str(_value(row, "Code", "code")) for row in self.scopes[market]]
            run_security_items(items=symbols, stage=f"daily_{market}", run_id=result.run_id, artifact_root=self.config.artifact_root, worker=worker, result=result)

    def eltdx_finance(self, result: BootstrapResult) -> None:
        symbols = list(self.stock_names)
        codes = [exchange.lower() + code for code, exchange in map(split_symbol, symbols)]
        finance_rows = self.eltdx.fetch_finance_batch(codes)
        for row in finance_rows:
            code = normalize_eltdx_code(_value(row, "code"))
            if code: self.finance_by_stock[code] = row
        if self.daily_mode:
            previous_payloads = self.repository.latest_stock_finance_payloads()
            pending_rows: list[dict[str, Any]] = []
            refreshed_reports = 0
            reused_reports = 0
            for symbol in symbols:
                try:
                    code, exchange = split_symbol(symbol)
                    base = self.finance_by_stock.get(code)
                    if base is None:
                        raise RuntimeError("finance_batch row missing")
                    previous_payload = previous_payloads.get(code, {})
                    previous_base = previous_payload.get("finance_batch")
                    previous_reports = previous_payload.get("reports")
                    reports: Mapping[str, Any]
                    if (
                        isinstance(previous_base, Mapping)
                        and isinstance(previous_reports, Mapping)
                        and previous_reports
                        and finance_report_fingerprint(base)
                        == finance_report_fingerprint(previous_base)
                    ):
                        reports = previous_reports
                        reused_reports += 1
                    else:
                        reports = self.eltdx.fetch_three_reports(code)
                        if any(not rows for rows in reports.values()):
                            raise RuntimeError("one or more finance reports empty")
                        refreshed_reports += 1
                    total_share = _value(
                        base, "total_shares", "zong_gu_ben", "zongguben",
                        "zong_gu_ben_raw_float",
                    )
                    float_share = _value(
                        base, "circulating_shares", "liu_tong_gu_ben", "liutongguben",
                        "liu_tong_gu_ben_raw_float",
                    )
                    close = self.daily_by_stock.get(symbol, [{}])[-1].get("close")
                    total_mv, circ_mv = calculate_market_values(
                        close=close, total_share=total_share, float_share=float_share,
                    )
                    pending_rows.append({
                        "stock_identity_key": f"stock:{exchange}:{code}",
                        "asof_date": self.config.end_date,
                        "source_trade_date": self.config.end_date,
                        "announcement_date": None,
                        "report_period": None,
                        "ts_code": symbol,
                        "code": code,
                        "exchange": exchange,
                        "roe": None,
                        "revenue_yoy": None,
                        "profit_yoy": None,
                        "total_revenue": _value(
                            base, "operating_revenue_yuan", "zhu_ying_shou_ru",
                            "zhu_ying_shou_ru_raw_float",
                        ),
                        "net_profit": _value(
                            base, "net_profit_yuan", "jing_li_run", "jing_li_run_raw_float",
                        ),
                        "net_assets": _value(
                            base, "net_assets_yuan", "jing_zi_chan", "jing_zi_chan_raw_float",
                        ),
                        "eps": _value(base, "eps", "eps_raw"),
                        "bps": _value(
                            base, "book_value_per_share", "mei_gu_jing_zi_chan_raw_float",
                        ),
                        "pe_core": None,
                        "total_mv": total_mv,
                        "circ_mv": circ_mv,
                        "score": None,
                        "warning": None,
                        "quality_status": "passed",
                        "source": "ELTDX_1_2_0",
                        "source_batch_id": "",
                        "source_version": self.version,
                        "raw_payload": {
                            "finance_batch": base,
                            "reports": reports,
                            "total_share": total_share,
                            "float_share": float_share,
                        },
                    })
                except Exception as error:
                    result.security_failures.append({
                        "symbol": symbol,
                        "stage": "eltdx_finance_daily",
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "other_security_rows_rolled_back": False,
                    })
            for offset in range(0, len(pending_rows), 100):
                rows = pending_rows[offset : offset + 100]
                batch_id = f"{result.run_id}_finance_v3_chunk_{offset // 100 + 1:03d}"
                for row in rows:
                    row["source_batch_id"] = batch_id
                self.repository.persist_batch(
                    table="stock_financial_metrics_fact",
                    rows=rows,
                    conflict_columns=("stock_identity_key", "asof_date", "source_version"),
                    batch_id=batch_id,
                    trade_date=self.config.end_date,
                    data_domain="stock",
                    data_type="stock_financial_metrics_fact",
                    source_version=self.version,
                )
            self.row_counts["stock_financial_metrics_fact"] = len(pending_rows)
            result.evidence["finance_incremental"] = {
                "finance_batch_rows": len(finance_rows),
                "report_refresh_count": refreshed_reports,
                "report_reuse_count": reused_reports,
                "persist_chunk_count": (len(pending_rows) + 99) // 100,
            }
            coverage = len(pending_rows) / max(len(symbols), 1)
            result.finance_gate_passed = coverage >= 0.90
            return
        def worker(symbol: str) -> None:
            code, exchange = split_symbol(symbol)
            base = self.finance_by_stock.get(code)
            if base is None: raise RuntimeError("finance_batch row missing")
            reports = self.eltdx.fetch_three_reports(code)
            if any(not rows for rows in reports.values()): raise RuntimeError("one or more finance reports empty")
            batch_id = f"{result.run_id}_finance_v2_{code}"
            total_share = _value(
                base, "total_shares", "zong_gu_ben", "zongguben", "zong_gu_ben_raw_float"
            )
            float_share = _value(
                base, "circulating_shares", "liu_tong_gu_ben", "liutongguben",
                "liu_tong_gu_ben_raw_float",
            )
            close = self.daily_by_stock.get(symbol, [{}])[-1].get("close")
            total_mv, circ_mv = calculate_market_values(close=close, total_share=total_share, float_share=float_share)
            row = {"stock_identity_key": f"stock:{exchange}:{code}", "asof_date": self.config.end_date, "source_trade_date": self.config.end_date, "announcement_date": None, "report_period": None, "ts_code": symbol, "code": code, "exchange": exchange, "roe": None, "revenue_yoy": None, "profit_yoy": None, "total_revenue": _value(base, "operating_revenue_yuan", "zhu_ying_shou_ru", "zhu_ying_shou_ru_raw_float"), "net_profit": _value(base, "net_profit_yuan", "jing_li_run", "jing_li_run_raw_float"), "net_assets": _value(base, "net_assets_yuan", "jing_zi_chan", "jing_zi_chan_raw_float"), "eps": _value(base, "eps", "eps_raw"), "bps": _value(base, "book_value_per_share", "mei_gu_jing_zi_chan_raw_float"), "pe_core": None, "total_mv": total_mv, "circ_mv": circ_mv, "score": None, "warning": None, "quality_status": "passed", "source": "ELTDX_1_2_0", "source_batch_id": batch_id, "source_version": self.version, "raw_payload": {"finance_batch": base, "reports": reports, "total_share": total_share, "float_share": float_share}}
            self.repository.persist_batch(table="stock_financial_metrics_fact", rows=[row], conflict_columns=("stock_identity_key", "asof_date", "source_version"), batch_id=batch_id, trade_date=self.config.end_date, data_domain="stock", data_type="stock_financial_metrics_fact", source_version=self.version)
            self.row_counts["stock_financial_metrics_fact"] = self.row_counts.get("stock_financial_metrics_fact", 0) + 1
        run_security_items(items=symbols, stage="eltdx_finance", run_id=result.run_id, artifact_root=self.config.artifact_root, worker=worker, result=result)
        coverage = self.row_counts.get("stock_financial_metrics_fact", 0) / max(len(symbols), 1)
        result.finance_gate_passed = coverage >= 0.90

    def daily_basic(self, result: BootstrapResult) -> None:
        if self.daily_mode:
            pending_rows: list[dict[str, Any]] = []
            for symbol in self.stock_names:
                try:
                    code, exchange = split_symbol(symbol)
                    finance = self.finance_by_stock.get(code)
                    if finance is None:
                        raise RuntimeError("finance shares missing")
                    total_share = _value(
                        finance, "total_shares", "zong_gu_ben", "zongguben",
                        "zong_gu_ben_raw_float",
                    )
                    float_share = _value(
                        finance, "circulating_shares", "liu_tong_gu_ben", "liutongguben",
                        "liu_tong_gu_ben_raw_float",
                    )
                    if total_share is None or float_share is None:
                        raise RuntimeError("finance shares missing")
                    bars = self.daily_by_stock.get(symbol, [])
                    for bar in bars:
                        total_mv, circ_mv = calculate_market_values(
                            close=bar["close"], total_share=total_share,
                            float_share=float_share,
                        )
                        pending_rows.append({
                            "stock_identity_key": f"stock:{exchange}:{code}",
                            "trade_date": bar["trade_date"],
                            "ts_code": symbol,
                            "code": code,
                            "exchange": exchange,
                            "close": bar["close"],
                            "turnover_rate": None,
                            "turnover_rate_f": None,
                            "volume_ratio": None,
                            "pe": None,
                            "pe_ttm": None,
                            "pb": None,
                            "ps": None,
                            "ps_ttm": None,
                            "dv_ratio": None,
                            "dv_ttm": None,
                            "total_share": total_share,
                            "float_share": float_share,
                            "free_share": None,
                            "total_mv": total_mv,
                            "circ_mv": circ_mv,
                            "source": "TQ_ELTDX_WINDOWS",
                            "source_batch_id": "",
                            "source_version": self.version,
                            "raw_payload": {
                                "close_source": "TQ_HTTP",
                                "share_source": "ELTDX_1_2_0",
                            },
                        })
                except Exception as error:
                    result.security_failures.append({
                        "symbol": symbol,
                        "stage": "daily_basic_daily",
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "other_security_rows_rolled_back": False,
                    })
            for offset in range(0, len(pending_rows), 100):
                rows = pending_rows[offset : offset + 100]
                batch_id = f"{result.run_id}_daily_basic_v3_chunk_{offset // 100 + 1:03d}"
                for row in rows:
                    row["source_batch_id"] = batch_id
                self.repository.persist_batch(
                    table="stock_daily_basic",
                    rows=rows,
                    conflict_columns=("stock_identity_key", "trade_date", "source_version"),
                    batch_id=batch_id,
                    trade_date=self.config.end_date,
                    data_domain="stock",
                    data_type="stock_daily_basic",
                    source_version=self.version,
                )
            self.row_counts["stock_daily_basic"] = len(pending_rows)
            coverage = len(pending_rows) / max(
                self.row_counts.get("stock_daily_bar_fact", 0), 1,
            )
            if coverage < MIN_DAILY_BASIC_MARKET_VALUE_COVERAGE:
                raise RuntimeError(
                    f"daily-basic market-value coverage below gate: {coverage:.6f}"
                )
            result.evidence["daily_basic_incremental"] = {
                "row_count": len(pending_rows),
                "persist_chunk_count": (len(pending_rows) + 99) // 100,
            }
            return
        def worker(symbol: str) -> None:
            code, exchange = split_symbol(symbol); finance = self.finance_by_stock.get(code)
            if finance is None: raise RuntimeError("finance shares missing")
            total_share = _value(
                finance, "total_shares", "zong_gu_ben", "zongguben", "zong_gu_ben_raw_float"
            )
            float_share = _value(
                finance, "circulating_shares", "liu_tong_gu_ben", "liutongguben",
                "liu_tong_gu_ben_raw_float",
            )
            if total_share is None or float_share is None:
                raise RuntimeError("finance shares missing")
            batch_id = f"{result.run_id}_daily_basic_v2_{code}"; rows = []
            for bar in self.daily_by_stock.get(symbol, []):
                total_mv, circ_mv = calculate_market_values(close=bar["close"], total_share=total_share, float_share=float_share)
                rows.append({"stock_identity_key": f"stock:{exchange}:{code}", "trade_date": bar["trade_date"], "ts_code": symbol, "code": code, "exchange": exchange, "close": bar["close"], "turnover_rate": None, "turnover_rate_f": None, "volume_ratio": None, "pe": None, "pe_ttm": None, "pb": None, "ps": None, "ps_ttm": None, "dv_ratio": None, "dv_ttm": None, "total_share": total_share, "float_share": float_share, "free_share": None, "total_mv": total_mv, "circ_mv": circ_mv, "source": "TQ_ELTDX_WINDOWS", "source_batch_id": batch_id, "source_version": self.version, "raw_payload": {"close_source": "TQ_HTTP", "share_source": "ELTDX_1_2_0"}})
            if not rows: raise RuntimeError("daily rows missing")
            self.repository.persist_batch(table="stock_daily_basic", rows=rows, conflict_columns=("stock_identity_key", "trade_date", "source_version"), batch_id=batch_id, trade_date=self.config.end_date, data_domain="stock", data_type="stock_daily_basic", source_version=self.version)
            self.row_counts["stock_daily_basic"] = self.row_counts.get("stock_daily_basic", 0) + len(rows)
        run_security_items(items=list(self.stock_names), stage="daily_basic", run_id=result.run_id, artifact_root=self.config.artifact_root, worker=worker, result=result)
        daily_basic_rows = self.row_counts.get("stock_daily_basic", 0)
        daily_bar_rows = self.row_counts.get("stock_daily_bar_fact", 0)
        coverage = daily_basic_rows / max(daily_bar_rows, 1)
        if coverage < MIN_DAILY_BASIC_MARKET_VALUE_COVERAGE:
            raise RuntimeError(
                f"daily-basic market-value coverage below gate: {coverage:.6f}"
            )

    def activate_n1_sources(self, result: BootstrapResult) -> None:
        domains = {"stock_identity": "stock", "index_identity": "index", "board_identity": "board", "index_membership_fact": "index", "board_membership_fact": "board", "stock_daily_bar_fact": "stock", "index_daily_bar_fact": "index", "board_daily_bar_fact": "board", "stock_financial_metrics_fact": "stock", "stock_daily_basic": "stock"}
        for data_type, domain in domains.items():
            count = self.row_counts.get(data_type, 0)
            if count <= 0: raise RuntimeError(f"cannot activate empty source: {data_type}")
            revision = "_v2" if data_type in {"stock_financial_metrics_fact", "stock_daily_basic"} else ""
            self.repository.activate_source(data_domain=domain, data_type=data_type, scope_key=self.config.end_date, source_version=self.version, batch_id=f"{result.run_id}_activate_{data_type}{revision}", row_count=count)

    def n1_data_ready(self, result: BootstrapResult) -> None:
        ready_counts = self.repository.assert_n1_data_ready(self.config.end_date)
        after_downstream = self.repository.downstream_row_counts()
        if after_downstream != self.before_downstream:
            raise RuntimeError("N2-N6/downstream row counts changed")
        after_n1 = self.repository.business_row_counts()
        if after_n1.get("common_trade_calendar", 0) != self.before_n1.get("common_trade_calendar", 0):
            raise RuntimeError("common_trade_calendar changed")
        result.evidence.update({
            "n1_ready_counts": ready_counts,
            "n1_before_counts": self.before_n1,
            "n1_after_counts": after_n1,
            "downstream_before_counts": self.before_downstream,
            "downstream_after_counts": after_downstream,
            "common_trade_calendar_delta": after_n1.get("common_trade_calendar", 0) - self.before_n1.get("common_trade_calendar", 0),
            "downstream_delta": 0,
        })
