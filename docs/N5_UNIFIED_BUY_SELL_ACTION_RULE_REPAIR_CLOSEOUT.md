# N5 Unified Buy/Sell Action Rule Repair Closeout

Status: BLOCKED

```text
classification=BLOCKED
blocker=trigger_time_aligned_n3_action_confirmation_metric_rows_missing_and_ordinary_formal_n4_evidence_not_available_in_20260608_b2_projection
n4_run_id=trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry
n3_metric_run_id=action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry
```

## Root Cause

- RC1: N4 ordinary formal BUY/SELL path is repaired in code, but 20260608 B2 projection inputs lack v4 formal enrichment; read-only repaired N4 dry-run has ordinary_formal_matched_count=0 and ordinary_formal_pending_count=4219.
- RC2: N5 HINT special-case was not the direct root; repaired N5 now sends BUY_HINT/SELL_HINT provenance through the same canonical metric-aware B_BUY/S_SELL rule.
- RC3: Existing N3 metrics are not trigger-time aligned; deterministic v2 join coverage=0/122 and all missing samples are metric_time_mismatch.

## Read-Only Final Distributions

N4 repaired dry-run summary:

```json
{
  "bj_920xxx_not_ready_object_count": 0,
  "board_not_ready_object_count": 127,
  "buy_hint_matched_count": 116,
  "by_asset_kind": {
    "board": 267,
    "index": 169,
    "stock": 4241
  },
  "by_direction": {
    "buy": 2371,
    "sell": 2306
  },
  "by_legacy_signal_type": {
    "BUY_HINT": 218,
    "B_BUY_30M_VOL": 2153,
    "SELL_HINT": 154,
    "S_SELL_30M_SHRINK": 2152
  },
  "by_projection_signal_status": {
    "down_volume_expanding": 120,
    "down_volume_flat": 72,
    "down_volume_shrinking": 36,
    "flat": 42,
    "unknown": 3561,
    "up_volume_expanding": 591,
    "up_volume_flat": 201,
    "up_volume_shrinking": 54
  },
  "by_signal_type": {
    "B_BUY": 2371,
    "S_SELL": 2306
  },
  "by_trigger_mark_candidate": {
    "30m_shrink": 6,
    "30m_volume": 116,
    "normal": 4555
  },
  "candidate_count": 4677,
  "canonical_payload_invalid_count": 0,
  "matched_by_asset_kind": {
    "board": 3,
    "index": 6,
    "stock": 113
  },
  "matched_by_direction": {
    "buy": 116,
    "sell": 6
  },
  "matched_by_legacy_signal_type": {
    "BUY_HINT": 116,
    "SELL_HINT": 6
  },
  "matched_by_projection_signal_status": {
    "down_volume_shrinking": 6,
    "up_volume_expanding": 116
  },
  "matched_by_signal_type": {
    "B_BUY": 116,
    "S_SELL": 6
  },
  "matched_by_trigger_mark_candidate": {
    "30m_shrink": 6,
    "30m_volume": 116
  },
  "matched_count": 122,
  "matched_output_event_types": {
    "TriggerMatched": 122
  },
  "not_matched_by_projection_signal_status": {
    "down_volume_expanding": 40,
    "down_volume_flat": 24,
    "down_volume_shrinking": 6,
    "flat": 14,
    "unknown": 86,
    "up_volume_expanding": 81,
    "up_volume_flat": 67,
    "up_volume_shrinking": 18
  },
  "not_matched_signal_count": 336,
  "not_ready_candidate_count": 4219,
  "pending_by_asset_kind": {
    "board": 250,
    "index": 163,
    "stock": 3806
  },
  "pending_by_direction": {
    "buy": 2106,
    "sell": 2113
  },
  "pending_by_legacy_signal_type": {
    "B_BUY_30M_VOL": 2106,
    "S_SELL_30M_SHRINK": 2113
  },
  "pending_by_not_ready_classification": {
    "blocked": 4219
  },
  "pending_by_projection_signal_status": {
    "down_volume_expanding": 80,
    "down_volume_flat": 48,
    "down_volume_shrinking": 24,
    "flat": 28,
    "unknown": 3475,
    "up_volume_expanding": 394,
    "up_volume_flat": 134,
    "up_volume_shrinking": 36
  },
  "pending_by_signal_type": {
    "B_BUY": 2106,
    "S_SELL": 2113
  },
  "pending_by_trigger_mark_candidate": {
    "normal": 4219
  },
  "pending_count": 4219,
  "pending_output_event_types": {
    "TriggerPendingMarketData": 4219
  },
  "ready_candidate_count": 1116,
  "sell_hint_matched_count": 6,
  "trigger_period_distribution": {
    "": 4555,
    "30m": 122
  }
}
```

N5 repaired read-only probe:

```json
{
  "candidate_action_state_distribution": {
    "blocked": 3892
  },
  "candidate_blocked_reason_distribution": {
    "": 3770,
    "metric_missing": 122
  },
  "candidate_event_type_distribution": {
    "": 3770,
    "ActionBlocked": 122
  },
  "candidate_final_action_mark_distribution": {
    "": 3892
  },
  "candidate_metric_required_distribution": {
    "": 3770,
    "True": 122
  },
  "candidate_metric_status_distribution": {
    "missing": 122,
    "not_required": 3770
  },
  "deterministic_join_summary": {
    "by_asset_kind": {
      "board": {
        "joined_n4_rows": 0,
        "metric_rows": 3,
        "missing_n4_rows": 3,
        "n4_trigger_matched_rows": 3
      },
      "index": {
        "joined_n4_rows": 0,
        "metric_rows": 6,
        "missing_n4_rows": 6,
        "n4_trigger_matched_rows": 6
      },
      "stock": {
        "joined_n4_rows": 0,
        "metric_rows": 113,
        "missing_n4_rows": 113,
        "n4_trigger_matched_rows": 113
      }
    },
    "coverage": "0/122",
    "duplicate_join_key_count": 0,
    "duplicate_join_key_rows": 0,
    "duplicate_join_keys_sample": {},
    "join_key": [
      "source_trigger_match_id/source_trigger_event_id",
      "asset_kind",
      "identity_key",
      "direction",
      "condition_key",
      "trigger_time/metric_time",
      "trade_date/for_trade_date",
      "action_metric_run_id"
    ],
    "join_policy": "deterministic_v2_trigger_row_time_action_metric_run",
    "joined_n4_rows": 0,
    "metric_rows": 122,
    "metric_run_id": "action_confirmation_metric_20260608_until_1500__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry",
    "missing_n4_rows": 122,
    "missing_sample": [
      {
        "event_id": "evt_0012573d10b230d21a97055d78e72c1ef95c0e8b",
        "join_key": [
          "board",
          "board:TDX:881373",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128206",
        "trigger_time": "2026-06-08T14:59:00+08:00"
      },
      {
        "event_id": "evt_c4f1b9939bbd840ea3a169a68e2ddf36d85e1aca",
        "join_key": [
          "board",
          "board:TDX:881410",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128207",
        "trigger_time": "2026-06-08T14:59:00+08:00"
      },
      {
        "event_id": "evt_17585ac83d9632d179c54235896f89b512d0661e",
        "join_key": [
          "board",
          "board:TDX:881436",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128208",
        "trigger_time": "2026-06-08T14:59:00+08:00"
      },
      {
        "event_id": "evt_e57355b176ecdec7c81104d1aefb16bd71d6910b",
        "join_key": [
          "index",
          "index:SH:000001",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128200",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_6486c401b2de9311d9267e09f481d106959347f9",
        "join_key": [
          "index",
          "index:SH:000300",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128201",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_d93edf5cb1f1919f75f4988dc12f41a45f47a315",
        "join_key": [
          "index",
          "index:SH:000688",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128202",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_bc78c30381c041b72e05989fc91f69b418d6da08",
        "join_key": [
          "index",
          "index:SH:000905",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128203",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_638a273a9d736e88a294e2074431b127a9526b50",
        "join_key": [
          "index",
          "index:SZ:399001",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128204",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_28efc8cb32fdd32de64fb88e10eed2fee07c5eaf",
        "join_key": [
          "index",
          "index:SZ:399006",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128205",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_7146555449acdcd0ef4afcda3e2b89f56ced3c2c",
        "join_key": [
          "stock",
          "stock:SH:600150",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128087",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_53a37165f33c6df233003753e553f9a8168fb199",
        "join_key": [
          "stock",
          "stock:SH:600176",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128088",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_4a4a8ced00bf07d6606df1f5d131c399b9aeef83",
        "join_key": [
          "stock",
          "stock:SH:600323",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128089",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_982d8baec2dd3c0fb03d9e2cfd13bddc77e3955c",
        "join_key": [
          "stock",
          "stock:SH:600330",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128090",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_64e9f058c051b07ee9d8bec05b23a76a437beac3",
        "join_key": [
          "stock",
          "stock:SH:600641",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128091",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_38957ca8824826ce63775cba29149cecb663cf7e",
        "join_key": [
          "stock",
          "stock:SH:600901",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128092",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_44b45f9c422a09514982edbb7b8765739450c85c",
        "join_key": [
          "stock",
          "stock:SH:600961",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128093",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_9edbb14845881d2351b8c2e86b73083ad170504c",
        "join_key": [
          "stock",
          "stock:SH:600988",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128094",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_d0af3773fbd8e3e00a57c2990d46b09b4edb97bc",
        "join_key": [
          "stock",
          "stock:SH:600999",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128095",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_be31293d49cc374ff3857ed78cc03e875b1276bb",
        "join_key": [
          "stock",
          "stock:SH:601066",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128096",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      },
      {
        "event_id": "evt_b7f28f5282212a5a4de789fd5427b9a191f693af",
        "join_key": [
          "stock",
          "stock:SH:601088",
          "20260608"
        ],
        "reason": "metric_time_mismatch",
        "source_trigger_match_id": "128097",
        "trigger_time": "2026-06-08T09:43:00+08:00"
      }
    ],
    "n4_trigger_matched_rows": 122,
    "payload_metric_id_rows": 0
  },
  "input_metric_rows": 122,
  "input_n4_outbox_rows": 3892,
  "trigger_matched_candidate_samples": [
    {
      "action_confirmation_metric_required": true,
      "action_confirmation_metric_status": "missing",
      "action_event_type": "ActionBlocked",
      "action_state": "blocked",
      "blocked_reason": "metric_missing",
      "condition_key": "SELL_HINT",
      "confirmation_source": "n3_action_confirmation_metric_missing",
      "final_action_mark": null,
      "signal_type": "S_SELL",
      "trigger_period": "30m",
      "trigger_time": "2026-06-08T14:59:00+08:00"
    },
    {
      "action_confirmation_metric_required": true,
      "action_confirmation_metric_status": "missing",
      "action_event_type": "ActionBlocked",
      "action_state": "blocked",
      "blocked_reason": "metric_missing",
      "condition_key": "SELL_HINT",
      "confirmation_source": "n3_action_confirmation_metric_missing",
      "final_action_mark": null,
      "signal_type": "S_SELL",
      "trigger_period": "30m",
      "trigger_time": "2026-06-08T14:59:00+08:00"
    },
    {
      "action_confirmation_metric_required": true,
      "action_confirmation_metric_status": "missing",
      "action_event_type": "ActionBlocked",
      "action_state": "blocked",
      "blocked_reason": "metric_missing",
      "condition_key": "SELL_HINT",
      "confirmation_source": "n3_action_confirmation_metric_missing",
      "final_action_mark": null,
      "signal_type": "S_SELL",
      "trigger_period": "30m",
      "trigger_time": "2026-06-08T14:59:00+08:00"
    },
    {
      "action_confirmation_metric_required": true,
      "action_confirmation_metric_status": "missing",
      "action_event_type": "ActionBlocked",
      "action_state": "blocked",
      "blocked_reason": "metric_missing",
      "condition_key": "BUY_HINT",
      "confirmation_source": "n3_action_confirmation_metric_missing",
      "final_action_mark": null,
      "signal_type": "B_BUY",
      "trigger_period": "30m",
      "trigger_time": "2026-06-08T09:43:00+08:00"
    },
    {
      "action_confirmation_metric_required": true,
      "action_confirmation_metric_status": "missing",
      "action_event_type": "ActionBlocked",
      "action_state": "blocked",
      "blocked_reason": "metric_missing",
      "condition_key": "BUY_HINT",
      "confirmation_source": "n3_action_confirmation_metric_missing",
      "final_action_mark": null,
      "signal_type": "B_BUY",
      "trigger_period": "30m",
      "trigger_time": "2026-06-08T09:43:00+08:00"
    },
    {
      "action_confirmation_metric_required": true,
      "action_confirmation_metric_status": "missing",
      "action_event_type": "ActionBlocked",
      "action_state": "blocked",
      "blocked_reason": "metric_missing",
      "condition_key": "BUY_HINT",
      "confirmation_source": "n3_action_confirmation_metric_missing",
      "final_action_mark": null,
      "signal_type": "B_BUY",
      "trigger_period": "30m",
      "trigger_time": "2026-06-08T09:43:00+08:00"
    },
    {
      "action_confirmation_metric_required": true,
      "action_confirmation_metric_status": "missing",
      "action_event_type": "ActionBlocked",
      "action_state": "blocked",
      "blocked_reason": "metric_missing",
      "condition_key": "BUY_HINT",
      "confirmation_source": "n3_action_confirmation_metric_missing",
      "final_action_mark": null,
      "signal_type": "B_BUY",
      "trigger_period": "30m",
      "trigger_time": "2026-06-08T09:43:00+08:00"
    },
    {
      "action_confirmation_metric_required": true,
      "action_confirmation_metric_status": "missing",
      "action_event_type": "ActionBlocked",
      "action_state": "blocked",
      "blocked_reason": "metric_missing",
      "condition_key": "BUY_HINT",
      "confirmation_source": "n3_action_confirmation_metric_missing",
      "final_action_mark": null,
      "signal_type": "B_BUY",
      "trigger_period": "30m",
      "trigger_time": "2026-06-08T09:43:00+08:00"
    },
    {
      "action_confirmation_metric_required": true,
      "action_confirmation_metric_status": "missing",
      "action_event_type": "ActionBlocked",
      "action_state": "blocked",
      "blocked_reason": "metric_missing",
      "condition_key": "BUY_HINT",
      "confirmation_source": "n3_action_confirmation_metric_missing",
      "final_action_mark": null,
      "signal_type": "B_BUY",
      "trigger_period": "30m",
      "trigger_time": "2026-06-08T09:43:00+08:00"
    },
    {
      "action_confirmation_metric_required": true,
      "action_confirmation_metric_status": "missing",
      "action_event_type": "ActionBlocked",
      "action_state": "blocked",
      "blocked_reason": "metric_missing",
      "condition_key": "BUY_HINT",
      "confirmation_source": "n3_action_confirmation_metric_missing",
      "final_action_mark": null,
      "signal_type": "B_BUY",
      "trigger_period": "30m",
      "trigger_time": "2026-06-08T09:43:00+08:00"
    }
  ]
}
```

Persisted N4 TriggerMatched distribution before rollback:

```json
[
  {
    "asset_kind": "index",
    "c": 6,
    "condition_key": "BUY_HINT",
    "output_event_type": "TriggerMatched",
    "signal_type": "B_BUY",
    "trigger_mark_candidate": "30m_volume",
    "trigger_period": "30m"
  },
  {
    "asset_kind": "stock",
    "c": 110,
    "condition_key": "BUY_HINT",
    "output_event_type": "TriggerMatched",
    "signal_type": "B_BUY",
    "trigger_mark_candidate": "30m_volume",
    "trigger_period": "30m"
  },
  {
    "asset_kind": "board",
    "c": 3,
    "condition_key": "SELL_HINT",
    "output_event_type": "TriggerMatched",
    "signal_type": "S_SELL",
    "trigger_mark_candidate": "30m_shrink",
    "trigger_period": "30m"
  },
  {
    "asset_kind": "stock",
    "c": 3,
    "condition_key": "SELL_HINT",
    "output_event_type": "TriggerMatched",
    "signal_type": "S_SELL",
    "trigger_mark_candidate": "30m_shrink",
    "trigger_period": "30m"
  }
]
```

Persisted N5 distribution before rollback:

```json
[
  {
    "action_mark": null,
    "action_state": "blocked",
    "asset_kind": "index",
    "blocked_reason": "price_confirmation_failed",
    "c": 6,
    "condition_key": "BUY_HINT",
    "confirmation_status": "failed",
    "event_type": "ActionBlocked",
    "payload_blocked_reason": "price_confirmation_failed",
    "signal_type": "B_BUY",
    "trigger_period": "30m"
  },
  {
    "action_mark": null,
    "action_state": "blocked",
    "asset_kind": "stock",
    "blocked_reason": "price_confirmation_failed",
    "c": 110,
    "condition_key": "BUY_HINT",
    "confirmation_status": "failed",
    "event_type": "ActionBlocked",
    "payload_blocked_reason": "price_confirmation_failed",
    "signal_type": "B_BUY",
    "trigger_period": "30m"
  },
  {
    "action_mark": null,
    "action_state": "blocked",
    "asset_kind": "board",
    "blocked_reason": "price_confirmation_failed",
    "c": 3,
    "condition_key": "SELL_HINT",
    "confirmation_status": "failed",
    "event_type": "ActionBlocked",
    "payload_blocked_reason": "price_confirmation_failed",
    "signal_type": "S_SELL",
    "trigger_period": "30m"
  },
  {
    "action_mark": null,
    "action_state": "blocked",
    "asset_kind": "stock",
    "blocked_reason": "price_confirmation_failed",
    "c": 3,
    "condition_key": "SELL_HINT",
    "confirmation_status": "failed",
    "event_type": "ActionBlocked",
    "payload_blocked_reason": "price_confirmation_failed",
    "signal_type": "S_SELL",
    "trigger_period": "30m"
  }
]
```

## Rollback / Rerun

No rollback or write rerun was executed. The scoped chain remains blocked because a write rerun would still lack trigger-time N3 metric proof and ordinary formal N4 evidence.

## Forbidden Scope Proof

```json
{
  "db_writes_by_this_closeout_probe": false,
  "delivery_push_voice_mobile_touched": false,
  "legacy_paths_opened": [],
  "long_worker_started": false,
  "n5_outbox_consumed": false,
  "old_system_db_or_services_touched": false,
  "real_trade_order_position_pnl_touched": false,
  "scoped_outbox_status_counts_read_only": [
    {
      "c": 122,
      "source_run_id": "action_consumer_execute_20260608_until_1500_metric_aware_retry__trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry",
      "status": "pending"
    },
    {
      "c": 3892,
      "source_run_id": "trigger_projection_matcher_execute_20260608_v13_index_all_until_1500_v4_repair_retry",
      "status": "pending"
    }
  ],
  "sim_touched": false
}
```
