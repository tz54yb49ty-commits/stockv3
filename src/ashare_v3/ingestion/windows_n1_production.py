"""Production stage handlers for the Windows TQ/eltdx N1 bootstrap."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .windows_n1_bootstrap import BootstrapResult, WindowsN1BootstrapConfig, run_security_items
from .windows_n1_postgres import WindowsN1PostgresRepository
from .windows_n1_sources import EltdxWindowsSource, TQWindowsSource, calculate_market_values, normalize_tq_daily_rows


MARKET_BOARD_TYPES = {"11": "tdx_industry", "12": "tdx_concept", "14": "tdx_region"}


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


@dataclass
class WindowsN1ProductionHandlers:
    config: WindowsN1BootstrapConfig
    tq: TQWindowsSource
    eltdx: EltdxWindowsSource
    repository: WindowsN1PostgresRepository
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
        if self.before_n1.get("common_trade_calendar", 0) != 0:
            raise RuntimeError("calendar external contract requires empty common_trade_calendar")

    def scope(self, _result: BootstrapResult) -> None:
        self.scopes = {market: [] for market in ("5", "9", "11", "12", "14")}
        for row in self.tq.fetch_market_members():
            self.scopes[str(row["market"])].append(row)
        empty = [market for market, rows in self.scopes.items() if not rows]
        if empty:
            raise RuntimeError(f"empty TQ market scopes: {empty}")

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

    def identity_membership(self, _result: BootstrapResult) -> None:
        for market in ("5", "9", "11", "12", "14"):
            batch_id = f"windows_n1_identity_{market}_{self.config.end_date}"
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
            batch_id = f"windows_n1_membership_{market}_{self.config.end_date}"
            for row in rows: row["source_batch_id"] = batch_id
            conflicts = ("trade_date", "index_identity_key", "stock_identity_key", "source_version") if market == "9" else ("trade_date", "board_identity_key", "stock_identity_key", "source_version")
            self.repository.persist_batch(table=table, rows=rows, conflict_columns=conflicts, batch_id=batch_id, trade_date=self.config.end_date, data_domain="index" if market == "9" else "board", data_type=table, source_version=self.version)
            self.row_counts[table] = self.row_counts.get(table, 0) + len(rows)

    def daily_bars(self, result: BootstrapResult) -> None:
        for market, asset_kind, table in (("5", "stock", "stock_daily_bar_fact"), ("9", "index", "index_daily_bar_fact"), ("11", "board", "board_daily_bar_fact"), ("12", "board", "board_daily_bar_fact"), ("14", "board", "board_daily_bar_fact")):
            def worker(symbol: str) -> None:
                raw_scope = next(row for row in self.scopes[market] if str(_value(row, "Code", "code")) == symbol)
                code, exchange = split_symbol(symbol); name = str(_value(raw_scope, "Name", "name") or symbol)
                bars = normalize_tq_daily_rows(self.tq.fetch_daily(symbol, asset_kind=asset_kind, start_date=self.config.start_date, end_date=self.config.end_date))
                if not bars: raise RuntimeError("no valid daily bars")
                batch_id = f"windows_n1_daily_{market}_{code}_{self.config.end_date}"
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
        def worker(symbol: str) -> None:
            code, exchange = split_symbol(symbol)
            base = self.finance_by_stock.get(code)
            if base is None: raise RuntimeError("finance_batch row missing")
            reports = self.eltdx.fetch_three_reports(code)
            if any(not rows for rows in reports.values()): raise RuntimeError("one or more finance reports empty")
            batch_id = f"windows_n1_finance_{code}_{self.config.end_date}"
            total_share = _value(base, "total_shares", "zong_gu_ben", "zongguben")
            float_share = _value(base, "circulating_shares", "liu_tong_gu_ben", "liutongguben")
            close = self.daily_by_stock.get(symbol, [{}])[-1].get("close")
            total_mv, circ_mv = calculate_market_values(close=close, total_share=total_share, float_share=float_share)
            row = {"stock_identity_key": f"stock:{exchange}:{code}", "asof_date": self.config.end_date, "source_trade_date": self.config.end_date, "announcement_date": None, "report_period": None, "ts_code": symbol, "code": code, "exchange": exchange, "roe": None, "revenue_yoy": None, "profit_yoy": None, "total_revenue": _value(base, "operating_revenue_yuan", "zhu_ying_shou_ru"), "net_profit": _value(base, "net_profit_yuan", "jing_li_run"), "net_assets": _value(base, "net_assets_yuan", "jing_zi_chan"), "eps": _value(base, "eps", "eps_raw"), "bps": _value(base, "book_value_per_share"), "pe_core": None, "total_mv": total_mv, "circ_mv": circ_mv, "score": None, "warning": None, "quality_status": "passed", "source": "ELTDX_1_2_0", "source_batch_id": batch_id, "source_version": self.version, "raw_payload": {"finance_batch": base, "reports": reports, "total_share": total_share, "float_share": float_share}}
            self.repository.persist_batch(table="stock_financial_metrics_fact", rows=[row], conflict_columns=("stock_identity_key", "asof_date", "source_version"), batch_id=batch_id, trade_date=self.config.end_date, data_domain="stock", data_type="stock_financial_metrics_fact", source_version=self.version)
            self.row_counts["stock_financial_metrics_fact"] = self.row_counts.get("stock_financial_metrics_fact", 0) + 1
        run_security_items(items=symbols, stage="eltdx_finance", run_id=result.run_id, artifact_root=self.config.artifact_root, worker=worker, result=result)
        coverage = self.row_counts.get("stock_financial_metrics_fact", 0) / max(len(symbols), 1)
        result.finance_gate_passed = coverage >= 0.90

    def daily_basic(self, result: BootstrapResult) -> None:
        def worker(symbol: str) -> None:
            code, exchange = split_symbol(symbol); finance = self.finance_by_stock.get(code)
            if finance is None: raise RuntimeError("finance shares missing")
            total_share = _value(finance, "total_shares", "zong_gu_ben", "zongguben")
            float_share = _value(finance, "circulating_shares", "liu_tong_gu_ben", "liutongguben")
            batch_id = f"windows_n1_daily_basic_{code}_{self.config.end_date}"; rows = []
            for bar in self.daily_by_stock.get(symbol, []):
                total_mv, circ_mv = calculate_market_values(close=bar["close"], total_share=total_share, float_share=float_share)
                rows.append({"stock_identity_key": f"stock:{exchange}:{code}", "trade_date": bar["trade_date"], "ts_code": symbol, "code": code, "exchange": exchange, "close": bar["close"], "turnover_rate": None, "turnover_rate_f": None, "volume_ratio": None, "pe": None, "pe_ttm": None, "pb": None, "ps": None, "ps_ttm": None, "dv_ratio": None, "dv_ttm": None, "total_share": total_share, "float_share": float_share, "free_share": None, "total_mv": total_mv, "circ_mv": circ_mv, "source": "TQ_ELTDX_WINDOWS", "source_batch_id": batch_id, "source_version": self.version, "raw_payload": {"close_source": "TQ_HTTP", "share_source": "ELTDX_1_2_0"}})
            if not rows: raise RuntimeError("daily rows missing")
            self.repository.persist_batch(table="stock_daily_basic", rows=rows, conflict_columns=("stock_identity_key", "trade_date", "source_version"), batch_id=batch_id, trade_date=self.config.end_date, data_domain="stock", data_type="stock_daily_basic", source_version=self.version)
            self.row_counts["stock_daily_basic"] = self.row_counts.get("stock_daily_basic", 0) + len(rows)
        run_security_items(items=list(self.stock_names), stage="daily_basic", run_id=result.run_id, artifact_root=self.config.artifact_root, worker=worker, result=result)

    def activate_n1_sources(self, _result: BootstrapResult) -> None:
        domains = {"stock_identity": "stock", "index_identity": "index", "board_identity": "board", "index_membership_fact": "index", "board_membership_fact": "board", "stock_daily_bar_fact": "stock", "index_daily_bar_fact": "index", "board_daily_bar_fact": "board", "stock_financial_metrics_fact": "stock", "stock_daily_basic": "stock"}
        for data_type, domain in domains.items():
            count = self.row_counts.get(data_type, 0)
            if count <= 0: raise RuntimeError(f"cannot activate empty source: {data_type}")
            self.repository.activate_source(data_domain=domain, data_type=data_type, scope_key=self.config.end_date, source_version=self.version, batch_id=f"windows_n1_activate_{data_type}_{self.config.end_date}", row_count=count)

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
