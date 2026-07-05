# N2-R 000001.SH index_daily 历史修复报告

## 结论

- execute: `True`
- source_trade_date: `20260522`
- new_source_version: `index_daily_20260522_v4`
- previous_active_source_version: `index_daily_20260522_v3`
- row_count_written: `897`
- 000001_history_rows: `817`
- 000001_min_trade_date: `20230103`
- 000001_max_trade_date: `20260522`
- required_history_range: `20230101` - `20260522`
- required_history_trade_days: `817`
- fixed_9_present_on_source_trade_date: `9/9`
- rollback_sql: `/Users/chuanfuchen/Documents/A股监控系统v3/sql/N2_R_index_daily_000001_history_repair_rollback.sql`

## 数据来源

```json
{
  "warehouse_checked": true,
  "warehouse_used": false,
  "history_start_date": "20230101",
  "history_end_date": "20260522",
  "required_trade_date_count": 817,
  "postgres_raw_count": 576,
  "postgres_unique_trade_days": 575,
  "postgres_missing_required_count": 242,
  "postgres_missing_required_sample": [
    "20230103",
    "20230104",
    "20230105",
    "20230106",
    "20230109",
    "20230110",
    "20230111",
    "20230112",
    "20230113",
    "20230116",
    "20230117",
    "20230118",
    "20230119",
    "20230120",
    "20230130",
    "20230131",
    "20230201",
    "20230202",
    "20230203",
    "20230206"
  ],
  "parquet_raw_count": 575,
  "combined_unique_trade_days": 575,
  "missing_required_count": 242,
  "missing_required_sample": [
    "20230103",
    "20230104",
    "20230105",
    "20230106",
    "20230109",
    "20230110",
    "20230111",
    "20230112",
    "20230113",
    "20230116",
    "20230117",
    "20230118",
    "20230119",
    "20230120",
    "20230130",
    "20230131",
    "20230201",
    "20230202",
    "20230203",
    "20230206"
  ],
  "external_pull_required": true,
  "external_fetch_used": true,
  "external_source_summary": {
    "mootdx_raw_count": 800,
    "tushare_raw_count": 817,
    "tushare_fallback_used": true,
    "missing_required_after_mootdx": [
      "20230103",
      "20230104",
      "20230105",
      "20230106",
      "20230109",
      "20230110",
      "20230111",
      "20230112",
      "20230113",
      "20230116",
      "20230117",
      "20230118",
      "20230119",
      "20230120",
      "20230130",
      "20230131",
      "20230201"
    ]
  }
}
```

## 历史窗口

```json
[
  {
    "period": "Y",
    "slot": "seed",
    "start_date": "20240101",
    "end_date": "20241231"
  },
  {
    "period": "Y",
    "slot": "previous",
    "start_date": "20250101",
    "end_date": "20251231"
  },
  {
    "period": "Q",
    "slot": "seed",
    "start_date": "20251001",
    "end_date": "20251231"
  },
  {
    "period": "Q",
    "slot": "previous",
    "start_date": "20260101",
    "end_date": "20260331"
  },
  {
    "period": "Y",
    "slot": "current",
    "start_date": "20260101",
    "end_date": "20260522"
  },
  {
    "period": "M",
    "slot": "seed",
    "start_date": "20260301",
    "end_date": "20260331"
  },
  {
    "period": "M",
    "slot": "previous",
    "start_date": "20260401",
    "end_date": "20260430"
  },
  {
    "period": "Q",
    "slot": "current",
    "start_date": "20260401",
    "end_date": "20260522"
  },
  {
    "period": "M",
    "slot": "current",
    "start_date": "20260501",
    "end_date": "20260522"
  },
  {
    "period": "W",
    "slot": "seed",
    "start_date": "20260504",
    "end_date": "20260510"
  },
  {
    "period": "W",
    "slot": "previous",
    "start_date": "20260511",
    "end_date": "20260517"
  },
  {
    "period": "W",
    "slot": "current",
    "start_date": "20260518",
    "end_date": "20260522"
  },
  {
    "period": "D",
    "slot": "previous",
    "start_date": "20260521",
    "end_date": "20260521"
  },
  {
    "period": "D",
    "slot": "current",
    "start_date": "20260522",
    "end_date": "20260522"
  }
]
```

## 质量闸

- index_daily_000001_history_non_empty: passed (817 / expected >0)
- index_daily_000001_required_history_coverage: passed (817/817 / expected all open dates covered from 20230101 to 20260522)
- index_daily_000001_previous_day_present: passed (True / expected 20260521)
- index_daily_000001_period_window_coverage: passed (0 / expected all N2-R current/previous/seed period windows covered)
- index_daily_000001_ohlc_amount_non_null: passed (0 / expected open/close/amount non-null for 000001 rows)
- index_daily_fixed_core_daily_coverage: passed (0 / expected all fixed core indexes have source_trade_date rows)
- index_daily_current_trade_date_row_count_preserved: passed (81 / expected 81)
- index_daily_unique_key: passed (0 / expected 0 duplicates)
- index_daily_no_88xxxx: passed (0 / expected 0)

## condition source ready

exit_code=0

```text
{
  "source_trade_date": "20260522",
  "passed": true,
  "view_exists": true,
  "required_data_types": [
    "stock_daily",
    "stock_daily_basic",
    "stock_financial",
    "index_daily",
    "index_membership",
    "board_daily",
    "board_membership"
  ],
  "missing_data_types": [],
  "checks": [
    {
      "source_trade_date": "20260522",
      "data_domain": "stock",
      "data_type": "stock_daily",
      "active_source_version": "stock_daily_20260522_v1",
      "source_batch_id": "stock_daily_20260522_v1",
      "activated_at": "2026-05-23T08:34:39.310639+08:00",
      "activated_by": "codex_daily_incremental",
      "active_exists": true,
      "fact": {
        "table_name": "stock_daily_bar_fact",
        "date_column": "trade_date",
        "date_mode": "equal",
        "row_count": 5504,
        "row_count_gt_zero": true,
        "identity_key_column": "stock_identity_key",
        "missing_identity_key_count": 0,
        "identity_key_coverage_100pct": true
      },
      "passed": true,
      "failure_reasons": []
    },
    {
      "source_trade_date": "20260522",
      "data_domain": "stock",
      "data_type": "stock_daily_basic",
      "active_source_version": "stock_daily_basic_20260522_v1",
      "source_batch_id": "stock_daily_basic_20260522_v1",
      "activated_at": "2026-05-23T08:34:41.892901+08:00",
      "activated_by": "codex_daily_incremental",
      "active_exists": true,
      "fact": {
        "table_name": "stock_daily_basic",
        "date_column": "trade_date",
        "date_mode": "equal",
        "row_count": 5504,
        "row_count_gt_zero": true,
        "identity_key_column": "stock_identity_key",
        "missing_identity_key_count": 0,
        "identity_key_coverage_100pct": true
      },
      "passed": true,
      "failure_reasons": []
    },
    {
      "source_trade_date": "20260522",
      "data_domain": "stock",
      "data_type": "stock_financial",
      "active_source_version": "stock_financial_20260522_v2",
      "source_batch_id": "stock_financial_20260522_v2",
      "activated_at": "2026-05-23T10:39:07.708813+08:00",
      "activated_by": "codex_daily_incremental",
      "active_exists": true,
      "fact": {
        "table_name": "stock_financial_metrics_fact",
        "date_column": "source_trade_date",
        "date_mode": "equal",
        "row_count": 5504,
        "row_count_gt_zero": true,
        "identity_key_column": "stock_identity_key",
        "missing_identity_key_count": 0,
        "identity_key_coverage_100pct": true,
        "stock_universe_row_count": 5504,
        "aligned_to_stock_universe": true
      },
      "passed": true,
      "failure_reasons": []
    },
    {
      "source_trade_date": "20260522",
      "data_domain": "index",
      "data_type": "index_daily",
      "active_source_version": "index_daily_20260522_v4",
      "source_batch_id": "index_daily_20260522_v4",
      "activated_at": "2026-05-24T01:16:03.726524+08:00",
      "activated_by": "codex_index_daily_000001_history_repair",
      "active_exists": true,
      "fact": {
        "table_name": "index_daily_bar_fact",
        "date_column": "trade_date",
        "date_mode": "equal",
        "row_count": 81,
        "row_count_gt_zero": true,
        "identity_key_column": "index_identity_key",
        "missing_identity_key_count": 0,
        "identity_key_coverage_100pct": true
      },
      "passed": true,
      "failure_reasons": []
    },
    {
      "source_trade_date": "20260522",
      "data_domain": "index",
      "data_type": "index_membership",
      "active_source_version": "index_membership_20260522_v1",
      "source_batch_id": "index_membership_20260522_v1",
      "activated_at": "2026-05-23T08:34:34.866290+08:00",
      "activated_by": "codex_daily_incremental",
      "active_exists": true,
      "fact": {
        "table_name": "index_membership_fact",
        "date_column": "trade_date",
        "date_mode": "equal",
        "row_count": 12841,
        "row_count_gt_zero": true,
        "identity_key_column": "index_identity_key",
        "missing_identity_key_count": 0,
        "identity_key_coverage_100pct": true
      },
      "passed": true,
      "failure_reasons": []
    },
    {
      "source_trade_date": "20260522",
      "data_domain": "board",
      "data_type": "board_daily",
      "active_source_version": "board_daily_20260522_v1",
      "source_batch_id": "board_daily_20260522_v1",
      "activated_at": "2026-05-23T08:35:03.149986+08:00",
      "activated_by": "codex_daily_incremental",
      "active_exists": true,
      "fact": {
        "table_name": "board_daily_bar_fact",
        "date_column": "trade_date",
        "date_mode": "equal",
        "row_count": 428,
        "row_count_gt_zero": true,
        "identity_key_column": "board_identity_key",
        "missing_identity_key_count": 0,
        "identity_key_coverage_100pct": true
      },
      "passed": true,
      "failure_reasons": []
    },
    {
      "source_trade_date": "20260522",
      "data_domain": "board",
      "data_type": "board_membership",
      "active_source_version": "board_membership_20260522_v1",
      "source_batch_id": "board_membership_20260522_v1",
      "activated_at": "2026-05-23T08:34:35.667958+08:00",
      "activated_by": "codex_daily_incremental",
      "active_exists": true,
      "fact": {
        "table_name": "board_membership_fact",
        "date_column": "trade_date",
        "date_mode": "equal",
        "row_count": 56872,
        "row_count_gt_zero": true,
        "identity_key_column": "board_identity_key",
        "missing_identity_key_count": 0,
        "identity_key_coverage_100pct": true
      },
      "passed": true,
      "failure_reasons": []
    }
  ]
}
```

## 边界

- 未触碰旧系统写入。
- 未进入条件层 overwrite / execute。
- 未进入 N3。
- 未启动 worker。
- 未写 trigger/action/mobile/voice/sim。
