# N5 20260608 Old System Normal Action Parity Oracle Review

result: PARITY_ORACLE_REVIEW_PASS
classification: ActionExecuted_7_not_acceptable_as_old_system_normal_action_parity

## Old Oracle Summary

```json
{
  "excel_path": "/Users/chuanfuchen/Desktop/普通买卖动作_20260608.xlsx",
  "old_action_rows": 734,
  "unique_monitored_objects": 141,
  "unique_identity_direction_condition_period": 171,
  "by_signal": {
    "S_SELL": 527,
    "B_BUY": 207
  },
  "by_monitor_type": {
    "stock_board": 469,
    "stock": 197,
    "index": 67,
    "stock_sell": 1
  },
  "by_asset_kind": {
    "board": 469,
    "stock": 198,
    "index": 67
  },
  "by_trigger_period": {
    "D": 466,
    "W": 135,
    "M": 96,
    "Y": 37
  },
  "by_condition_key_top20": {
    "SELL:Y,Q,D": 176,
    "SELL:Y,D": 133,
    "SELL:Y,Q,M,W,D": 101,
    "BUY:FULL": 56,
    "BUY:W": 47,
    "BUY:M,W,D": 37,
    "BUY:D": 31,
    "BUY:W,D": 27,
    "SELL:Y,Q,M,D": 22,
    "SELL:Y,Q,W": 18,
    "SELL:M,W,D": 17,
    "SELL:Y,M,W,D": 14,
    "SELL:Q,W,D": 10,
    "SELL:FULL": 9,
    "SELL:Y,Q,W,D": 8,
    "SELL:Y,W": 7,
    "SELL:Y,W,D": 6,
    "SELL:Q,M,W,D": 5,
    "BUY:M,W": 5,
    "BUY:M": 2
  },
  "trigger_date_distribution": {
    "20260608": 505,
    "20260604": 138,
    "20260605": 90,
    "20260603": 1
  },
  "trigger_time_top20": {
    "09:31": 76,
    "13:42": 21,
    "09:34": 20,
    "13:45": 16,
    "13:30": 16,
    "13:37": 15,
    "09:35": 15,
    "13:16": 13,
    "09:47": 13,
    "13:39": 11,
    "13:44": 10,
    "11:26": 10,
    "13:20": 10,
    "13:12": 10,
    "13:09": 10,
    "13:32": 9,
    "14:26": 8,
    "13:18": 8,
    "11:24": 8,
    "09:46": 8
  }
}
```

## v3 Summary

```json
{
  "n4_run_id": "trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry",
  "n5_run_id": "action_consumer_execute_20260608_until_1500_scoped_coverage_repair_additive__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_formal_snapshot_fallback_retry",
  "n4_trigger_match_rows": 556,
  "n4_trigger_state_rows": 556,
  "n4_trigger_state_by_status": {
    "matched": 556
  },
  "n4_match_by_signal": {
    "B_BUY": 415,
    "S_SELL": 141
  },
  "n4_match_by_asset_kind": {
    "stock": 412,
    "board": 84,
    "index": 60
  },
  "n4_match_by_condition_key_top20": {
    "BUY_HINT": 116,
    "BUY:Y,Q,M,W,D": 53,
    "BUY:Q,M,W,D": 26,
    "SELL:Y,Q,D": 23,
    "BUY:Y,Q,M,W": 22,
    "SELL:Y,D": 21,
    "BUY:W,D": 19,
    "BUY:W": 19,
    "BUY:Q,W,D": 18,
    "SELL:Y,Q,M,W": 16,
    "BUY:Q,D": 15,
    "BUY:Y,Q,W": 12,
    "BUY:Q,M,W": 12,
    "SELL:Y,Q,M,W,D": 11,
    "BUY:Q": 11,
    "BUY:Y,Q,D": 10,
    "SELL:Y,Q,M": 10,
    "BUY:Q,W": 10,
    "SELL:Y,Q": 9,
    "BUY:M,W,D": 9
  },
  "n4_outbox": [
    {
      "event_type": "TriggerMatched",
      "status": "pending",
      "rows": 556
    }
  ],
  "n5_action_fact_rows": 556,
  "n5_event_rows": 556,
  "n5_action_by_state": {
    "blocked": 549,
    "executed": 7
  },
  "n5_event_by_type": {
    "ActionBlocked": 549,
    "ActionExecuted": 7
  },
  "n5_fact_by_asset_kind": {
    "stock": 412,
    "board": 84,
    "index": 60
  },
  "n5_outbox": [
    {
      "event_type": "ActionBlocked",
      "status": "pending",
      "rows": 549
    },
    {
      "event_type": "ActionExecuted",
      "status": "pending",
      "rows": 7
    }
  ],
  "n4_trigger_time_top30": {
    "09:44": 236,
    "09:45": 185,
    "15:00": 81,
    "09:43": 28,
    "09:46": 23,
    "14:59": 3
  },
  "n5_trigger_time_top30": {
    "09:44": 236,
    "09:45": 185,
    "15:00": 81,
    "09:43": 28,
    "09:46": 23,
    "14:59": 3
  }
}
```

## Row-Grain Parity

```json
{
  "old_rows_with_v3_n4_match_multiset": 40,
  "old_rows_missing_v3_n4_match_multiset": 694,
  "old_rows_with_v3_n5_any_multiset": 40,
  "old_rows_with_v3_n5_executed_multiset": 0,
  "old_rows_with_v3_n5_blocked_multiset": 40,
  "old_unique_key_classification": {
    "missing_in_v3_n4": 131,
    "has_n5_blocked": 40
  },
  "by_asset_kind_classification": [
    {
      "asset_kind": "board",
      "classification": "has_n5_blocked",
      "old_rows": 256
    },
    {
      "asset_kind": "board",
      "classification": "missing_in_v3_n4",
      "old_rows": 213
    },
    {
      "asset_kind": "index",
      "classification": "has_n5_blocked",
      "old_rows": 9
    },
    {
      "asset_kind": "index",
      "classification": "missing_in_v3_n4",
      "old_rows": 58
    },
    {
      "asset_kind": "stock",
      "classification": "has_n5_blocked",
      "old_rows": 24
    },
    {
      "asset_kind": "stock",
      "classification": "missing_in_v3_n4",
      "old_rows": 174
    }
  ],
  "sample_missing_in_v3_n4": [
    {
      "asset_kind": "index",
      "identity_key": "index:SH:000001",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,W,D",
      "trigger_period": "D",
      "old_rows": 3,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "index",
      "identity_key": "index:SH:000001",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,D",
      "trigger_period": "D",
      "old_rows": 5,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "index",
      "identity_key": "index:SH:000016",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,D",
      "trigger_period": "D",
      "old_rows": 6,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "index",
      "identity_key": "index:SH:000300",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,W,D",
      "trigger_period": "D",
      "old_rows": 2,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "index",
      "identity_key": "index:SH:000300",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,D",
      "trigger_period": "D",
      "old_rows": 5,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "index",
      "identity_key": "index:SH:000688",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,D",
      "trigger_period": "D",
      "old_rows": 11,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "index",
      "identity_key": "index:SH:000852",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,W,D",
      "trigger_period": "D",
      "old_rows": 3,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "index",
      "identity_key": "index:SH:000852",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,D",
      "trigger_period": "D",
      "old_rows": 4,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "index",
      "identity_key": "index:SH:000905",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,W,D",
      "trigger_period": "D",
      "old_rows": 2,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "index",
      "identity_key": "index:SH:000905",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,D",
      "trigger_period": "D",
      "old_rows": 7,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "index",
      "identity_key": "index:SZ:399001",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,W,D",
      "trigger_period": "D",
      "old_rows": 4,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "index",
      "identity_key": "index:SZ:399006",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,W,D",
      "trigger_period": "D",
      "old_rows": 3,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "index",
      "identity_key": "index:SZ:399303",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,W,D",
      "trigger_period": "D",
      "old_rows": 2,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881034",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,W,D",
      "trigger_period": "D",
      "old_rows": 8,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881078",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,D",
      "trigger_period": "D",
      "old_rows": 13,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881091",
      "direction": "sell",
      "condition_key": "SELL:Y,D",
      "trigger_period": "D",
      "old_rows": 10,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881104",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,W,D",
      "trigger_period": "D",
      "old_rows": 3,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881111",
      "direction": "sell",
      "condition_key": "SELL:Y,W",
      "trigger_period": "W",
      "old_rows": 7,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881136",
      "direction": "sell",
      "condition_key": "SELL:Q,W,D",
      "trigger_period": "W",
      "old_rows": 10,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881171",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,W,D",
      "trigger_period": "D",
      "old_rows": 3,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881171",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,D",
      "trigger_period": "D",
      "old_rows": 5,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881198",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,W,D",
      "trigger_period": "W",
      "old_rows": 1,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881231",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,D",
      "trigger_period": "D",
      "old_rows": 9,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881234",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,D",
      "trigger_period": "D",
      "old_rows": 17,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881241",
      "direction": "sell",
      "condition_key": "SELL:Y,D",
      "trigger_period": "D",
      "old_rows": 12,
      "v3_n4_match_rows": 0,
      "v3_n5_rows": 0,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 0,
      "classification": "missing_in_v3_n4"
    }
  ],
  "sample_has_n5_blocked": [
    {
      "asset_kind": "index",
      "identity_key": "index:SZ:399001",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,D",
      "trigger_period": "D",
      "old_rows": 3,
      "v3_n4_match_rows": 1,
      "v3_n5_rows": 1,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 1,
      "classification": "has_n5_blocked"
    },
    {
      "asset_kind": "index",
      "identity_key": "index:SZ:399006",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,D",
      "trigger_period": "D",
      "old_rows": 2,
      "v3_n4_match_rows": 1,
      "v3_n5_rows": 1,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 1,
      "classification": "has_n5_blocked"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881016",
      "direction": "sell",
      "condition_key": "SELL:M,W,D",
      "trigger_period": "M",
      "old_rows": 17,
      "v3_n4_match_rows": 1,
      "v3_n5_rows": 1,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 1,
      "classification": "has_n5_blocked"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881026",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,W,D",
      "trigger_period": "M",
      "old_rows": 20,
      "v3_n4_match_rows": 1,
      "v3_n5_rows": 1,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 1,
      "classification": "has_n5_blocked"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881044",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,W,D",
      "trigger_period": "W",
      "old_rows": 1,
      "v3_n4_match_rows": 1,
      "v3_n5_rows": 1,
      "v3_n5_executed_rows": 0,
      "v3_n5_blocked_rows": 1,
      "classification": "has_n5_blocked"
    },
    {
      "asset_kind": "board",
      "identity_key": "board:TDX:881082",
      "direction": "sell",
      "condition_key": "SELL:Y,Q,M,W,D",
      "trigger_period": "M",
      "old_rows": 5,
      "v3_n4_match_rows": 1,
```

## N5 Gap Diagnosis

```json
{
  "blocked_reason_distribution": {
    "price_confirmation_failed": 535,
    "amount_confirmation_failed": 14
  },
  "false_flag_distribution": {
    "buy_1m_amount_pass": 231,
    "buy_1m_price_pass": 258,
    "buy_5m_amount_pass": 359,
    "buy_5m_price_pass": 267,
    "buy_120m_price_pass": 324,
    "buy_30m_price_pass": 256,
    "sell_5m_price_pass": 134,
    "sell_1m_amount_pass": 105,
    "sell_1m_price_pass": 63,
    "sell_120m_price_pass": 35,
    "sell_30m_price_pass": 84,
    "sell_5m_amount_pass": 28
  },
  "false_flag_by_direction": {
    "buy": {
      "buy_1m_amount_pass": 231,
      "buy_1m_price_pass": 258,
      "buy_5m_amount_pass": 359,
      "buy_5m_price_pass": 267,
      "buy_120m_price_pass": 324,
      "buy_30m_price_pass": 256
    },
    "sell": {
      "sell_5m_price_pass": 134,
      "sell_1m_amount_pass": 105,
      "sell_1m_price_pass": 63,
      "sell_120m_price_pass": 35,
      "sell_30m_price_pass": 84,
      "sell_5m_amount_pass": 28
    }
  },
  "false_flag_combo_top20": [
    {
      "false_flags": [
        "buy_120m_price_pass",
        "buy_1m_amount_pass",
        "buy_1m_price_pass",
        "buy_30m_price_pass",
        "buy_5m_amount_pass",
        "buy_5m_price_pass"
      ],
      "rows": 73
    },
    {
      "false_flags": [
        "buy_120m_price_pass",
        "buy_1m_price_pass",
        "buy_30m_price_pass",
        "buy_5m_amount_pass",
        "buy_5m_price_pass"
      ],
      "rows": 44
    },
    {
      "false_flags": [
        "buy_120m_price_pass",
        "buy_30m_price_pass",
        "buy_5m_amount_pass"
      ],
      "rows": 31
    },
    {
      "false_flags": [
        "buy_1m_amount_pass",
        "buy_1m_price_pass",
        "buy_5m_amount_pass",
        "buy_5m_price_pass"
      ],
      "rows": 30
    },
    {
      "false_flags": [
        "buy_120m_price_pass",
        "buy_1m_amount_pass",
        "buy_30m_price_pass",
        "buy_5m_amount_pass"
      ],
      "rows": 27
    },
    {
      "false_flags": [
        "buy_120m_price_pass",
        "buy_1m_amount_pass",
        "buy_30m_price_pass",
        "buy_5m_amount_pass",
        "buy_5m_price_pass"
      ],
      "rows": 23
    },
    {
      "false_flags": [
        "sell_5m_price_pass"
      ],
      "rows": 18
    },
    {
      "false_flags": [
        "buy_1m_price_pass",
        "buy_5m_amount_pass",
        "buy_5m_price_pass"
      ],
      "rows": 17
    },
    {
      "false_flags": [
        "buy_120m_price_pass",
        "buy_30m_price_pass",
        "buy_5m_amount_pass",
        "buy_5m_price_pass"
      ],
      "rows": 17
    },
    {
      "false_flags": [
        "sell_1m_amount_pass",
        "sell_1m_price_pass",
        "sell_30m_price_pass",
        "sell_5m_price_pass"
      ],
      "rows": 17
    },
    {
      "false_flags": [
        "buy_120m_price_pass",
        "buy_1m_amount_pass",
        "buy_1m_price_pass",
        "buy_5m_amount_pass",
        "buy_5m_price_pass"
      ],
      "rows": 16
    },
    {
      "false_flags": [
        "sell_1m_amount_pass",
        "sell_30m_price_pass",
        "sell_5m_price_pass"
      ],
      "rows": 15
    },
    {
      "false_flags": [
        "sell_1m_amount_pass",
        "sell_5m_price_pass"
      ],
      "rows": 14
    },
    {
      "false_flags": [
        "sell_120m_price_pass",
        "sell_1m_amount_pass",
        "sell_1m_price_pass",
        "sell_30m_price_pass",
        "sell_5m_price_pass"
      ],
      "rows": 13
    },
    {
      "false_flags": [
        "buy_120m_price_pass",
        "buy_1m_amount_pass",
        "buy_1m_price_pass",
        "buy_30m_price_pass",
        "buy_5m_amount_pass"
      ],
      "rows": 12
    },
    {
      "false_flags": [
        "sell_1m_price_pass",
        "sell_5m_price_pass"
      ],
      "rows": 12
    },
    {
      "false_flags": [
        "buy_120m_price_pass",
        "buy_1m_price_pass",
        "buy_5m_amount_pass",
        "buy_5m_price_pass"
      ],
      "rows": 11
    },
    {
      "false_flags": [
        "buy_120m_price_pass",
        "buy_5m_amount_pass"
      ],
      "rows": 10
    },
    {
      "false_flags": [
        "sell_1m_amount_pass",
        "sell_30m_price_pass",
        "sell_5m_amount_pass",
        "sell_5m_price_pass"
      ],
      "rows": 10
    },
    {
      "false_flags": [
        "buy_120m_price_pass",
        "buy_1m_price_pass",
        "buy_30m_price_pass",
        "buy_5m_amount_pass"
      ],
      "rows": 7
    }
  ],
  "passed_flag_count_distribution_for_blocked": {
    "2": 145,
    "3": 107,
    "0": 78,
    "1": 125,
    "4": 56,
    "5": 38
  },
  "metric_alignment_status_distribution": {
    "aligned": 556
  },
  "metric_minute_top30": {
    "09:44": 236,
    "09:45": 185,
    "15:00": 81,
    "09:43": 28,
    "09:46": 23,
    "14:59": 3
  },
  "executed_rows": [
    {
      "asset_kind": "stock",
      "identity_key": "stock:SZ:300489",
      "direction": "buy",
      "condition_key": "BUY_HINT",
      "trigger_period": "30m",
      "trigger_time": "2026-06-08 09:44:00+08:00",
      "action_mark": "30m_volume",
      "metric_time": "2026-06-08T09:44:00+08:00",
      "metric_minute_label": "09:44",
      "flags": {
        "buy_1m_price_pass": true,
        "buy_5m_price_pass": true,
        "buy_1m_amount_pass": true,
        "buy_30m_price_pass": true,
        "buy_5m_amount_pass": true,
        "buy_120m_price_pass": true
      }
    },
    {
      "asset_kind": "stock",
      "identity_key": "stock:SH:603626",
      "direction": "buy",
      "condition_key": "BUY:M,W,D",
      "trigger_period": "D",
      "trigger_time": "2026-06-08 09:45:03.273538+08:00",
      "action_mark": "normal",
      "metric_time": "2026-06-08T09:45:00+08:00",
      "metric_minute_label": "09:45",
      "flags": {
        "buy_1m_price_pass": true,
        "buy_5m_price_pass": true,
        "buy_1m_amount_pass": true,
        "buy_30m_price_pass": true,
        "buy_5m_amount_pass": true,
        "buy_120m_price_pass": true
      }
    },
    {
      "asset_kind": "stock",
      "identity_key": "stock:SH:605016",
      "direction": "buy",
      "condition_key": "BUY:Q,M,W,D",
      "trigger_period": "D",
      "trigger_time": "2026-06-08 09:45:06.661403+08:00",
      "action_mark": "normal",
      "metric_time": "2026-06-08T09:45:00+08:00",
      "metric_minute_label": "09:45",
      "flags": {
        "buy_1m_price_pass": true,
        "buy_5m_price_pass": true,
        "buy_1m_amount_pass": true,
        "buy_30m_price_pass": true,
        "buy_5m_amount_pass": true,
        "buy_120m_price_pass": true
      }
    },
    {
      "asset_kind": "stock",
      "identity_key": "stock:SZ:000429",
      "direction": "buy",
      "condition_key": "BUY:Y,Q,W,D",
      "trigger_period": "Q",
      "trigger_time": "2026-06-08 09:45:24.054250+08:00",
      "action_mark": "normal",
      "metric_time": "2026-06-08T09:45:00+08:00",
      "metric_minute_label": "09:45",
      "flags": {
        "buy_1m_price_pass": true,
        "buy_5m_price_pass": true,
        "buy_1m_amount_pass": true,
        "buy_30m_price_pass": true,
        "buy_5m_amount_pass": true,
        "buy_120m_price_pass": true
      }
    },
    {
      "asset_kind": "stock",
      "identity_key": "stock:SZ:000738",
      "direction": "buy",
      "condition_key": "BUY:Y,Q,M,W,D",
      "trigger_period": "D",
      "trigger_time": "2026-06-08 09:45:27.250453+08:00",
      "action_mark": "normal",
      "metric_time": "2026-06-08T09:45:00+08:00",
      "metric_minute_label": "09:45",
      "flags": {
        "buy_1m_price_pass": true,
        "buy_5m_price_pass": true,
        "buy_1m_amount_pass": true,
        "buy_30m_price_pass": true,
        "buy_5m_amount_pass": true,
        "buy_120m_price_pass": true
      }
    },
    {
      "asset_kind": "stock",
      "identity_key": "stock:SZ:002046",
      "direction": "buy",
      "condition_key": "BUY:Q,W,D",
      "trigger_period": "Q",
      "trigger_time": "2026-06-08 09:45:33.528961+08:00",
      "action_mark": "normal",
      "metric_time": "2026-06-08T09:45:00+08:00",
      "metric_minute_label": "09:45",
      "flags": {
        "buy_1m_price_pass": true,
        "buy_5m_price_pass": true,
        "buy_1m_amount_pass": true,
        "buy_30m_price_pass": true,
        "buy_5m_amount_pass": true,
        "buy_120m_price_pass": true
      }
    },
    {
      "asset_kind": "index",
      "identity_key": "index:SZ:399319",
      "direction": "sell",
      "condition_key": "SELL:Y,Q",
      "trigger_period": "Q",
      "trigger_time": "2026-06-08 09:44:25.346313+08:00",
      "action_mark": "normal",
      "metric_time": "2026-06-08T09:44:00+08:00",
      "metric_minute_label": "09:44",
      "flags": {
        "sell_1m_price_pass": true,
        "sell_5m_price_pass": true,
        "sell_1m_amount_pass": true,
        "sell_30m_price_pass": true,
        "sell_5m_amount_pass": true,
        "sell_120m_price_pass": true
      }
    }
  ]
}
```

## Decision

```json
{
  "action_executed_7_acceptable": false,
  "old_action_best_current_mapping": "closer_to_N4_TriggerMatched_or_N5_ActionExecuted_under_old_target_machine_semantics; unresolved, requires rule parity decision",
  "primary_blockers": [
    "N4 TriggerMatched coverage 556 is below old ordinary action rows 734 and old row-grain overlap only partial",
    "N5 unified rule currently requires all 120m/30m/5m/1m price/amount flags, causing 549/556 blocked",
    "old target machine ordinary action semantics may correspond to trigger/live action row rather than v3 all-period ActionExecuted; this must be decided before final closeout"
  ],
  "recommended_next_gate": "N5_20260608_OLD_SYSTEM_ACTION_RULE_PARITY_REPAIR_CONTRACT_GATE"
}
```

## Forbidden Scope Proof

```json
{
  "old_system_db_read": false,
  "db_write": false,
  "rollback_executed": false,
  "n3_n4_n5_n6_execute": false,
  "outbox_consumed_or_updated": false,
  "worker_started": false,
  "real_trade": false
}
```
