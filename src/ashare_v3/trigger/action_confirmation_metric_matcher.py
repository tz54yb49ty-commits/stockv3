"""N4 action-confirmation metric dry-run/preflight planner.

This module consumes only N3 standard action-confirmation metric facts. It is
read-only by construction: it does not consume outbox rows, write trigger facts,
write inbox/checkpoint rows, pull market data, or assemble raw minute indicators.
"""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Iterator, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from ashare_v3.condition.basis import count_quality_severities, normalize_mapping, quality_item
from ashare_v3.events.ids import stable_hash
from ashare_v3.trigger.canonical_signal import (
    CANONICAL_SIGNAL_TYPES,
    canonical_payload_errors,
    canonicalize_trigger_candidate,
)
from ashare_v3.trigger.context_preflight import ASSET_KINDS, TARGET_CONTEXT_TABLES, normalize_text_array
from ashare_v3.trigger.projection_matcher import fetch_context_rows
from ashare_v3.trigger.query_audit_phase1 import audited_n4_trigger_connect
from ashare_v3.trigger.synthetic_dry_run import build_period_trigger_baseline_trace


DEFAULT_TRIGGER_CONTEXT_RUN_ID = "trigger_context_snapshot_20260602_condition_layer_20260601_source_20260601_v1"
DEFAULT_PROJECTION_RUN_ID = (
    "action_confirmation_projection_metric_20260602_1105__"
    "realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1"
)
DEFAULT_SOURCE_CONDITION_RUN_ID = "condition_layer_20260601_source_20260601_v1"
DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID = "market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1"
DEFAULT_SOURCE_SNAPSHOT_RUN_ID = (
    "realtime_snapshot_20260602_live3_outbox_market_data_subscription_20260602_condition_layer_20260601_source_20260601_v1"
)
DEFAULT_FOR_TRADE_DATE = "20260602"
DEFAULT_JSON_REPORT_PATH = "docs/N4_action_confirmation_metric_dry_run_report.json"
DEFAULT_MARKDOWN_REPORT_PATH = "docs/N4_ACTION_CONFIRMATION_METRIC_DRY_RUN_REPORT.md"
DEFAULT_PREFLIGHT_JSON_PATH = "docs/N4_action_confirmation_metric_execute_preflight.json"
DEFAULT_PREFLIGHT_MARKDOWN_PATH = "docs/N4_ACTION_CONFIRMATION_METRIC_EXECUTE_PREFLIGHT.md"
DEFAULT_EXECUTE_RUN_ID = "trigger_action_confirmation_metric_execute_20260602_1105__condition_layer_20260601_source_20260601_v1"
DEFAULT_EXECUTE_CONTRACT_JSON_PATH = "docs/N4_action_confirmation_metric_business_execute_contract.json"
DEFAULT_EXECUTE_CONTRACT_MARKDOWN_PATH = "docs/N4_ACTION_CONFIRMATION_METRIC_BUSINESS_EXECUTE_CONTRACT.md"
DEFAULT_EXECUTE_FINAL_PREFLIGHT_JSON_PATH = "docs/N4_action_confirmation_metric_business_execute_final_preflight.json"
DEFAULT_EXECUTE_FINAL_PREFLIGHT_MARKDOWN_PATH = "docs/N4_ACTION_CONFIRMATION_METRIC_BUSINESS_EXECUTE_FINAL_PREFLIGHT.md"
DEFAULT_EXECUTE_ROLLBACK_SQL_PATH = "sql/N4_action_confirmation_metric_business_execute_rollback.sql"

ACTION_CONFIRMATION_SCHEMA_VERSION = "n3.action_confirmation_metric.v1"
FORMAL_AMOUNT_PROOF_SCHEMA_VERSION = "n3.action_confirmation_metric.formal_amount_proof.v1"
REALTIME_VIRTUAL_METRIC_SCHEMA_VERSION = "v3.realtime_virtual_metric.writer.contract.v1"
REALTIME_VIRTUAL_METRIC_WRITER_SCHEMA_VERSION = "v3.realtime_virtual_metric.writer.v1"
TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION = "n3.action_confirmation_metric.true_full_day_minute_series.v1"
HISTORICAL_REPLAY_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_SCHEMA_VERSION = (
    "v3.realtime_virtual_metric.writer.contract.v1.historical_replay.formal_amount_chain_unit_proof"
)
ALLOWED_ACTION_CONFIRMATION_SCHEMA_VERSIONS = (
    ACTION_CONFIRMATION_SCHEMA_VERSION,
    FORMAL_AMOUNT_PROOF_SCHEMA_VERSION,
    REALTIME_VIRTUAL_METRIC_SCHEMA_VERSION,
    REALTIME_VIRTUAL_METRIC_WRITER_SCHEMA_VERSION,
    TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION,
    HISTORICAL_REPLAY_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_SCHEMA_VERSION,
)
LATEST_METRIC_BY_IDENTITY_REPLAY_MODE = "latest_metric_by_identity"
FULL_DAY_METRIC_TIME_SERIES_REPLAY_MODE = "full_day_metric_time_series"
TRIGGER_PERIOD = "30m"
FORMAL_PERIOD_PRIORITY = ("Y", "Q", "M", "W", "D")
SOURCE_EVENT_TYPE = "MarketSnapshotUpdated"
ALLOWED_OUTPUT_EVENT_TYPES = ("TriggerMatched", "TriggerStateChanged")
LEGACY_OUTPUT_EVENT_TYPES = ("TriggerPendingMarketData",)
STATE_CHANGE_EVENT_TYPE = "TriggerStateChanged"
LIFECYCLE_STATE_KEY_VERSION = "n4_lifecycle_state_key_v1"
MAX_LIFECYCLE_EVENT_OUTBOX_COUNT = 10_000
METRIC_TABLE_CONFIG = {
    "stock": "stock_action_confirmation_projection_metric",
    "index": "index_action_confirmation_projection_metric",
    "board": "board_action_confirmation_projection_metric",
}
PROJECTION_ENRICHMENT_V4_TABLE_CONFIG = {
    "stock": "stock_projection_enrichment_v4_metric",
    "index": "index_projection_enrichment_v4_metric",
    "board": "board_projection_enrichment_v4_metric",
}
ACTION_CONFIRMATION_METRIC_READ_TABLES = (
    "common_trigger_run",
    *TARGET_CONTEXT_TABLES.values(),
    *METRIC_TABLE_CONFIG.values(),
    *PROJECTION_ENRICHMENT_V4_TABLE_CONFIG.values(),
)
FORBIDDEN_ACTION_CONFIRMATION_METRIC_READ_TABLES = (
    "stock_minute_bar_1m",
    "index_minute_bar_1m",
    "board_minute_bar_1m",
    "stock_realtime_projection_metric",
    "index_realtime_projection_metric",
    "board_realtime_projection_metric",
    "stock_intraday_bar_source",
    "index_intraday_bar_source",
    "board_intraday_bar_source",
)
ROW_COUNT_GUARD_TABLES = (
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "common_trigger_state",
    "common_trigger_match",
    "common_event_outbox",
)
ALLOWED_ACTION_CONFIRMATION_METRIC_EXECUTE_WRITE_TABLES = (
    "common_trigger_run",
    "common_trigger_quality_item",
    "common_trigger_state",
    "common_trigger_match",
    "common_event_outbox",
)
FORBIDDEN_ACTION_CONFIRMATION_METRIC_EXECUTE_WRITE_TABLES = (
    "common_event_inbox",
    "common_event_consumer_checkpoint",
    "N2 condition tables",
    "N3 action-confirmation metric/snapshot/minute/subscription facts",
    "N5/N6/action/user/voice/mobile/sim/position/real-trade tables",
    "worker state",
)
PROJECTION_CANDIDATE_LEGACY_SIGNALS = ("B_BUY_30M_VOL", "BUY_HINT", "S_SELL_30M_SHRINK", "SELL_HINT")
ORDINARY_RUNTIME_SIGNALS = ("B_BUY", "S_SELL")
FORMAL_AMOUNT_SOURCE_KIND = "N3_standard_period_metric"
FORMAL_AMOUNT_UNIT = "yuan"
FORMAL_AMOUNT_UNIT_CONVERSION_POLICY = "formal_amount_chain_thousand_yuan_to_yuan_v1"
FORMAL_AMOUNT_PROOF_V1_UNIT_CONVERSION_POLICY = "stock_thousand_yuan_to_yuan_else_native_yuan_v1"
TRUE_FULL_DAY_MINUTE_SERIES_UNIT_POLICY = "true_full_day_minute_series_yuan_passthrough_v1"
ALLOWED_FORMAL_AMOUNT_UNIT_CONVERSION_POLICIES = (
    FORMAL_AMOUNT_UNIT_CONVERSION_POLICY,
    FORMAL_AMOUNT_PROOF_V1_UNIT_CONVERSION_POLICY,
)
BASELINE_AMOUNT_UNIT_COMPAT_POLICY = "reviewed_n2_trigger_amount_unit_yuan_compat"
FORMAL_AMOUNT_RULE = "attachment_dwmqy_avg_chain"
CALIBRATED_30M_METRIC_POLICY = "previous_day_same_window_elapsed_ratio_v1"
FORMAL_AMOUNT_CHAIN_FIELDS = {
    "D": ("today_virt_amount", "weekly_avg_with_today", "prev_weekly_avg"),
    "W": ("weekly_avg_with_today", "monthly_avg_with_today", "prev_monthly_avg"),
    "M": ("monthly_avg_with_today", "quarterly_avg_with_today", "prev_quarterly_avg"),
    "Q": ("quarterly_avg_with_today", "yearly_avg_with_today", "prev_yearly_avg"),
}
FORMAL_TRANSITION_CURRENT_AMOUNT_FIELDS = {
    "D": "today_virt_amount",
    "W": "weekly_avg_with_today",
    "M": "monthly_avg_with_today",
    "Q": "quarterly_avg_with_today",
    "Y": "yearly_avg_with_today",
}
FORMAL_AMOUNT_PROOF_ALIAS_FIELDS = {
    "today_virt_amount": "current_d_virtual_amount",
    "weekly_avg_with_today": "current_w_virtual_amount",
    "monthly_avg_with_today": "current_m_virtual_amount",
    "quarterly_avg_with_today": "current_q_virtual_amount",
    "yearly_avg_with_today": "current_y_virtual_amount",
}
TRUE_FULL_DAY_FORMAL_AMOUNT_CHAIN_FIELD_ALIASES = {
    "today_virt_amount": "current_d_virtual_amount",
    "weekly_avg_with_today": "current_w_virtual_amount",
    "prev_weekly_avg": "previous_w_amount",
    "monthly_avg_with_today": "current_m_virtual_amount",
    "prev_monthly_avg": "previous_m_amount",
    "quarterly_avg_with_today": "current_q_virtual_amount",
    "prev_quarterly_avg": "previous_q_amount",
    "yearly_avg_with_today": "current_y_virtual_amount",
    "prev_yearly_avg": "previous_y_amount",
}
FORMAL_AMOUNT_PROOF_V1_FIELD_PERIOD = {
    "today_virt_amount": ("D", "current"),
    "weekly_avg_with_today": ("W", "current_avg"),
    "prev_weekly_avg": ("W", "previous_avg"),
    "monthly_avg_with_today": ("M", "current_avg"),
    "prev_monthly_avg": ("M", "previous_avg"),
    "quarterly_avg_with_today": ("Q", "current_avg"),
    "prev_quarterly_avg": ("Q", "previous_avg"),
    "yearly_avg_with_today": ("Y", "current_avg"),
    "prev_yearly_avg": ("Y", "previous_avg"),
}
FORMAL_TRANSITION_PREVIOUS_AMOUNT_FIELDS = {
    "D": ("previous_avg_amount", "previous_amount", "previous_amount_baseline", "classification_previous_amount_baseline"),
    "W": ("previous_avg_amount", "previous_amount", "previous_amount_baseline", "classification_previous_amount_baseline"),
    "M": ("previous_avg_amount", "previous_amount", "previous_amount_baseline", "classification_previous_amount_baseline"),
    "Q": ("previous_avg_amount", "previous_amount", "previous_amount_baseline", "classification_previous_amount_baseline"),
    "Y": ("previous_avg_amount", "previous_amount", "previous_amount_baseline", "classification_previous_amount_baseline"),
}
N2_PREVIOUS_TRANSITION_AMOUNT_FIELDS = (
    "previous_avg_amount",
    "previous_amount",
    "previous_amount_baseline",
    "classification_previous_amount_baseline",
)
N2_FORBIDDEN_TRANSITION_AMOUNT_FIELDS = (
    "trigger_previous_amount_baseline",
    "current_amount_seed",
    "current_avg_amount_seed",
    "current_amount_total_seed",
)
N2_AMOUNT_UNIT_CONVERSION_POLICY = "n2_period_trigger_baseline_thousand_yuan_to_yuan_v1"
N2_AMOUNT_UNIT_PASSTHROUGH_POLICY = "n2_period_trigger_baseline_yuan_passthrough_v1"
N2_BASELINE_AMOUNT_UNIT_SOURCE_POLICY = "explicit_asset_kind_rule"
N2_BASELINE_AMOUNT_UNIT_BY_ASSET_KIND = {
    "stock": "thousand_yuan",
    "index": FORMAL_AMOUNT_UNIT,
    "board": FORMAL_AMOUNT_UNIT,
}
FORMAL_BUY_TARGET_TRANSITION = "volume_up"
FORMAL_SELL_TARGET_TRANSITION = "low_volume_down"
_LOCAL_CACHE_KEY = "__n4_action_confirmation_metric_matcher_cache__"
_DEFER_HEAVY_TRACE_KEY = "__n4_defer_heavy_trace__"


def run_action_confirmation_metric_dry_run(
    *,
    dsn: str,
    trigger_context_run_id: str = DEFAULT_TRIGGER_CONTEXT_RUN_ID,
    projection_run_id: str = DEFAULT_PROJECTION_RUN_ID,
    source_condition_run_id: str = DEFAULT_SOURCE_CONDITION_RUN_ID,
    source_subscription_run_id: str = DEFAULT_SOURCE_SUBSCRIPTION_RUN_ID,
    source_snapshot_run_id: str = DEFAULT_SOURCE_SNAPSHOT_RUN_ID,
    for_trade_date: str = DEFAULT_FOR_TRADE_DATE,
    json_report_path: str = DEFAULT_JSON_REPORT_PATH,
    markdown_report_path: str = DEFAULT_MARKDOWN_REPORT_PATH,
    preflight_json_path: str = DEFAULT_PREFLIGHT_JSON_PATH,
    preflight_markdown_path: str = DEFAULT_PREFLIGHT_MARKDOWN_PATH,
    sample_limit: int = 80,
) -> tuple[dict[str, Any], dict[str, Any]]:
    before_counts = capture_row_counts(dsn)
    context_rows, trigger_run = fetch_context_rows(dsn, trigger_context_run_id)
    schema_counts = fetch_action_confirmation_metric_schema_counts(
        dsn,
        projection_run_id=projection_run_id,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=source_subscription_run_id,
        source_snapshot_run_id=source_snapshot_run_id,
        for_trade_date=for_trade_date,
    )
    if schema_counts.get(TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION):
        report = build_action_confirmation_metric_true_full_day_streaming_report(
            dsn=dsn,
            trigger_context_run_id=trigger_context_run_id,
            projection_run_id=projection_run_id,
            source_condition_run_id=source_condition_run_id,
            source_subscription_run_id=source_subscription_run_id,
            source_snapshot_run_id=source_snapshot_run_id,
            for_trade_date=for_trade_date,
            trigger_run=trigger_run,
            context_rows=context_rows,
            before_row_counts=before_counts,
            sample_limit=sample_limit,
        )
        preflight = build_action_confirmation_metric_preflight_report(report)
        write_json(json_report_path, report)
        write_text(markdown_report_path, format_action_confirmation_metric_report(report))
        write_json(preflight_json_path, preflight)
        write_text(preflight_markdown_path, format_action_confirmation_metric_preflight(preflight))
        return report, preflight
    metric_rows = fetch_action_confirmation_metric_rows(
        dsn,
        projection_run_id=projection_run_id,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=source_subscription_run_id,
        source_snapshot_run_id=source_snapshot_run_id,
        for_trade_date=for_trade_date,
    )
    after_counts = capture_row_counts(dsn)
    report = build_action_confirmation_metric_dry_run_report(
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=source_subscription_run_id,
        source_snapshot_run_id=source_snapshot_run_id,
        for_trade_date=for_trade_date,
        trigger_run=trigger_run,
        context_rows=context_rows,
        metric_rows=metric_rows,
        before_row_counts=before_counts,
        after_row_counts=after_counts,
        sample_limit=sample_limit,
    )
    preflight = build_action_confirmation_metric_preflight_report(report)
    write_json(json_report_path, report)
    write_text(markdown_report_path, format_action_confirmation_metric_report(report))
    write_json(preflight_json_path, preflight)
    write_text(preflight_markdown_path, format_action_confirmation_metric_preflight(preflight))
    return report, preflight


def fetch_action_confirmation_metric_rows(
    dsn: str,
    *,
    projection_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    for_trade_date: str,
) -> list[dict[str, Any]]:
    """Fetch N3 metric rows for N4 planning.

    True full-day minute replay is high-cardinality, so it must not hydrate the
    full raw/trace/source-ref JSON for every metric minute. N4 only needs the
    canonical proof blocks for matching; emitted rows hydrate trace later.
    """
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_action_confirmation_metric_fetch_rows",
        source_run_id=projection_run_id,
        readonly_expected=True,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        rows: list[dict[str, Any]] = []
        for asset_kind in ASSET_KINDS:
            table_name = METRIC_TABLE_CONFIG[asset_kind]
            cur.execute(
                true_full_day_minimal_metric_select_sql(table_name),
                (
                    projection_run_id,
                    source_condition_run_id,
                    source_subscription_run_id,
                    source_snapshot_run_id,
                    TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION,
                    for_trade_date,
                ),
            )
            rows.extend(normalize_metric_row(row) for row in cur.fetchall())
            cur.execute(
                f"""
                SELECT action_confirmation_metric_id, projection_run_id, projection_schema_version,
                       source_condition_run_id, source_subscription_run_id, source_snapshot_run_id,
                       source_snapshot_id, source_snapshot_event_id,
                       source_today_minute_run_id, source_previous_day_minute_run_id,
                       for_trade_date, trade_date, asset_kind, identity_key, exchange, code,
                       display_code, name, metric_time, metric_minute_label,
                       current_price, current_price_source, current_price_time,
                       previous_120m_body_high, previous_120m_body_low,
                       previous_30m_body_high, previous_30m_body_low,
                       previous_5m_body_high, previous_5m_body_low,
                       previous_1m_body_high, previous_1m_body_low,
                       current_1m_amount, previous_1m_amount,
                       current_5m_virtual_amount, previous_5m_full_amount,
                       current_30m_virtual_amount,
                       previous_day_same_window_amount,
                       previous_30m_full_amount,
                       current_d_body_high, current_d_body_low, current_d_virtual_amount,
                       current_w_body_high, current_w_body_low, current_w_virtual_amount,
                       current_m_body_high, current_m_body_low, current_m_virtual_amount,
                       current_q_body_high, current_q_body_low, current_q_virtual_amount,
                       current_y_body_high, current_y_body_low, current_y_virtual_amount,
                       is_first_1m_of_day, is_first_5m_of_day,
                       is_first_30m_of_day, is_first_120m_of_day,
                       first_1m_amount_default_pass, first_5m_amount_default_pass,
                       previous_1m_period_source, previous_5m_period_source,
                       previous_30m_period_source, previous_120m_period_source,
                       boundary_policy_version,
                       buy_120m_price_pass, buy_30m_price_pass,
                       buy_5m_price_pass, buy_5m_amount_pass,
                       buy_1m_price_pass, buy_1m_amount_pass,
                       sell_120m_price_pass, sell_30m_price_pass,
                       sell_5m_price_pass, sell_5m_amount_pass,
                       sell_1m_price_pass, sell_1m_amount_pass,
                       metric_quality_status, metric_ready,
                       source_fact_ids, source_minute_refs, previous_day_minute_refs,
                       calculation_config_hash, raw_json, trace_json, created_at
                FROM {table_name}
                WHERE projection_run_id = %s
                  AND source_condition_run_id = %s
                  AND source_subscription_run_id = %s
                  AND projection_schema_version <> %s
                  AND (
                      source_snapshot_run_id = %s
                      OR projection_schema_version = %s
                  )
                  AND for_trade_date = %s
                ORDER BY identity_key, metric_time DESC, action_confirmation_metric_id
                """,
                (
                    projection_run_id,
                    source_condition_run_id,
                    source_subscription_run_id,
                    TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION,
                    source_snapshot_run_id,
                    HISTORICAL_REPLAY_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_SCHEMA_VERSION,
                    for_trade_date,
                ),
            )
            rows.extend(normalize_metric_row(row) for row in cur.fetchall())
        return rows


def fetch_projection_enrichment_v4_quality_visible_rows(
    dsn: str,
    *,
    projection_run_id: str,
    source_trigger_context_run_id: str,
    for_trade_date: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_projection_enrichment_v4_quality_visible_fetch_rows",
        source_run_id=projection_run_id,
        readonly_expected=True,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        for asset_kind in ASSET_KINDS:
            table_name = PROJECTION_ENRICHMENT_V4_TABLE_CONFIG[asset_kind]
            cur.execute(
                f"""
                SELECT projection_enrichment_id, projection_run_id,
                       source_trigger_context_run_id, source_trigger_context_id,
                       for_trade_date, trade_date, asset_kind, identity_key,
                       direction, condition_key, source_freshness_status,
                       metric_ready, metric_quality_status, quality_visible,
                       quality_reason, created_at
                FROM {table_name}
                WHERE projection_run_id = %s
                  AND source_trigger_context_run_id = %s
                  AND for_trade_date = %s
                  AND quality_visible IS TRUE
                  AND metric_ready IS FALSE
                  AND metric_quality_status = 'missing'
                  AND source_freshness_status = 'source_minute_missing_quality_visible'
                ORDER BY identity_key, condition_key, direction, projection_enrichment_id
                """,
                (projection_run_id, source_trigger_context_run_id, for_trade_date),
            )
            for row in cur.fetchall():
                item = dict(row)
                item["asset_kind"] = asset_kind
                rows.append(item)
    return rows


def fetch_action_confirmation_metric_schema_counts(
    dsn: str,
    *,
    projection_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    for_trade_date: str,
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_action_confirmation_metric_schema_counts",
        source_run_id=projection_run_id,
        readonly_expected=True,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        for asset_kind in ASSET_KINDS:
            table_name = METRIC_TABLE_CONFIG[asset_kind]
            cur.execute(
                f"""
                SELECT projection_schema_version, count(*) AS row_count
                FROM {table_name}
                WHERE projection_run_id = %s
                  AND source_condition_run_id = %s
                  AND source_subscription_run_id = %s
                  AND for_trade_date = %s
                  AND (
                      (projection_schema_version = %s AND source_snapshot_run_id = %s)
                      OR (
                          projection_schema_version IS DISTINCT FROM %s
                          AND (
                              source_snapshot_run_id = %s
                              OR projection_schema_version = %s
                          )
                      )
                  )
                GROUP BY projection_schema_version
                """,
                (
                    projection_run_id,
                    source_condition_run_id,
                    source_subscription_run_id,
                    for_trade_date,
                    TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION,
                    source_snapshot_run_id,
                    TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION,
                    source_snapshot_run_id,
                    HISTORICAL_REPLAY_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_SCHEMA_VERSION,
                ),
            )
            for row in cur.fetchall():
                counts[str(row.get("projection_schema_version") or ACTION_CONFIRMATION_SCHEMA_VERSION)] += int(
                    row.get("row_count") or 0
                )
    return dict(counts)


def iter_true_full_day_metric_identity_groups(
    dsn: str,
    *,
    projection_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    for_trade_date: str,
) -> Iterator[tuple[tuple[str, str], list[dict[str, Any]]]]:
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_action_confirmation_metric_true_full_day_stream",
        source_run_id=projection_run_id,
        readonly_expected=True,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn:
        for asset_kind in ASSET_KINDS:
            table_name = METRIC_TABLE_CONFIG[asset_kind]
            current_key: tuple[str, str] | None = None
            current_rows: list[dict[str, Any]] = []
            with conn.cursor(name=f"n4_true_full_day_{asset_kind}") as cur:
                cur.arraysize = 5000
                cur.execute(
                    true_full_day_minimal_metric_select_sql(table_name, ordered=True),
                    (
                        projection_run_id,
                        source_condition_run_id,
                        source_subscription_run_id,
                        source_snapshot_run_id,
                        TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION,
                        for_trade_date,
                    ),
                )
                while True:
                    batch = cur.fetchmany(5000)
                    if not batch:
                        break
                    for row in batch:
                        metric = normalize_metric_row(row)
                        key = (str(metric.get("asset_kind") or ""), str(metric.get("identity_key") or ""))
                        if current_key is not None and key != current_key:
                            yield current_key, current_rows
                            current_rows = []
                        current_key = key
                        current_rows.append(metric)
            if current_key is not None:
                yield current_key, current_rows


def true_full_day_minimal_metric_select_sql(table_name: str, *, ordered: bool = False) -> str:
    order_clause = (
        "ORDER BY identity_key, metric_time, metric_minute_label, action_confirmation_metric_id"
        if ordered
        else ""
    )
    return f"""
                SELECT action_confirmation_metric_id, projection_run_id, projection_schema_version,
                       source_condition_run_id, source_subscription_run_id, source_snapshot_run_id,
                       source_snapshot_id, source_snapshot_event_id,
                       source_today_minute_run_id, source_previous_day_minute_run_id,
                       for_trade_date, trade_date, asset_kind, identity_key, exchange, code,
                       display_code, name, metric_time, metric_minute_label,
                       current_price, current_price_source, current_price_time,
                       current_30m_virtual_amount,
                       previous_day_same_window_amount,
                       previous_30m_full_amount,
                       buy_30m_price_pass,
                       sell_30m_price_pass,
                       metric_quality_status, metric_ready,
                       NULL::jsonb AS source_fact_ids,
                       NULL::jsonb AS source_minute_refs,
                       NULL::jsonb AS previous_day_minute_refs,
                       calculation_config_hash,
                       raw_json ->> 'condition_key' AS condition_key,
                       raw_json ->> 'signal_type' AS signal_type,
                       raw_json -> 'full_scope_condition_rows' AS full_scope_condition_rows,
                       NULL::jsonb AS formal_period_amount_proof,
                       NULL::jsonb AS formal_amount_chain_metrics,
                       COALESCE(raw_json #>> '{{formal_amount_chain_metrics,today_virt_amount}}', trace_json #>> '{{formal_amount_chain_metrics,today_virt_amount}}', raw_json #>> '{{formal_period_amount_proof,amount_chain_metrics,today_virt_amount}}', trace_json #>> '{{formal_period_amount_proof,amount_chain_metrics,today_virt_amount}}') AS today_virt_amount,
                       COALESCE(raw_json #>> '{{formal_amount_chain_metrics,weekly_avg_with_today}}', trace_json #>> '{{formal_amount_chain_metrics,weekly_avg_with_today}}', raw_json #>> '{{formal_period_amount_proof,amount_chain_metrics,weekly_avg_with_today}}', trace_json #>> '{{formal_period_amount_proof,amount_chain_metrics,weekly_avg_with_today}}') AS weekly_avg_with_today,
                       COALESCE(raw_json #>> '{{formal_amount_chain_metrics,prev_weekly_avg}}', trace_json #>> '{{formal_amount_chain_metrics,prev_weekly_avg}}', raw_json #>> '{{formal_period_amount_proof,amount_chain_metrics,prev_weekly_avg}}', trace_json #>> '{{formal_period_amount_proof,amount_chain_metrics,prev_weekly_avg}}') AS prev_weekly_avg,
                       COALESCE(raw_json #>> '{{formal_amount_chain_metrics,monthly_avg_with_today}}', trace_json #>> '{{formal_amount_chain_metrics,monthly_avg_with_today}}', raw_json #>> '{{formal_period_amount_proof,amount_chain_metrics,monthly_avg_with_today}}', trace_json #>> '{{formal_period_amount_proof,amount_chain_metrics,monthly_avg_with_today}}') AS monthly_avg_with_today,
                       COALESCE(raw_json #>> '{{formal_amount_chain_metrics,prev_monthly_avg}}', trace_json #>> '{{formal_amount_chain_metrics,prev_monthly_avg}}', raw_json #>> '{{formal_period_amount_proof,amount_chain_metrics,prev_monthly_avg}}', trace_json #>> '{{formal_period_amount_proof,amount_chain_metrics,prev_monthly_avg}}') AS prev_monthly_avg,
                       COALESCE(raw_json #>> '{{formal_amount_chain_metrics,quarterly_avg_with_today}}', trace_json #>> '{{formal_amount_chain_metrics,quarterly_avg_with_today}}', raw_json #>> '{{formal_period_amount_proof,amount_chain_metrics,quarterly_avg_with_today}}', trace_json #>> '{{formal_period_amount_proof,amount_chain_metrics,quarterly_avg_with_today}}') AS quarterly_avg_with_today,
                       COALESCE(raw_json #>> '{{formal_amount_chain_metrics,prev_quarterly_avg}}', trace_json #>> '{{formal_amount_chain_metrics,prev_quarterly_avg}}', raw_json #>> '{{formal_period_amount_proof,amount_chain_metrics,prev_quarterly_avg}}', trace_json #>> '{{formal_period_amount_proof,amount_chain_metrics,prev_quarterly_avg}}') AS prev_quarterly_avg,
                       COALESCE(raw_json #>> '{{formal_amount_chain_metrics,yearly_avg_with_today}}', trace_json #>> '{{formal_amount_chain_metrics,yearly_avg_with_today}}', raw_json #>> '{{formal_period_amount_proof,amount_chain_metrics,yearly_avg_with_today}}', trace_json #>> '{{formal_period_amount_proof,amount_chain_metrics,yearly_avg_with_today}}') AS yearly_avg_with_today,
                       COALESCE(raw_json #>> '{{formal_amount_chain_metrics,prev_yearly_avg}}', trace_json #>> '{{formal_amount_chain_metrics,prev_yearly_avg}}', raw_json #>> '{{formal_period_amount_proof,amount_chain_metrics,prev_yearly_avg}}', trace_json #>> '{{formal_period_amount_proof,amount_chain_metrics,prev_yearly_avg}}') AS prev_yearly_avg,
                       COALESCE(raw_json -> 'virtual_amount_policy', trace_json -> 'virtual_amount_policy') AS virtual_amount_policy,
                       COALESCE(raw_json ->> 'virtual_amount_policy_version', trace_json ->> 'virtual_amount_policy_version') AS virtual_amount_policy_version,
                       NULL::jsonb AS raw_json,
                       NULL::jsonb AS trace_json,
                       created_at
                FROM {table_name}
                WHERE projection_run_id = %s
                  AND source_condition_run_id = %s
                  AND source_subscription_run_id = %s
                  AND source_snapshot_run_id = %s
                  AND projection_schema_version = %s
                  AND for_trade_date = %s
                {order_clause}
                """



def normalize_metric_row(row: Mapping[str, Any]) -> dict[str, Any]:
    output = normalize_mapping(row)
    output["asset_kind"] = str(output.get("asset_kind") or "")
    output["identity_key"] = str(output.get("identity_key") or "")
    output["projection_run_id"] = str(output.get("projection_run_id") or "")
    output["projection_schema_version"] = str(output.get("projection_schema_version") or "")
    output["metric_quality_status"] = str(output.get("metric_quality_status") or "")
    if output["projection_schema_version"] == TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION:
        for field in (
            "current_price",
            "current_30m_virtual_amount",
            "previous_day_same_window_amount",
            "previous_30m_full_amount",
            "today_virt_amount",
            "weekly_avg_with_today",
            "prev_weekly_avg",
            "monthly_avg_with_today",
            "prev_monthly_avg",
            "quarterly_avg_with_today",
            "prev_quarterly_avg",
            "yearly_avg_with_today",
            "prev_yearly_avg",
        ):
            output[field] = decimal_or_none(output.get(field))
        chain = output.get("formal_amount_chain_metrics")
        if isinstance(chain, Mapping):
            output["formal_amount_chain_metrics"] = {
                str(key): decimal_or_none(value) for key, value in chain.items()
            }
    return output


def projection_schema_versions(metric_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    versions = sorted({str(row.get("projection_schema_version") or "") for row in metric_rows if row.get("projection_schema_version")})
    return versions or [ACTION_CONFIRMATION_SCHEMA_VERSION]


def primary_projection_schema_version(metric_rows: Sequence[Mapping[str, Any]]) -> str:
    versions = projection_schema_versions(metric_rows)
    return versions[0] if len(versions) == 1 else "mixed"


def action_confirmation_metric_plan_replay_mode(metric_rows: Sequence[Mapping[str, Any]]) -> str:
    versions = {str(row.get("projection_schema_version") or "") for row in metric_rows if row.get("projection_schema_version")}
    if TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION in versions:
        return FULL_DAY_METRIC_TIME_SERIES_REPLAY_MODE
    latest_schema_versions = {
        ACTION_CONFIRMATION_SCHEMA_VERSION,
        FORMAL_AMOUNT_PROOF_SCHEMA_VERSION,
        REALTIME_VIRTUAL_METRIC_SCHEMA_VERSION,
        REALTIME_VIRTUAL_METRIC_WRITER_SCHEMA_VERSION,
        HISTORICAL_REPLAY_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_SCHEMA_VERSION,
    }
    if versions and versions <= latest_schema_versions:
        return LATEST_METRIC_BY_IDENTITY_REPLAY_MODE

    labels_by_identity: dict[tuple[str, str], set[str]] = {}
    for row in metric_rows:
        label = str(row.get("metric_minute_label") or "")
        if not label:
            continue
        key = (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""))
        if not key[0] or not key[1]:
            continue
        labels_by_identity.setdefault(key, set()).add(label)
    if any(len(labels) > 1 for labels in labels_by_identity.values()):
        return FULL_DAY_METRIC_TIME_SERIES_REPLAY_MODE
    return LATEST_METRIC_BY_IDENTITY_REPLAY_MODE


def build_action_confirmation_metric_plans_for_metric_grain(
    *,
    trigger_context_run_id: str,
    projection_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    for_trade_date: str,
    context_rows: Sequence[Mapping[str, Any]],
    metric_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return list(
        iter_action_confirmation_metric_plans_for_metric_grain(
            trigger_context_run_id=trigger_context_run_id,
            projection_run_id=projection_run_id,
            source_condition_run_id=source_condition_run_id,
            source_subscription_run_id=source_subscription_run_id,
            source_snapshot_run_id=source_snapshot_run_id,
            for_trade_date=for_trade_date,
            context_rows=context_rows,
            metric_rows=metric_rows,
        )
    )


def iter_action_confirmation_metric_plans_for_metric_grain(
    *,
    trigger_context_run_id: str,
    projection_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    for_trade_date: str,
    context_rows: Sequence[Mapping[str, Any]],
    metric_rows: Sequence[Mapping[str, Any]],
) -> Iterator[dict[str, Any]]:
    if action_confirmation_metric_plan_replay_mode(metric_rows) == FULL_DAY_METRIC_TIME_SERIES_REPLAY_MODE:
        yield from iter_action_confirmation_metric_full_day_replay_plans(
            trigger_context_run_id=trigger_context_run_id,
            projection_run_id=projection_run_id,
            source_condition_run_id=source_condition_run_id,
            source_subscription_run_id=source_subscription_run_id,
            source_snapshot_run_id=source_snapshot_run_id,
            for_trade_date=for_trade_date,
            context_rows=context_rows,
            metric_rows=metric_rows,
        )
        return
    yield from build_action_confirmation_metric_plans(
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=source_subscription_run_id,
        source_snapshot_run_id=source_snapshot_run_id,
        for_trade_date=for_trade_date,
        context_rows=context_rows,
        metric_rows=metric_rows,
    )


def collect_action_confirmation_metric_plan_report(
    plans: Iterable[Mapping[str, Any]],
    *,
    sample_limit: int,
) -> tuple[dict[str, Any], dict[str, list[Mapping[str, Any]]]]:
    counters: dict[str, Counter[str]] = {
        "by_asset_kind": Counter(),
        "would_trigger_by_asset_kind": Counter(),
        "would_pending_by_asset_kind": Counter(),
        "by_signal_type": Counter(),
        "would_trigger_by_signal_type": Counter(),
        "would_pending_by_signal_type": Counter(),
        "by_trigger_mark_candidate": Counter(),
        "would_trigger_by_trigger_mark_candidate": Counter(),
        "would_pending_by_trigger_mark_candidate": Counter(),
        "by_legacy_signal_type": Counter(),
        "would_trigger_by_legacy_signal_type": Counter(),
        "would_pending_by_legacy_signal_type": Counter(),
        "by_output_event_type": Counter(),
        "by_not_ready_reason": Counter(),
    }
    samples: dict[str, list[Mapping[str, Any]]] = {
        "would_trigger_plans": [],
        "would_pending_plans": [],
        "quality_only_plans": [],
        "no_op_samples": [],
    }
    candidate_count = 0
    would_trigger_count = 0
    would_pending_count = 0
    quality_only_count = 0
    state_change_plan_count = 0
    metric_ready_candidate_count = 0
    metric_missing_or_not_ready_candidate_count = 0
    trigger_live_true_count = 0
    pending_trigger_live_false_count = 0
    canonical_payload_invalid_count = 0
    opaque_action_confirmation_payload_count = 0
    matched_unready_count = 0
    year_auto_amount_operator_count = 0
    ordinary_formal_count = 0
    ordinary_formal_matched_count = 0
    ordinary_formal_proof_missing_count = 0
    legacy_runtime_signals: set[str] = set()
    lifecycle_state_keys: set[tuple[str, str, str, str, str, str]] = set()

    for plan in plans:
        candidate_count += 1
        plan_status = str(plan.get("plan_status") or "")
        output_event_type = str(plan.get("output_event_type") or "")
        signal_type = str(plan.get("signal_type") or "")
        asset_kind = str(plan.get("asset_kind") or "")
        trigger_mark_candidate = str(plan.get("trigger_mark_candidate") or "")
        legacy_signal_type = str(plan.get("legacy_signal_type") or "")
        not_ready_reason = str(plan.get("not_ready_reason") or "")

        increment_counter(counters["by_asset_kind"], asset_kind)
        increment_counter(counters["by_signal_type"], signal_type)
        increment_counter(counters["by_trigger_mark_candidate"], trigger_mark_candidate)
        increment_counter(counters["by_legacy_signal_type"], legacy_signal_type)
        increment_counter(counters["by_output_event_type"], output_event_type)
        increment_counter(counters["by_not_ready_reason"], not_ready_reason)
        if output_event_type in ALLOWED_OUTPUT_EVENT_TYPES:
            lifecycle_state_keys.add(lifecycle_state_key_tuple(plan))

        if plan_status == "would_trigger":
            would_trigger_count += 1
            increment_counter(counters["would_trigger_by_asset_kind"], asset_kind)
            increment_counter(counters["would_trigger_by_signal_type"], signal_type)
            increment_counter(counters["would_trigger_by_trigger_mark_candidate"], trigger_mark_candidate)
            increment_counter(counters["would_trigger_by_legacy_signal_type"], legacy_signal_type)
            append_sample(samples["would_trigger_plans"], plan, sample_limit)
        elif plan_status == "would_pending":
            would_pending_count += 1
            increment_counter(counters["would_pending_by_asset_kind"], asset_kind)
            increment_counter(counters["would_pending_by_signal_type"], signal_type)
            increment_counter(counters["would_pending_by_trigger_mark_candidate"], trigger_mark_candidate)
            increment_counter(counters["would_pending_by_legacy_signal_type"], legacy_signal_type)
            append_sample(samples["would_pending_plans"], plan, sample_limit)
        elif plan_status == "quality_only":
            quality_only_count += 1
            append_sample(samples["quality_only_plans"], plan, sample_limit)
        elif plan_status == "no_op":
            append_sample(samples["no_op_samples"], plan, sample_limit)

        if plan_has_material_trigger_state_change(plan):
            state_change_plan_count += 1
        if plan.get("metric_ready") is True:
            metric_ready_candidate_count += 1
        if not_ready_reason in {"metric_row_missing", "metric_not_ready"}:
            metric_missing_or_not_ready_candidate_count += 1
        if plan.get("trigger_live") is True:
            trigger_live_true_count += 1
        if plan.get("current_status") == "pending_market_data" and plan.get("trigger_live") is False:
            pending_trigger_live_false_count += 1
        if canonical_payload_errors(plan):
            canonical_payload_invalid_count += 1
        if "action_confirmation" in (plan.get("metric_trace") or {}):
            opaque_action_confirmation_payload_count += 1
        if plan_status == "would_trigger" and plan.get("metric_ready") is not True:
            matched_unready_count += 1
        if plan_uses_year_auto_amount_operator(plan):
            year_auto_amount_operator_count += 1
        if is_ordinary_formal_plan(plan):
            ordinary_formal_count += 1
            if output_event_type == "TriggerMatched":
                ordinary_formal_matched_count += 1
            if not_ready_reason == "formal_trigger_period_proof_missing":
                ordinary_formal_proof_missing_count += 1
        if signal_type and signal_type not in CANONICAL_SIGNAL_TYPES:
            legacy_runtime_signals.add(signal_type)

    by_output_event_type = dict(counters["by_output_event_type"])
    planned_output_event_types = dict(by_output_event_type)
    planned_output_event_types["TriggerPendingMarketData"] = 0
    planned_output_event_types.setdefault("TriggerMatched", 0)
    planned_output_event_types.setdefault(STATE_CHANGE_EVENT_TYPE, state_change_plan_count)
    planned_common_event_outbox = int(planned_output_event_types.get("TriggerMatched") or 0) + int(
        planned_output_event_types.get(STATE_CHANGE_EVENT_TYPE) or 0
    )
    summary = {
        "candidate_count": candidate_count,
        "would_trigger_count": would_trigger_count,
        "would_pending_count": would_pending_count,
        "quality_only_count": quality_only_count,
        **{key: dict(counter) for key, counter in counters.items()},
        "by_output_event_type": by_output_event_type,
        "state_change_plan_count": state_change_plan_count,
        "planned_output_event_types": planned_output_event_types,
        "planned_common_event_outbox": planned_common_event_outbox,
        "planned_common_trigger_state": len(lifecycle_state_keys),
        "dropped_pending_candidate_count": would_pending_count,
        "metric_ready_candidate_count": metric_ready_candidate_count,
        "metric_missing_or_not_ready_candidate_count": metric_missing_or_not_ready_candidate_count,
        "trigger_live_true_count": trigger_live_true_count,
        "pending_trigger_live_false_count": pending_trigger_live_false_count,
        "canonical_payload_invalid_count": canonical_payload_invalid_count,
        "opaque_action_confirmation_payload_count": opaque_action_confirmation_payload_count,
        "quality_stream_counts": {
            "matched_unready_count": matched_unready_count,
            "invalid_canonical_payload_count": canonical_payload_invalid_count,
            "year_auto_amount_operator_count": year_auto_amount_operator_count,
            "ordinary_formal_count": ordinary_formal_count,
            "ordinary_formal_matched_count": ordinary_formal_matched_count,
            "ordinary_formal_proof_missing_count": ordinary_formal_proof_missing_count,
            "legacy_runtime_signals": sorted(legacy_runtime_signals),
        },
    }
    return summary, samples


def increment_counter(counter: Counter[str], value: str) -> None:
    if value:
        counter[value] += 1


def append_sample(samples: list[Mapping[str, Any]], plan: Mapping[str, Any], sample_limit: int) -> None:
    if len(samples) < sample_limit:
        samples.append(plan)


def build_action_confirmation_metric_dry_run_report(
    *,
    trigger_context_run_id: str,
    projection_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    for_trade_date: str,
    context_rows: Sequence[Mapping[str, Any]],
    metric_rows: Sequence[Mapping[str, Any]],
    trigger_run: Mapping[str, Any] | None = None,
    before_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    after_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    sample_limit: int = 80,
) -> dict[str, Any]:
    replay_mode = action_confirmation_metric_plan_replay_mode(metric_rows)
    summary, plan_samples = collect_action_confirmation_metric_plan_report(
        iter_action_confirmation_metric_plans_for_metric_grain(
            trigger_context_run_id=trigger_context_run_id,
            projection_run_id=projection_run_id,
            source_condition_run_id=source_condition_run_id,
            source_subscription_run_id=source_subscription_run_id,
            source_snapshot_run_id=source_snapshot_run_id,
            for_trade_date=for_trade_date,
            context_rows=context_rows,
            metric_rows=metric_rows,
        ),
        sample_limit=sample_limit,
    )
    quality_items = build_action_confirmation_metric_quality_items(
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=source_subscription_run_id,
        source_snapshot_run_id=source_snapshot_run_id,
        for_trade_date=for_trade_date,
        trigger_run=trigger_run or {},
        context_rows=context_rows,
        metric_rows=metric_rows,
        plans=[],
        summary=summary,
        before_row_counts=before_row_counts,
        after_row_counts=after_row_counts,
    )
    quality_counts = count_quality_severities(quality_items)
    return {
        "stage": "N4 action-confirmation metric dry-run",
        "result": "DRY_RUN_PASS" if quality_counts["P0"] == 0 else "DRY_RUN_BLOCKED",
        "layer_role": "N4_trigger",
        "mode": "action_confirmation_metric_dry_run",
        "replay_mode": replay_mode,
        "trigger_context_run_id": trigger_context_run_id,
        "projection_run_id": projection_run_id,
        "projection_schema_version": primary_projection_schema_version(metric_rows),
        "projection_schema_versions": projection_schema_versions(metric_rows),
        "source_condition_run_id": source_condition_run_id,
        "source_subscription_run_id": source_subscription_run_id,
        "source_snapshot_run_id": source_snapshot_run_id,
        "for_trade_date": for_trade_date,
        "matcher_contract": {
            "reads_only_n3_action_confirmation_metric_facts": True,
            "reads_raw_minute_tables": False,
            "assembles_1m_5m_30m_120m_indicators": False,
            "trusts_opaque_action_confirmation_payload": False,
            "consumes_outbox": False,
            "writes_database": False,
            "n4_decides_final_action_mark": False,
            "n5_final_confirmation_deferred": True,
        },
        "input_summary": {
            "raw_context_row_count": len(context_rows),
            "metric_row_count": len(metric_rows),
            "metric_ready_count": sum(1 for row in metric_rows if metric_is_ready(row)),
            "metric_not_ready_count": sum(1 for row in metric_rows if not metric_is_ready(row)),
        },
        "summary": summary,
        "plans": {
            "output_plan_count": summary.get("planned_common_event_outbox", 0),
            "would_trigger_plans": plan_samples["would_trigger_plans"],
            "would_pending_plans": plan_samples["would_pending_plans"],
            "quality_only_plans": plan_samples["quality_only_plans"],
            "no_op_samples": plan_samples["no_op_samples"],
        },
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "read_only_database_checks": True,
            "common_event_outbox_consumed": False,
            "common_event_inbox_written": False,
            "checkpoint_written": False,
            "trigger_match_written": False,
            "trigger_state_written": False,
            "event_outbox_written": False,
            "market_data_pulled": False,
            "raw_minute_tables_read": False,
            "worker_started": False,
            "downstream_layers_touched": False,
            "old_system_touched": False,
            "real_trade": False,
        },
        "before_row_counts": before_row_counts or {},
        "after_row_counts": after_row_counts or {},
        "rollback_plan": {
            "this_dry_run": "No DB rollback required; generated report/preflight artifacts may be deleted if discarded.",
            "future_execute": "Future N4 execute rollback must be scoped to its execute_run_id and guard N5/N6 downstream refs.",
        },
        "next_gate": {
            "allow_final_gate_review": quality_counts["P0"] == 0,
            "allow_business_execute": False,
            "execute_blocker": "business execute still requires separate N4 execute contract/preflight/final gate",
            "n5_action_execute_allowed": False,
        },
    }


def build_action_confirmation_metric_true_full_day_streaming_report(
    *,
    dsn: str,
    trigger_context_run_id: str,
    projection_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    for_trade_date: str,
    context_rows: Sequence[Mapping[str, Any]],
    trigger_run: Mapping[str, Any] | None = None,
    before_row_counts: Mapping[str, Mapping[str, Any]] | None = None,
    sample_limit: int = 80,
) -> dict[str, Any]:
    contexts_by_identity: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in context_rows:
        if row.get("run_id") != trigger_context_run_id:
            continue
        key = (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""))
        if key[0] and key[1]:
            contexts_by_identity.setdefault(key, []).append(row)

    metric_row_count = 0
    metric_ready_count = 0
    metric_not_ready_count = 0
    metric_lineage_mismatch_count = 0

    def iter_streaming_plans() -> Iterator[dict[str, Any]]:
        nonlocal metric_row_count, metric_ready_count, metric_not_ready_count, metric_lineage_mismatch_count
        for key, metrics in iter_true_full_day_metric_identity_groups(
            dsn,
            projection_run_id=projection_run_id,
            source_condition_run_id=source_condition_run_id,
            source_subscription_run_id=source_subscription_run_id,
            source_snapshot_run_id=source_snapshot_run_id,
            for_trade_date=for_trade_date,
        ):
            metric_row_count += len(metrics)
            metric_ready_count += sum(1 for metric in metrics if metric_is_ready(metric))
            metric_not_ready_count += sum(1 for metric in metrics if not metric_is_ready(metric))
            metric_lineage_mismatch_count += sum(
                1
                for metric in metrics
                if metric_lineage_errors(
                    metric,
                    projection_run_id=projection_run_id,
                    source_condition_run_id=source_condition_run_id,
                    source_subscription_run_id=source_subscription_run_id,
                    source_snapshot_run_id=source_snapshot_run_id,
                    for_trade_date=for_trade_date,
                )
            )
            rows = contexts_by_identity.get(key)
            if not rows:
                continue
            yield from iter_action_confirmation_metric_full_day_replay_plans(
                trigger_context_run_id=trigger_context_run_id,
                projection_run_id=projection_run_id,
                source_condition_run_id=source_condition_run_id,
                source_subscription_run_id=source_subscription_run_id,
                source_snapshot_run_id=source_snapshot_run_id,
                for_trade_date=for_trade_date,
                context_rows=rows,
                metric_rows=metrics,
            )

    summary, plan_samples = collect_action_confirmation_metric_plan_report(
        iter_streaming_plans(),
        sample_limit=sample_limit,
    )
    summary.update(
        {
            "metric_row_count": metric_row_count,
            "metric_ready_count": metric_ready_count,
            "metric_not_ready_count": metric_not_ready_count,
            "metric_lineage_mismatch_count": metric_lineage_mismatch_count,
            "streaming_metric_fetch": True,
        }
    )
    after_row_counts = capture_row_counts(dsn)
    quality_items = build_action_confirmation_metric_quality_items(
        trigger_context_run_id=trigger_context_run_id,
        projection_run_id=projection_run_id,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=source_subscription_run_id,
        source_snapshot_run_id=source_snapshot_run_id,
        for_trade_date=for_trade_date,
        trigger_run=trigger_run or {},
        context_rows=context_rows,
        metric_rows=[],
        plans=[],
        summary=summary,
        before_row_counts=before_row_counts,
        after_row_counts=after_row_counts,
    )
    quality_counts = count_quality_severities(quality_items)
    return {
        "stage": "N4 action-confirmation metric dry-run",
        "result": "DRY_RUN_PASS" if quality_counts["P0"] == 0 else "DRY_RUN_BLOCKED",
        "layer_role": "N4_trigger",
        "mode": "action_confirmation_metric_dry_run",
        "replay_mode": FULL_DAY_METRIC_TIME_SERIES_REPLAY_MODE,
        "trigger_context_run_id": trigger_context_run_id,
        "projection_run_id": projection_run_id,
        "projection_schema_version": TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION,
        "projection_schema_versions": [TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION],
        "source_condition_run_id": source_condition_run_id,
        "source_subscription_run_id": source_subscription_run_id,
        "source_snapshot_run_id": source_snapshot_run_id,
        "for_trade_date": for_trade_date,
        "matcher_contract": {
            "reads_only_n3_action_confirmation_metric_facts": True,
            "reads_raw_minute_tables": False,
            "assembles_1m_5m_30m_120m_indicators": False,
            "trusts_opaque_action_confirmation_payload": False,
            "consumes_outbox": False,
            "writes_database": False,
            "n4_decides_final_action_mark": False,
            "n5_final_confirmation_deferred": True,
        },
        "input_summary": {
            "raw_context_row_count": len(context_rows),
            "metric_row_count": metric_row_count,
            "metric_ready_count": metric_ready_count,
            "metric_not_ready_count": metric_not_ready_count,
            "streaming_metric_fetch": True,
        },
        "summary": summary,
        "plans": {
            "output_plan_count": summary.get("planned_common_event_outbox", 0),
            "would_trigger_plans": plan_samples["would_trigger_plans"],
            "would_pending_plans": plan_samples["would_pending_plans"],
            "quality_only_plans": plan_samples["quality_only_plans"],
            "no_op_samples": plan_samples["no_op_samples"],
        },
        "quality": {
            "p0_count": quality_counts["P0"],
            "p1_count": quality_counts["P1"],
            "p2_count": quality_counts["P2"],
            "items": quality_items,
        },
        "side_effects": {
            "read_only_database_checks": True,
            "common_event_outbox_consumed": False,
            "common_event_inbox_written": False,
            "checkpoint_written": False,
            "trigger_match_written": False,
            "trigger_state_written": False,
            "event_outbox_written": False,
            "market_data_pulled": False,
            "raw_minute_tables_read": False,
            "worker_started": False,
            "downstream_layers_touched": False,
            "old_system_touched": False,
            "real_trade": False,
        },
        "before_row_counts": before_row_counts or {},
        "after_row_counts": after_row_counts,
        "rollback_plan": {
            "this_dry_run": "No DB rollback required; generated report/preflight artifacts may be deleted if discarded.",
            "future_execute": "Future N4 execute rollback must be scoped to its execute_run_id and guard N5/N6 downstream refs.",
        },
        "next_gate": {
            "allow_final_gate_review": quality_counts["P0"] == 0,
            "allow_business_execute": False,
            "execute_blocker": "business execute still requires separate N4 execute contract/preflight/final gate",
            "n5_action_execute_allowed": False,
        },
    }


def build_action_confirmation_metric_plans(
    *,
    trigger_context_run_id: str,
    projection_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    for_trade_date: str,
    context_rows: Sequence[Mapping[str, Any]],
    metric_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    metric_lookup = latest_metric_by_identity(metric_rows, projection_run_id=projection_run_id)
    plans: list[dict[str, Any]] = []
    for row in context_rows:
        if row.get("run_id") != trigger_context_run_id:
            continue
        legacy_signal = metric_candidate_signal_for_context(row)
        if not legacy_signal:
            continue
        metric = metric_lookup.get((str(row.get("asset_kind") or ""), str(row.get("identity_key") or "")))
        plans.append(
            evaluate_action_confirmation_metric_candidate(
                row=row,
                metric=metric,
                legacy_signal_type=legacy_signal,
                projection_run_id=projection_run_id,
                source_condition_run_id=source_condition_run_id,
                source_subscription_run_id=source_subscription_run_id,
                source_snapshot_run_id=source_snapshot_run_id,
                for_trade_date=for_trade_date,
            )
        )
    return plans


def build_action_confirmation_metric_full_day_replay_plans(
    *,
    trigger_context_run_id: str,
    projection_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    for_trade_date: str,
    context_rows: Sequence[Mapping[str, Any]],
    metric_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return list(
        iter_action_confirmation_metric_full_day_replay_plans(
            trigger_context_run_id=trigger_context_run_id,
            projection_run_id=projection_run_id,
            source_condition_run_id=source_condition_run_id,
            source_subscription_run_id=source_subscription_run_id,
            source_snapshot_run_id=source_snapshot_run_id,
            for_trade_date=for_trade_date,
            context_rows=context_rows,
            metric_rows=metric_rows,
        )
    )


def iter_lifecycle_metric_plans(raw_plans: Iterable[Mapping[str, Any]]) -> Iterator[dict[str, Any]]:
    previous_state = inactive_lifecycle_state()
    for raw_plan in raw_plans:
        output_event_type = str(raw_plan.get("output_event_type") or "")
        if output_event_type == "TriggerMatched":
            current_state = lifecycle_state_from_plan(raw_plan)
            if not previous_state["trigger_live"]:
                yield lifecycle_output_plan(
                    raw_plan,
                    previous_state=previous_state,
                    output_event_type="TriggerMatched",
                    state_change_reason="activated",
                )
                previous_state = current_state
                continue
            if lifecycle_state_materially_changed(previous_state, current_state):
                yield lifecycle_output_plan(
                    raw_plan,
                    previous_state=previous_state,
                    output_event_type=STATE_CHANGE_EVENT_TYPE,
                    state_change_reason=lifecycle_state_change_reason(previous_state, current_state),
                )
                previous_state = current_state
            continue
        if previous_state["trigger_live"] and plan_has_formal_no_trigger_evidence(raw_plan):
            yield lifecycle_inactive_output_plan(raw_plan, previous_state=previous_state)
            previous_state = inactive_lifecycle_state()


def inactive_lifecycle_state() -> dict[str, Any]:
    return {
        "trigger_live": False,
        "current_status": "inactive",
        "primary_trigger_period": None,
        "all_trigger_periods": [],
        "projection_30m_flag": False,
        "projection_30m_type": "none",
        "trigger_mark_candidate": None,
    }


def lifecycle_state_from_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "trigger_live": bool(plan.get("trigger_live")),
        "current_status": str(plan.get("current_status") or ("matched" if plan.get("trigger_live") else "inactive")),
        "primary_trigger_period": plan.get("primary_trigger_period"),
        "all_trigger_periods": list(normalize_periods_for_state_change(plan.get("all_trigger_periods"))),
        "projection_30m_flag": bool(plan.get("projection_30m_flag")),
        "projection_30m_type": str(plan.get("projection_30m_type") or "none"),
        "trigger_mark_candidate": plan.get("trigger_mark_candidate"),
    }


def lifecycle_state_materially_changed(previous_state: Mapping[str, Any], current_state: Mapping[str, Any]) -> bool:
    if bool(previous_state.get("trigger_live")) != bool(current_state.get("trigger_live")):
        return True
    if str(previous_state.get("current_status") or "") != str(current_state.get("current_status") or ""):
        return True
    if str(previous_state.get("primary_trigger_period") or "") != str(current_state.get("primary_trigger_period") or ""):
        return True
    if normalize_periods_for_state_change(previous_state.get("all_trigger_periods")) != normalize_periods_for_state_change(
        current_state.get("all_trigger_periods")
    ):
        return True
    return False


def lifecycle_state_change_reason(previous_state: Mapping[str, Any], current_state: Mapping[str, Any]) -> str:
    if normalize_periods_for_state_change(previous_state.get("all_trigger_periods")) != normalize_periods_for_state_change(
        current_state.get("all_trigger_periods")
    ):
        return "trigger_periods_changed"
    if str(previous_state.get("primary_trigger_period") or "") != str(current_state.get("primary_trigger_period") or ""):
        return "primary_trigger_period_changed"
    return "state_changed"


def lifecycle_output_plan(
    plan: Mapping[str, Any],
    *,
    previous_state: Mapping[str, Any],
    output_event_type: str,
    state_change_reason: str,
) -> dict[str, Any]:
    output = dict(plan)
    output["output_event_type"] = output_event_type
    output["plan_status"] = "would_trigger" if output_event_type == "TriggerMatched" else "would_state_change"
    output["writes_common_trigger_match"] = output_event_type == "TriggerMatched"
    output["is_n5_action_entry"] = output_event_type == "TriggerMatched"
    output["n5_entry_allowed"] = output_event_type == "TriggerMatched"
    output["previous_trigger_live"] = bool(previous_state.get("trigger_live"))
    output["previous_status"] = previous_state.get("current_status") or "inactive"
    output["previous_primary_trigger_period"] = previous_state.get("primary_trigger_period")
    output["previous_all_trigger_periods"] = list(
        normalize_periods_for_state_change(previous_state.get("all_trigger_periods"))
    )
    output["previous_projection_30m_flag"] = bool(previous_state.get("projection_30m_flag"))
    output["previous_projection_30m_type"] = previous_state.get("projection_30m_type") or "none"
    output["previous_trigger_mark_candidate"] = previous_state.get("trigger_mark_candidate")
    output["state_change_reason"] = state_change_reason
    output["source_outcome_event_type"] = None
    output["source_outcome_event_id"] = None
    output["lifecycle_state_key_version"] = LIFECYCLE_STATE_KEY_VERSION
    output["lifecycle_state_key"] = lifecycle_state_key(output)
    return output


def hydrate_metric_plan_trace(plan: dict[str, Any], *, row: Mapping[str, Any], metric: Mapping[str, Any]) -> None:
    """Populate trace fields only for lifecycle rows that are actually emitted."""

    legacy_signal_type = str(plan.get("legacy_signal_type") or "")
    condition_key = str(plan.get("condition_key") or row.get("condition_key") or "")
    trigger_period = str(plan.get("trigger_period") or "")
    plan["metric_trace"] = build_metric_trace(metric, legacy_signal_type=legacy_signal_type)
    plan["period_trigger_baseline_trace"] = build_period_trigger_baseline_trace(row, condition_key, trigger_period)


def lifecycle_inactive_output_plan(
    plan: Mapping[str, Any],
    *,
    previous_state: Mapping[str, Any],
) -> dict[str, Any]:
    output = lifecycle_output_plan(
        plan,
        previous_state=previous_state,
        output_event_type=STATE_CHANGE_EVENT_TYPE,
        state_change_reason="deactivated",
    )
    output["trigger_live"] = False
    output["current_status"] = "inactive"
    output["trigger_period"] = previous_state.get("primary_trigger_period") or output.get("trigger_period")
    output["primary_trigger_period"] = None
    output["all_trigger_periods"] = []
    output["triggered_periods"] = []
    output["trigger_price"] = None
    output["trigger_price_source"] = None
    output["projection_30m_flag"] = False
    output["projection_30m_type"] = "none"
    return output


def lifecycle_state_key(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "trade_date": plan.get("for_trade_date"),
        "asset_kind": plan.get("asset_kind"),
        "identity_key": plan.get("identity_key"),
        "direction": plan.get("direction"),
        "signal_type": plan.get("signal_type"),
        "condition_key": plan.get("condition_key"),
    }


def lifecycle_state_key_tuple(plan: Mapping[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(plan.get("asset_kind") or ""),
        str(plan.get("identity_key") or ""),
        str(plan.get("direction") or ""),
        str(plan.get("signal_type") or ""),
        str(plan.get("condition_key") or ""),
        str(plan.get("for_trade_date") or ""),
    )


def plan_has_formal_no_trigger_evidence(plan: Mapping[str, Any]) -> bool:
    if plan.get("metric_ready") is not True:
        return False
    if str(plan.get("data_quality_status") or "") != "passed":
        return False
    return str(plan.get("not_ready_reason") or "") in {
        "metric_ready_but_formal_trigger_not_satisfied",
        "metric_ready_but_side_projection_not_satisfied",
    }


def iter_action_confirmation_metric_full_day_replay_plans(
    *,
    trigger_context_run_id: str,
    projection_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    for_trade_date: str,
    context_rows: Sequence[Mapping[str, Any]],
    metric_rows: Sequence[Mapping[str, Any]],
) -> Iterator[dict[str, Any]]:
    """Build N4 replay plans for every metric minute.

    The existing realtime planner intentionally uses only the latest metric per
    identity.  Full-day replay must evaluate the time series, otherwise a later
    non-match can hide an earlier match such as 10:56.
    """

    metric_lookup = metrics_by_identity_time_series(metric_rows, projection_run_id=projection_run_id)
    for row in context_rows:
        if row.get("run_id") != trigger_context_run_id:
            continue
        legacy_signal = metric_candidate_signal_for_context(row)
        if not legacy_signal:
            continue
        key = (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""))
        metrics = metric_lookup.get(key) or []
        if not metrics:
            plan = evaluate_action_confirmation_metric_candidate(
                row=row,
                metric=None,
                legacy_signal_type=legacy_signal,
                projection_run_id=projection_run_id,
                source_condition_run_id=source_condition_run_id,
                source_subscription_run_id=source_subscription_run_id,
                source_snapshot_run_id=source_snapshot_run_id,
                for_trade_date=for_trade_date,
            )
            plan["replay_mode"] = "full_day_metric_time_series"
            continue
        previous_state = inactive_lifecycle_state()
        for metric in metrics:
            if isinstance(metric, dict):
                metric[_DEFER_HEAVY_TRACE_KEY] = True
            plan = evaluate_action_confirmation_metric_candidate(
                row=row,
                metric=metric,
                legacy_signal_type=legacy_signal,
                projection_run_id=projection_run_id,
                source_condition_run_id=source_condition_run_id,
                source_subscription_run_id=source_subscription_run_id,
                source_snapshot_run_id=source_snapshot_run_id,
                for_trade_date=for_trade_date,
            )
            plan["replay_mode"] = "full_day_metric_time_series"
            output_event_type = str(plan.get("output_event_type") or "")
            if output_event_type == "TriggerMatched":
                current_state = lifecycle_state_from_plan(plan)
                if not previous_state["trigger_live"]:
                    output = lifecycle_output_plan(
                        plan,
                        previous_state=previous_state,
                        output_event_type="TriggerMatched",
                        state_change_reason="activated",
                    )
                    hydrate_metric_plan_trace(output, row=row, metric=metric)
                    yield output
                    previous_state = current_state
                    continue
                if lifecycle_state_materially_changed(previous_state, current_state):
                    output = lifecycle_output_plan(
                        plan,
                        previous_state=previous_state,
                        output_event_type=STATE_CHANGE_EVENT_TYPE,
                        state_change_reason=lifecycle_state_change_reason(previous_state, current_state),
                    )
                    hydrate_metric_plan_trace(output, row=row, metric=metric)
                    yield output
                    previous_state = current_state
                continue
            if previous_state["trigger_live"] and plan_has_formal_no_trigger_evidence(plan):
                output = lifecycle_inactive_output_plan(plan, previous_state=previous_state)
                hydrate_metric_plan_trace(output, row=row, metric=metric)
                yield output
                previous_state = inactive_lifecycle_state()



def latest_metric_by_identity(
    metric_rows: Sequence[Mapping[str, Any]],
    *,
    projection_run_id: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    output: dict[tuple[str, str], dict[str, Any]] = {}
    for row in metric_rows:
        if row.get("projection_run_id") != projection_run_id:
            continue
        key = (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""))
        if not key[0] or not key[1]:
            continue
        output.setdefault(key, dict(row))
    return output


def metrics_by_identity_time_series(
    metric_rows: Sequence[Mapping[str, Any]],
    *,
    projection_run_id: str,
) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    output: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in metric_rows:
        if row.get("projection_run_id") != projection_run_id:
            continue
        key = (str(row.get("asset_kind") or ""), str(row.get("identity_key") or ""))
        if not key[0] or not key[1]:
            continue
        output.setdefault(key, []).append(row)
    for rows in output.values():
        rows.sort(
            key=lambda item: (
                str(item.get("metric_time") or ""),
                str(item.get("metric_minute_label") or ""),
                int(item.get("action_confirmation_metric_id") or 0),
            )
        )
    return output


def metric_candidate_signal_for_context(row: Mapping[str, Any]) -> str | None:
    direction = str(row.get("direction") or "")
    condition_key = str(row.get("condition_key") or "")
    allowed = set(normalize_text_array(row.get("allowed_signal_types")))
    if condition_key == "BUY_HINT" and direction == "buy" and "BUY_HINT" in allowed:
        return "BUY_HINT"
    if condition_key == "SELL_HINT" and direction == "sell" and "SELL_HINT" in allowed:
        return "SELL_HINT"
    if direction == "buy" and "B_BUY" in allowed:
        return "B_BUY"
    if direction == "sell" and "S_SELL" in allowed:
        return "S_SELL"
    if direction == "buy" and "B_BUY_30M_VOL" in allowed:
        return "B_BUY_30M_VOL"
    if direction == "sell" and "S_SELL_30M_SHRINK" in allowed:
        return "S_SELL_30M_SHRINK"
    return None


def evaluate_action_confirmation_metric_candidate(
    *,
    row: Mapping[str, Any],
    metric: Mapping[str, Any] | None,
    legacy_signal_type: str,
    projection_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    for_trade_date: str,
) -> dict[str, Any]:
    if metric is None:
        return build_metric_plan(
            row=row,
            metric={},
            legacy_signal_type=legacy_signal_type,
            projection_run_id=projection_run_id,
            plan_status="would_pending",
            output_event_type="TriggerPendingMarketData",
            data_quality_status="missing",
            projection_30m_type="none",
            not_ready_reason="metric_row_missing",
            dry_run_reason="N3 action-confirmation metric row is missing; N4 must not repair from raw minute facts",
        )
    lineage_errors = metric_lineage_errors(
        metric,
        projection_run_id=projection_run_id,
        source_condition_run_id=source_condition_run_id,
        source_subscription_run_id=source_subscription_run_id,
        source_snapshot_run_id=source_snapshot_run_id,
        for_trade_date=for_trade_date,
    )
    if lineage_errors:
        return build_metric_plan(
            row=row,
            metric=metric,
            legacy_signal_type=legacy_signal_type,
            projection_run_id=projection_run_id,
            plan_status="quality_only",
            output_event_type=None,
            data_quality_status="failed",
            projection_30m_type="none",
            not_ready_reason="metric_lineage_mismatch:" + ",".join(lineage_errors),
            dry_run_reason="Metric row lineage does not match the N4 allowlist; quality-only/no-op",
        )
    if not metric_scope_matches_context_legacy_signal(metric, legacy_signal_type):
        return build_metric_plan(
            row=row,
            metric=metric,
            legacy_signal_type=legacy_signal_type,
            projection_run_id=projection_run_id,
            plan_status="would_pending",
            output_event_type="TriggerPendingMarketData",
            data_quality_status="passed",
            projection_30m_type="none",
            not_ready_reason="metric_scope_not_compatible_with_context_condition",
            dry_run_reason="N3 metric condition scope does not match the N4 localized context condition; no fallback allowed",
        )
    if not metric_is_ready(metric):
        return build_metric_plan(
            row=row,
            metric=metric,
            legacy_signal_type=legacy_signal_type,
            projection_run_id=projection_run_id,
            plan_status="would_pending",
            output_event_type="TriggerPendingMarketData",
            data_quality_status=str(metric.get("metric_quality_status") or "not_ready"),
            projection_30m_type="none",
            not_ready_reason="metric_not_ready",
            dry_run_reason="N3 action-confirmation metric is not ready; N4 must not promote it to TriggerMatched",
        )
    if legacy_signal_type in ORDINARY_RUNTIME_SIGNALS:
        projection_type = projection_30m_type_for_metric_candidate(legacy_signal_type, metric)
        formal_proof = formal_trigger_period_proof(row=row, metric=metric)
        if not formal_proof["triggered_periods"] and formal_proof["status"] == "empty":
            return build_metric_plan(
                row=row,
                metric=metric,
                legacy_signal_type=legacy_signal_type,
                projection_run_id=projection_run_id,
                plan_status="would_pending",
                output_event_type="TriggerPendingMarketData",
                data_quality_status="passed",
                projection_30m_type=projection_type,
                not_ready_reason="metric_ready_but_formal_trigger_not_satisfied",
                dry_run_reason=(
                    "N3 ready action-confirmation metric and N2 trigger baseline were evaluated, "
                    "but no requested formal Y/Q/M/W/D period triggered"
                ),
                formal_triggered_periods=[],
                formal_triggered_period_details=formal_proof["triggered_period_details"],
                formal_proof_status=formal_proof["status"],
            )
        if not formal_proof["triggered_periods"]:
            return build_metric_plan(
                row=row,
                metric=metric,
                legacy_signal_type=legacy_signal_type,
                projection_run_id=projection_run_id,
                plan_status="would_pending",
                output_event_type="TriggerPendingMarketData",
                data_quality_status="passed",
                projection_30m_type=projection_type,
                not_ready_reason="formal_trigger_period_proof_missing",
                dry_run_reason=(
                    "N3 ready action-confirmation metric is available, "
                    "but N4 formal Y/Q/M/W/D trigger proof is missing"
                ),
                formal_triggered_periods=[],
                formal_triggered_period_details=formal_proof.get("triggered_period_details") or [],
                formal_proof_status=formal_proof["status"],
            )
        return build_metric_plan(
            row=row,
            metric=metric,
            legacy_signal_type=legacy_signal_type,
            projection_run_id=projection_run_id,
            plan_status="would_trigger",
            output_event_type="TriggerMatched",
            data_quality_status="passed",
            projection_30m_type=projection_type,
            not_ready_reason=None,
            dry_run_reason="N3 standard metric satisfies N4 ordinary formal price and amount-chain proof",
            formal_triggered_periods=formal_proof["triggered_periods"],
            formal_triggered_period_details=formal_proof["triggered_period_details"],
            formal_proof_status=formal_proof["status"],
        )
    if condition_key_is_hint(str(row.get("condition_key") or "")):
        hint_proof = hint_30m_calibrated_proof_status(legacy_signal_type=legacy_signal_type, metric=metric)
        if hint_proof.get("status") != "passed":
            return build_metric_plan(
                row=row,
                metric=metric,
                legacy_signal_type=legacy_signal_type,
                projection_run_id=projection_run_id,
                plan_status="would_pending",
                output_event_type="TriggerPendingMarketData",
                data_quality_status="passed",
                projection_30m_type="none",
                not_ready_reason="hint_30m_calibrated_proof_missing_or_invalid",
                dry_run_reason="N3 calibrated 30m proof is missing, invalid, or price confirmation failed; N4 must not fallback",
            )
        projection_type = projection_30m_type_for_metric_candidate(legacy_signal_type, metric)
        if projection_type != "none":
            return build_metric_plan(
                row=row,
                metric=metric,
                legacy_signal_type=legacy_signal_type,
                projection_run_id=projection_run_id,
                plan_status="would_trigger",
                output_event_type="TriggerMatched",
                data_quality_status="passed",
                projection_30m_type=projection_type,
                not_ready_reason=None,
                dry_run_reason="N3 ready calibrated 30m metric satisfies N4 HINT projection evidence",
            )
        return build_metric_plan(
            row=row,
            metric=metric,
            legacy_signal_type=legacy_signal_type,
            projection_run_id=projection_run_id,
            plan_status="would_pending",
            output_event_type="TriggerPendingMarketData",
            data_quality_status="passed",
            projection_30m_type="none",
            not_ready_reason="metric_ready_but_side_projection_not_satisfied",
            dry_run_reason="Metric is ready and calibrated, but side-specific N4 30m amount evidence is not satisfied",
        )
    projection_type = projection_30m_type_for_metric_candidate(legacy_signal_type, metric)
    if projection_type != "none":
        return build_metric_plan(
            row=row,
            metric=metric,
            legacy_signal_type=legacy_signal_type,
            projection_run_id=projection_run_id,
            plan_status="would_pending",
            output_event_type="TriggerPendingMarketData",
            data_quality_status="passed",
            projection_30m_type=projection_type,
            not_ready_reason="projection_30m_not_legal_without_hint_context",
            dry_run_reason="30m projection evidence is not a formal TriggerMatched source for ordinary BUY/SELL/FULL",
        )
    return build_metric_plan(
        row=row,
        metric=metric,
        legacy_signal_type=legacy_signal_type,
        projection_run_id=projection_run_id,
        plan_status="would_pending",
        output_event_type="TriggerPendingMarketData",
        data_quality_status="passed",
        projection_30m_type="none",
        not_ready_reason="metric_ready_but_side_projection_not_satisfied",
        dry_run_reason="Metric is ready, but side-specific N4 30m marker evidence is not satisfied",
    )


def metric_lineage_errors(
    metric: Mapping[str, Any],
    *,
    projection_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    for_trade_date: str,
) -> list[str]:
    checks = {
        "projection_run_id": projection_run_id,
        "source_condition_run_id": source_condition_run_id,
        "source_subscription_run_id": source_subscription_run_id,
        "for_trade_date": for_trade_date,
        "trade_date": for_trade_date,
    }
    if not metric_allows_multiple_source_snapshot_run_ids(metric):
        checks["source_snapshot_run_id"] = source_snapshot_run_id
    errors = [key for key, expected in checks.items() if str(metric.get(key) or "") != str(expected)]
    if str(metric.get("projection_schema_version") or "") not in ALLOWED_ACTION_CONFIRMATION_SCHEMA_VERSIONS:
        errors.append("projection_schema_version")
    return errors


def metric_allows_multiple_source_snapshot_run_ids(metric: Mapping[str, Any]) -> bool:
    return str(metric.get("projection_schema_version") or "") == HISTORICAL_REPLAY_FORMAL_AMOUNT_CHAIN_UNIT_PROOF_SCHEMA_VERSION


def metric_scope_matches_context_legacy_signal(metric: Mapping[str, Any], legacy_signal_type: str) -> bool:
    declared_conditions, declared_signals = metric_declared_condition_scope(metric)
    if not declared_conditions and not declared_signals:
        return True
    if legacy_signal_type in {"BUY_HINT", "SELL_HINT"}:
        if metric_full_scope_matches_hint_context(metric, legacy_signal_type):
            return True
        return legacy_signal_type in declared_conditions or legacy_signal_type in declared_signals
    if legacy_signal_type == "B_BUY":
        return not (declared_conditions & {"BUY_HINT", "SELL_HINT"} or declared_signals & {"BUY_HINT", "SELL_HINT"})
    if legacy_signal_type == "S_SELL":
        return not (declared_conditions & {"BUY_HINT", "SELL_HINT"} or declared_signals & {"BUY_HINT", "SELL_HINT"})
    return True


def metric_declared_condition_scope(metric: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    cache = mutable_local_cache(metric)
    cache_key = "metric_declared_condition_scope"
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    raw_json = metric.get("raw_json") if isinstance(metric.get("raw_json"), Mapping) else {}
    trace_json = metric.get("trace_json") if isinstance(metric.get("trace_json"), Mapping) else {}
    conditions = {
        str(value).upper()
        for value in (
            metric.get("condition_key"),
            raw_json.get("condition_key"),
            trace_json.get("condition_key"),
        )
        if value
    }
    signals = {
        str(value).upper()
        for value in (
            metric.get("signal_type"),
            raw_json.get("signal_type"),
            trace_json.get("signal_type"),
        )
        if value
    }
    result = (conditions, signals)
    if cache is not None:
        cache[cache_key] = result
    return result


def metric_full_scope_matches_hint_context(metric: Mapping[str, Any], legacy_signal_type: str) -> bool:
    expected = {
        "BUY_HINT": ("buy", "B_BUY"),
        "SELL_HINT": ("sell", "S_SELL"),
    }.get(legacy_signal_type)
    if expected is None:
        return False
    expected_direction, expected_runtime_signal = expected
    for row in metric_full_scope_condition_rows(metric):
        condition_tokens = {
            str(value).upper()
            for value in (
                row.get("condition_key"),
                row.get("canonical_condition_type"),
            )
            if value
        }
        allowed_tokens = {str(value).upper() for value in normalize_text_array(row.get("allowed_signal_types"))}
        signal_tokens = {
            str(value).upper()
            for value in (
                row.get("signal_type"),
                row.get("runtime_signal_type"),
            )
            if value
        }
        has_hint_scope = legacy_signal_type in condition_tokens or legacy_signal_type in allowed_tokens
        if not has_hint_scope:
            continue
        direction = str(row.get("direction") or "").lower()
        if direction and direction != expected_direction:
            continue
        if signal_tokens and expected_runtime_signal not in signal_tokens:
            continue
        return True
    return False


def metric_full_scope_condition_rows(metric: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    cache = mutable_local_cache(metric)
    cache_key = "metric_full_scope_condition_rows"
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    rows: list[Mapping[str, Any]] = []
    raw_json = metric.get("raw_json") if isinstance(metric.get("raw_json"), Mapping) else {}
    trace_json = metric.get("trace_json") if isinstance(metric.get("trace_json"), Mapping) else {}
    for container in (metric, raw_json, trace_json):
        value = container.get("full_scope_condition_rows")
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            continue
        rows.extend(item for item in value if isinstance(item, Mapping))
    if cache is not None:
        cache[cache_key] = rows
    return rows


def metric_is_ready(metric: Mapping[str, Any]) -> bool:
    return (
        bool(metric.get("metric_ready"))
        and metric.get("metric_quality_status") == "passed"
        and metric.get("projection_schema_version") in ALLOWED_ACTION_CONFIRMATION_SCHEMA_VERSIONS
        and bool(metric.get("current_price") is not None)
    )


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def decimal_json(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def same_window_30m_amount_pass(*, direction: str, metric: Mapping[str, Any]) -> bool:
    current_amount = decimal_or_none(metric.get("current_30m_virtual_amount"))
    previous_same_window_amount = decimal_or_none(metric.get("previous_day_same_window_amount"))
    if current_amount is None or previous_same_window_amount is None:
        return False
    if previous_same_window_amount <= 0:
        return False
    if direction == "buy":
        return current_amount > previous_same_window_amount
    if direction == "sell":
        return current_amount < previous_same_window_amount
    return False


def virtual_amount_policy_for_period(metric: Mapping[str, Any], period: str) -> Mapping[str, Any]:
    cache = mutable_local_cache(metric)
    cache_key = ("virtual_amount_policy_for_period", period)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    direct_policy = mapping_or_empty(metric.get("metric_policy"))
    if direct_policy:
        if cache is not None:
            cache[cache_key] = direct_policy
        return direct_policy
    for container in (
        metric,
        mapping_or_empty(metric.get("raw_json")),
        mapping_or_empty(metric.get("trace_json")),
    ):
        policy = mapping_or_empty(container.get("virtual_amount_policy"))
        periods = mapping_or_empty(policy.get("periods"))
        period_policy = mapping_or_empty(periods.get(period))
        if period_policy:
            if cache is not None:
                cache[cache_key] = period_policy
            return period_policy
    if cache is not None:
        cache[cache_key] = {}
    return {}


def metric_policy_value(metric: Mapping[str, Any], period: str) -> str:
    direct = metric.get("metric_policy")
    if direct and not isinstance(direct, Mapping):
        return str(direct)
    policy = virtual_amount_policy_for_period(metric, period)
    value = policy.get("metric_policy") or policy.get("policy_version")
    if value:
        return str(value)
    direct_version = metric.get("virtual_amount_policy_version")
    if direct_version and str(metric.get("projection_schema_version") or "") == TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION:
        return str(direct_version)
    raw_json = mapping_or_empty(metric.get("raw_json"))
    raw_value = raw_json.get("virtual_amount_policy_version")
    return str(raw_value or "")


def hint_30m_calibrated_proof_status(*, legacy_signal_type: str, metric: Mapping[str, Any]) -> dict[str, Any]:
    if legacy_signal_type not in {"BUY_HINT", "SELL_HINT"}:
        return {"status": "not_applicable"}
    direction = "buy" if legacy_signal_type == "BUY_HINT" else "sell"
    policy = metric_policy_value(metric, "30m")
    if policy != CALIBRATED_30M_METRIC_POLICY:
        return {
            "status": "failed",
            "reason": "metric_policy_invalid_or_missing",
            "metric_policy": policy or None,
            "required_metric_policy": CALIBRATED_30M_METRIC_POLICY,
        }
    price_flag = "buy_30m_price_pass" if direction == "buy" else "sell_30m_price_pass"
    if metric.get(price_flag) is not True:
        return {
            "status": "failed",
            "reason": f"{price_flag}_false",
            "metric_policy": policy,
            "required_metric_policy": CALIBRATED_30M_METRIC_POLICY,
        }
    current_amount = decimal_or_none(metric.get("current_30m_virtual_amount"))
    previous_amount = decimal_or_none(metric.get("previous_day_same_window_amount"))
    if current_amount is None or previous_amount is None:
        return {
            "status": "failed",
            "reason": "same_window_amount_missing",
            "metric_policy": policy,
            "required_metric_policy": CALIBRATED_30M_METRIC_POLICY,
        }
    if previous_amount <= 0:
        return {
            "status": "failed",
            "reason": "previous_day_same_window_amount_non_positive",
            "metric_policy": policy,
            "required_metric_policy": CALIBRATED_30M_METRIC_POLICY,
        }
    return {
        "status": "passed",
        "metric_policy": policy,
        "required_metric_policy": CALIBRATED_30M_METRIC_POLICY,
        "current_30m_virtual_amount": decimal_json(current_amount),
        "previous_day_same_window_amount": decimal_json(previous_amount),
        "price_flag": price_flag,
        "price_pass": True,
    }


def condition_key_is_hint(condition_key: str) -> bool:
    return str(condition_key or "").upper() in {"BUY_HINT", "SELL_HINT"}


def requested_formal_periods(row: Mapping[str, Any]) -> list[str]:
    condition_key = str(row.get("condition_key") or "").upper()
    requested: list[str] = []
    if ":" in condition_key:
        requested = [part.strip() for part in condition_key.split(":", 1)[1].split(",")]
    if not requested:
        raw_periods = row.get("condition_periods")
        if isinstance(raw_periods, str):
            requested = [part.strip() for part in raw_periods.split(",")]
        elif isinstance(raw_periods, Sequence) and not isinstance(raw_periods, (bytes, bytearray)):
            requested = [str(part).strip() for part in raw_periods]
    if condition_key in {"BUY:FULL", "SELL:FULL"}:
        requested = ["D"]
    allowed = {period for period in requested if period in FORMAL_PERIOD_PRIORITY}
    return [period for period in FORMAL_PERIOD_PRIORITY if period in allowed]


def primary_requested_formal_period(row: Mapping[str, Any]) -> str:
    periods = requested_formal_periods(row)
    return periods[0] if periods else "D"


def mapping_or_empty(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str) and value:
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, Mapping) else {}
    return {}


def mutable_local_cache(value: Mapping[str, Any]) -> dict[Any, Any] | None:
    if not isinstance(value, dict):
        return None
    cache = value.get(_LOCAL_CACHE_KEY)
    if isinstance(cache, dict):
        return cache
    cache = {}
    value[_LOCAL_CACHE_KEY] = cache
    return cache


def period_baseline_json(row: Mapping[str, Any]) -> Mapping[str, Any]:
    cache = mutable_local_cache(row)
    cache_key = "period_baseline_json"
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    baseline = mapping_or_empty(row.get("period_trigger_baseline_json"))
    if baseline:
        if cache is not None:
            cache[cache_key] = baseline
        return baseline
    raw_json = mapping_or_empty(row.get("raw_json"))
    result = mapping_or_empty(raw_json.get("period_trigger_baseline_json"))
    if cache is not None:
        cache[cache_key] = result
    return result


def period_baseline(row: Mapping[str, Any], period: str) -> Mapping[str, Any]:
    cache = mutable_local_cache(row)
    cache_key = ("period_baseline", period)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    baseline = period_baseline_json(row)
    periods = mapping_or_empty(baseline.get("periods"))
    result = mapping_or_empty(periods.get(period))
    if cache is not None:
        cache[cache_key] = result
    return result


def metric_json_block(metric: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    cache = mutable_local_cache(metric)
    cache_key = ("metric_json_block", key)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    direct = mapping_or_empty(metric.get(key))
    if direct:
        if cache is not None:
            cache[cache_key] = direct
        return direct
    raw_json = mapping_or_empty(metric.get("raw_json"))
    raw_value = mapping_or_empty(raw_json.get(key))
    if raw_value:
        if cache is not None:
            cache[cache_key] = raw_value
        return raw_value
    trace_json = mapping_or_empty(metric.get("trace_json"))
    result = mapping_or_empty(trace_json.get(key))
    if cache is not None:
        cache[cache_key] = result
    return result


def true_full_day_minimal_formal_amount_proof(period: str) -> dict[str, Any]:
    current_field = FORMAL_TRANSITION_CURRENT_AMOUNT_FIELDS.get(period, "")
    current_amount_field = FORMAL_AMOUNT_PROOF_ALIAS_FIELDS.get(current_field, "")
    return {
        "source_kind": FORMAL_AMOUNT_SOURCE_KIND,
        "amount_unit": FORMAL_AMOUNT_UNIT,
        "current_amount_unit": FORMAL_AMOUNT_UNIT,
        "current_amount_source_kind": FORMAL_AMOUNT_SOURCE_KIND,
        "current_amount_field": current_amount_field,
        "source_field_trace": {"current_amount_field": current_amount_field},
        "unit_conversion_policy": TRUE_FULL_DAY_MINUTE_SERIES_UNIT_POLICY,
        "schema_adapter": TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION,
    }


def n3_formal_amount_proof_for_period(metric: Mapping[str, Any], period: str) -> Mapping[str, Any]:
    cache = mutable_local_cache(metric)
    cache_key = ("n3_formal_amount_proof_for_period", period)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    proof = metric_json_block(metric, "formal_period_amount_proof")
    if not proof and str(metric.get("projection_schema_version") or "") == TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION:
        result = true_full_day_minimal_formal_amount_proof(period)
        if cache is not None:
            cache[cache_key] = result
        return result
    periods = mapping_or_empty(proof.get("periods"))
    period_proof = mapping_or_empty(periods.get(period))
    if not period_proof:
        if cache is not None:
            cache[cache_key] = proof
        return proof
    merged = dict(proof)
    merged.update(period_proof)
    if cache is not None:
        cache[cache_key] = merged
    return merged


def formal_amount_chain_metrics(metric: Mapping[str, Any]) -> Mapping[str, Any]:
    cache = mutable_local_cache(metric)
    cache_key = "formal_amount_chain_metrics"
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    proof = metric_json_block(metric, "formal_period_amount_proof")
    raw_json = mapping_or_empty(metric.get("raw_json"))
    trace_json = mapping_or_empty(metric.get("trace_json"))
    result = (
        mapping_or_empty(proof.get("amount_chain_metrics"))
        or mapping_or_empty(metric.get("formal_amount_chain_metrics"))
        or mapping_or_empty(raw_json.get("formal_amount_chain_metrics"))
        or mapping_or_empty(trace_json.get("formal_amount_chain_metrics"))
    )
    if cache is not None:
        cache[cache_key] = result
    return result


def formal_amount_chain_value(metric: Mapping[str, Any], field: str) -> Decimal | None:
    direct = decimal_or_none(metric.get(field))
    if direct is not None:
        return direct
    chain_value = decimal_or_none(formal_amount_chain_metrics(metric).get(field))
    if chain_value is not None:
        return chain_value
    true_full_day_value, _ = true_full_day_formal_amount_chain_value(metric, field)
    if true_full_day_value is not None:
        return true_full_day_value
    return formal_amount_proof_v1_chain_value(metric, field)


def true_full_day_formal_amount_chain_value(
    metric: Mapping[str, Any],
    field: str,
) -> tuple[Decimal | None, str | None]:
    if str(metric.get("projection_schema_version") or "") != TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION:
        return None, None
    alias_field = TRUE_FULL_DAY_FORMAL_AMOUNT_CHAIN_FIELD_ALIASES.get(field)
    if alias_field is None:
        return None, None
    chain_value = decimal_or_none(formal_amount_chain_metrics(metric).get(alias_field))
    if chain_value is not None:
        return chain_value, f"formal_amount_chain_metrics.{alias_field}"
    metric_value = decimal_or_none(metric.get(alias_field))
    if metric_value is not None:
        return metric_value, alias_field
    return None, None


def formal_amount_proof_alias_value(metric: Mapping[str, Any], field: str) -> tuple[Decimal | None, str | None]:
    alias_field = FORMAL_AMOUNT_PROOF_ALIAS_FIELDS.get(field)
    if alias_field is None:
        return None, None
    alias_value = decimal_or_none(metric.get(alias_field))
    if alias_value is None:
        return None, None
    return alias_value, alias_field


def formal_amount_proof_trace_value(
    metric: Mapping[str, Any],
    field: str,
    decision_value: Decimal | None,
) -> tuple[Decimal | None, str]:
    if decision_value is not None:
        if decimal_or_none(metric.get(field)) is not None:
            return decision_value, field
        if decimal_or_none(formal_amount_chain_metrics(metric).get(field)) is not None:
            return decision_value, f"formal_amount_chain_metrics.{field}"
        _, true_full_day_source = true_full_day_formal_amount_chain_value(metric, field)
        return decision_value, true_full_day_source or field
    alias_value, alias_field = formal_amount_proof_alias_value(metric, field)
    if alias_value is not None and alias_field is not None:
        return alias_value, alias_field
    true_full_day_value, true_full_day_source = true_full_day_formal_amount_chain_value(metric, field)
    if true_full_day_value is not None and true_full_day_source is not None:
        return true_full_day_value, true_full_day_source
    return None, "missing"


def formal_amount_proof_trace_values(
    metric: Mapping[str, Any],
    values: Mapping[str, Decimal | None],
) -> tuple[dict[str, str | None], dict[str, str]]:
    trace_values: dict[str, str | None] = {}
    trace_sources: dict[str, str] = {}
    for field, decision_value in values.items():
        trace_value, source = formal_amount_proof_trace_value(metric, field, decision_value)
        trace_values[field] = decimal_json(trace_value)
        trace_sources[field] = source
    return trace_values, trace_sources


def formal_amount_alias_trace_values(
    metric: Mapping[str, Any],
    fields: Sequence[str],
) -> tuple[dict[str, str | None], dict[str, str]]:
    alias_values: dict[str, str | None] = {}
    alias_sources: dict[str, str] = {}
    for field in fields:
        alias_value, alias_field = formal_amount_proof_alias_value(metric, field)
        alias_values[field] = decimal_json(alias_value)
        alias_sources[field] = alias_field or "missing"
    return alias_values, alias_sources


def formal_amount_proof_v1_chain_value(metric: Mapping[str, Any], field: str) -> Decimal | None:
    period_config = FORMAL_AMOUNT_PROOF_V1_FIELD_PERIOD.get(field)
    if period_config is None:
        return None
    period, value_kind = period_config
    proof = metric_json_block(metric, "formal_period_amount_proof")
    if str(proof.get("source_kind") or "") != FORMAL_AMOUNT_SOURCE_KIND:
        return None
    if str(proof.get("amount_unit") or "") != FORMAL_AMOUNT_UNIT:
        return None
    if str(proof.get("unit_conversion_policy") or "") != FORMAL_AMOUNT_PROOF_V1_UNIT_CONVERSION_POLICY:
        return None
    period_proof = mapping_or_empty(mapping_or_empty(proof.get("periods")).get(period))
    if value_kind == "current":
        return decimal_or_none(period_proof.get("current_virtual_amount"))
    if value_kind == "previous_avg":
        return decimal_or_none(period_proof.get("previous_avg_amount"))
    current_total = decimal_or_none(period_proof.get("current_virtual_amount"))
    total_units = decimal_or_none(period_proof.get("total_units"))
    if current_total is None or total_units is None or total_units == 0:
        return None
    return current_total / total_units


def formal_transition_previous(row: Mapping[str, Any], baseline: Mapping[str, Any], period: str) -> str | None:
    suffix = period.lower()
    value = (
        baseline.get("previous_transition")
        or baseline.get("period_transition")
        or row.get(f"period_transition_{suffix}")
    )
    text = str(value or "").strip()
    return text or None


def formal_transition_amount_value(
    metric: Mapping[str, Any],
    amount_proof: Mapping[str, Any],
    field: str,
) -> Decimal | None:
    direct = decimal_or_none(metric.get(field))
    if direct is not None:
        return direct
    chain_value = decimal_or_none(formal_amount_chain_metrics(metric).get(field))
    if chain_value is not None:
        return chain_value
    true_full_day_value, _ = true_full_day_formal_amount_chain_value(metric, field)
    if true_full_day_value is not None:
        return true_full_day_value
    proof_value = decimal_or_none(amount_proof.get(field))
    if proof_value is not None:
        return proof_value
    return formal_amount_proof_v1_chain_value(metric, field)


def n2_baseline_amount_unit(
    baseline: Mapping[str, Any],
    field: str,
    *,
    asset_kind: str | None = None,
) -> tuple[str, Decimal, str, str]:
    unit = str(
        baseline.get(f"{field}_unit")
        or baseline.get("previous_amount_unit")
        or baseline.get("previous_avg_amount_unit")
        or baseline.get("amount_unit")
        or ""
    ).strip()
    if not unit:
        normalized_asset_kind = str(asset_kind or "").strip().lower()
        unit = N2_BASELINE_AMOUNT_UNIT_BY_ASSET_KIND.get(normalized_asset_kind, "")
        unit_source = N2_BASELINE_AMOUNT_UNIT_SOURCE_POLICY
    else:
        unit_source = "explicit_baseline_unit"
    if unit == FORMAL_AMOUNT_UNIT:
        return FORMAL_AMOUNT_UNIT, Decimal("1"), N2_AMOUNT_UNIT_PASSTHROUGH_POLICY, unit_source
    if unit == "thousand_yuan":
        return "thousand_yuan", Decimal("1000"), N2_AMOUNT_UNIT_CONVERSION_POLICY, unit_source
    return unit, Decimal("0"), "unsupported_n2_period_trigger_baseline_amount_unit", unit_source


def formal_transition_previous_amount_value(
    baseline: Mapping[str, Any],
    period: str,
    *,
    asset_kind: str | None = None,
) -> tuple[Decimal | None, str | None, dict[str, Any]]:
    for field in FORMAL_TRANSITION_PREVIOUS_AMOUNT_FIELDS.get(period, ()):
        value = decimal_or_none(baseline.get(field))
        if value is None:
            continue
        source_unit, factor, policy, unit_source = n2_baseline_amount_unit(
            baseline,
            field,
            asset_kind=asset_kind,
        )
        canonical_unit = FORMAL_AMOUNT_UNIT if factor > 0 else None
        if factor <= 0:
            return None, None, {
                "source": "N2_period_trigger_baseline",
                "source_field": field,
                "source_unit": source_unit,
                "unit_conversion_policy": policy,
                "n2_baseline_source_amount_unit": source_unit,
                "n2_baseline_canonical_amount_unit": canonical_unit,
                "n2_baseline_unit_conversion_factor": decimal_json(factor),
                "n2_baseline_amount_unit_source": unit_source,
                "raw_value": decimal_json(value),
            }
        return value * factor, "n2_previous_amount_yuan", {
            "source": "N2_period_trigger_baseline",
            "source_field": field,
            "source_unit": source_unit,
            "unit_conversion_policy": policy,
            "n2_baseline_source_amount_unit": source_unit,
            "n2_baseline_canonical_amount_unit": canonical_unit,
            "n2_baseline_unit_conversion_factor": int(factor) if factor == factor.to_integral_value() else decimal_json(factor),
            "n2_baseline_amount_unit_source": unit_source,
            "raw_value": decimal_json(value),
            "forbidden_fields_ignored": list(N2_FORBIDDEN_TRANSITION_AMOUNT_FIELDS),
        }
    return None, None, {
        "source": "N2_period_trigger_baseline",
        "missing_allowed_fields": list(N2_PREVIOUS_TRANSITION_AMOUNT_FIELDS),
        "forbidden_fields_ignored": list(N2_FORBIDDEN_TRANSITION_AMOUNT_FIELDS),
    }


def evaluate_formal_transition_gate(
    *,
    row: Mapping[str, Any],
    baseline: Mapping[str, Any],
    metric: Mapping[str, Any],
    amount_proof: Mapping[str, Any],
    period: str,
    direction: str,
    current_price: Decimal | None,
    previous_high: Decimal | None,
    previous_low: Decimal | None,
) -> dict[str, Any]:
    current_field = FORMAL_TRANSITION_CURRENT_AMOUNT_FIELDS.get(period)
    current_amount = formal_transition_amount_value(metric, amount_proof, current_field or "") if current_field else None
    previous_amount, previous_field, previous_amount_trace = formal_transition_previous_amount_value(
        baseline,
        period,
        asset_kind=str(row.get("asset_kind") or ""),
    )
    previous_transition = formal_transition_previous(row, baseline, period)
    target_transition = FORMAL_BUY_TARGET_TRANSITION if direction == "buy" else FORMAL_SELL_TARGET_TRANSITION
    transition_amount_pass = False
    transition_price_pass = False
    if direction == "buy":
        transition_price_pass = bool(
            current_price is not None and previous_high is not None and current_price > previous_high
        )
        transition_amount_pass = bool(
            current_amount is not None and previous_amount is not None and current_amount > previous_amount
        )
        if transition_price_pass and transition_amount_pass:
            current_transition = "volume_up"
        elif transition_price_pass and current_amount is not None and previous_amount is not None and current_amount < previous_amount:
            current_transition = "low_volume_up"
        else:
            current_transition = "other"
    else:
        transition_price_pass = bool(
            current_price is not None and previous_low is not None and current_price < previous_low
        )
        transition_amount_pass = bool(
            current_amount is not None and previous_amount is not None and current_amount < previous_amount
        )
        if transition_price_pass and transition_amount_pass:
            current_transition = "low_volume_down"
        elif transition_price_pass and current_amount is not None and previous_amount is not None and current_amount > previous_amount:
            current_transition = "volume_down"
        else:
            current_transition = "other"
    transition_upgrade_pass = bool(
        previous_transition is not None
        and previous_transition != target_transition
        and current_transition == target_transition
    )
    missing_fields: list[str] = []
    if previous_transition is None:
        missing_fields.append("previous_transition")
    if current_field is None or current_amount is None:
        missing_fields.append(current_field or "current_transition_amount")
    if previous_field is None or previous_amount is None:
        missing_fields.append("previous_transition_amount")
    current_trace_value, current_trace_source = formal_amount_proof_trace_value(metric, current_field or "", current_amount)
    alias_values, alias_sources = formal_amount_alias_trace_values(
        metric,
        [current_field] if current_field else [],
    )
    return {
        "status": "missing" if missing_fields else "passed",
        "missing_fields": missing_fields,
        "previous_transition": previous_transition,
        "current_transition": current_transition,
        "target_transition": target_transition,
        "transition_price_pass": bool(transition_price_pass),
        "transition_amount_pass": bool(transition_amount_pass),
        "transition_upgrade_pass": bool(transition_upgrade_pass),
        "transition_amount_fields": [field for field in (current_field, previous_field) if field],
        "transition_amount_values": {
            field: decimal_json(value)
            for field, value in (
                (current_field, current_trace_value),
                (previous_field, previous_amount),
            )
            if field
        },
        "transition_amount_value_sources": {
            field: source
            for field, source in (
                (current_field, current_trace_source),
                (previous_field, previous_field or "missing"),
            )
            if field
        },
        "transition_amount_alias_values": alias_values,
        "transition_amount_alias_value_sources": alias_sources,
        "transition_previous_amount_trace": previous_amount_trace,
    }


def formal_amount_chain_unit_proof_status(metric: Mapping[str, Any], period: str) -> dict[str, Any]:
    proof = n3_formal_amount_proof_for_period(metric, period)
    policy = str(proof.get("unit_conversion_policy") or "")
    amount_unit = str(proof.get("current_amount_unit") or proof.get("amount_unit") or "")
    amount_rule = str(proof.get("amount_rule") or "")
    schema_version = str(metric.get("projection_schema_version") or "")
    current_amount_source_kind = str(
        proof.get("current_amount_source_kind")
        or proof.get("source_kind")
        or proof.get("period_amount_source_kind")
        or ""
    )
    current_amount_field = str(
        proof.get("current_amount_field")
        or mapping_or_empty(proof.get("source_field_trace")).get("current_amount_field")
        or ""
    )
    expected_current_amount_field = FORMAL_AMOUNT_PROOF_ALIAS_FIELDS.get(
        FORMAL_TRANSITION_CURRENT_AMOUNT_FIELDS.get(period, "")
    )
    true_full_day_minute_schema_implicit_by_schema = (
        schema_version == TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION
        and str(proof.get("source_kind") or "") == FORMAL_AMOUNT_SOURCE_KIND
        and current_amount_source_kind == FORMAL_AMOUNT_SOURCE_KIND
        and amount_unit == FORMAL_AMOUNT_UNIT
        and bool(current_amount_field)
        and current_amount_field == expected_current_amount_field
        and not amount_rule
    )
    amount_rule_implicit_by_schema = (
        (
            schema_version == FORMAL_AMOUNT_PROOF_SCHEMA_VERSION
            and str(proof.get("source_kind") or "") == FORMAL_AMOUNT_SOURCE_KIND
            and amount_unit == FORMAL_AMOUNT_UNIT
            and policy == FORMAL_AMOUNT_PROOF_V1_UNIT_CONVERSION_POLICY
            and not amount_rule
        )
        or true_full_day_minute_schema_implicit_by_schema
    )
    missing_fields: list[str] = []
    proof_errors: list[str] = []
    if policy not in ALLOWED_FORMAL_AMOUNT_UNIT_CONVERSION_POLICIES and not true_full_day_minute_schema_implicit_by_schema:
        missing_fields.append("unit_conversion_policy")
        proof_errors.append("unit_conversion_policy_mismatch_or_missing")
    if amount_unit != FORMAL_AMOUNT_UNIT:
        missing_fields.append("amount_unit")
        proof_errors.append("amount_unit_mismatch_or_missing")
    if amount_rule != FORMAL_AMOUNT_RULE and not amount_rule_implicit_by_schema:
        missing_fields.append("amount_rule")
        proof_errors.append("amount_rule_mismatch_or_missing")
    if schema_version == TRUE_FULL_DAY_MINUTE_SERIES_SCHEMA_VERSION:
        if str(proof.get("source_kind") or "") != FORMAL_AMOUNT_SOURCE_KIND:
            missing_fields.append("source_kind")
            proof_errors.append("source_kind_mismatch_or_missing")
        if current_amount_source_kind != FORMAL_AMOUNT_SOURCE_KIND:
            missing_fields.append("current_amount_source_kind")
            proof_errors.append("current_amount_source_kind_mismatch_or_missing")
        if not current_amount_field:
            missing_fields.append("current_amount_field")
            proof_errors.append("current_amount_field_missing")
        elif current_amount_field != expected_current_amount_field:
            missing_fields.append("current_amount_field")
            proof_errors.append("current_amount_field_mismatch")
    return {
        "status": "passed" if not proof_errors else "missing",
        "missing_fields": missing_fields,
        "proof_errors": proof_errors,
        "unit_conversion_policy": policy or (
            TRUE_FULL_DAY_MINUTE_SERIES_UNIT_POLICY if true_full_day_minute_schema_implicit_by_schema else None
        ),
        "allowed_unit_conversion_policies": list(ALLOWED_FORMAL_AMOUNT_UNIT_CONVERSION_POLICIES),
        "amount_unit": amount_unit or None,
        "required_amount_unit": FORMAL_AMOUNT_UNIT,
        "amount_rule_proof": amount_rule or (FORMAL_AMOUNT_RULE if amount_rule_implicit_by_schema else None),
        "amount_rule_implicit_by_schema": amount_rule_implicit_by_schema,
        "unit_conversion_policy_implicit_by_schema": true_full_day_minute_schema_implicit_by_schema,
        "current_amount_field_proof": current_amount_field or None,
        "expected_current_amount_field": expected_current_amount_field,
        "current_amount_source_kind_proof": current_amount_source_kind or None,
        "required_amount_rule": FORMAL_AMOUNT_RULE,
    }


def evaluate_formal_amount_chain(*, metric: Mapping[str, Any], period: str, direction: str) -> dict[str, Any]:
    if period == "Y":
        return {
            "status": "not_applicable",
            "amount_pass": None,
            "reason": "year_period_has_no_upper_amount_chain",
            "amount_rule": FORMAL_AMOUNT_RULE,
            "amount_chain_fields": [],
            "amount_chain_values": {},
            "operator_chain": "no_upper_period_chain_noop",
            "trigger_amount_chain_gate": "no_upper_period_chain_noop",
        }
    fields = FORMAL_AMOUNT_CHAIN_FIELDS.get(period)
    if fields is None:
        return {
            "status": "missing",
            "amount_pass": False,
            "reason": "unsupported_formal_amount_chain_period",
            "amount_rule": FORMAL_AMOUNT_RULE,
            "amount_chain_fields": [],
            "amount_chain_values": {},
        }
    unit_proof = formal_amount_chain_unit_proof_status(metric, period)
    if unit_proof["status"] != "passed":
        values = {field: formal_amount_chain_value(metric, field) for field in fields}
        trace_values, trace_sources = formal_amount_proof_trace_values(metric, values)
        alias_values, alias_sources = formal_amount_alias_trace_values(metric, fields)
        return {
            "status": "missing",
            "amount_pass": False,
            "reason": "formal_amount_chain_unit_proof_missing_or_invalid",
            "missing_fields": unit_proof["missing_fields"],
            "proof_errors": unit_proof["proof_errors"],
            "amount_rule": FORMAL_AMOUNT_RULE,
            "amount_chain_fields": list(fields),
            "amount_chain_values": trace_values,
            "amount_chain_value_sources": trace_sources,
            "amount_chain_alias_values": alias_values,
            "amount_chain_alias_value_sources": alias_sources,
            "operator_chain": ">=" if direction == "buy" else "<=",
            "unit_conversion_policy": unit_proof["unit_conversion_policy"],
            "allowed_unit_conversion_policies": unit_proof["allowed_unit_conversion_policies"],
            "amount_unit": unit_proof["amount_unit"],
            "required_amount_unit": unit_proof["required_amount_unit"],
            "amount_rule_proof": unit_proof["amount_rule_proof"],
            "required_amount_rule": unit_proof["required_amount_rule"],
        }
    values = {field: formal_amount_chain_value(metric, field) for field in fields}
    missing = [field for field, value in values.items() if value is None]
    trace_values, trace_sources = formal_amount_proof_trace_values(metric, values)
    alias_values, alias_sources = formal_amount_alias_trace_values(metric, fields)
    if missing:
        return {
            "status": "missing",
            "amount_pass": False,
            "reason": "formal_amount_chain_required_field_missing",
            "missing_fields": missing,
            "amount_rule": FORMAL_AMOUNT_RULE,
            "amount_chain_fields": list(fields),
            "amount_chain_values": trace_values,
            "amount_chain_value_sources": trace_sources,
            "amount_chain_alias_values": alias_values,
            "amount_chain_alias_value_sources": alias_sources,
            "operator_chain": ">=" if direction == "buy" else "<=",
        }
    first, second, third = (values[field] for field in fields)
    if direction == "buy":
        amount_pass = bool(first >= second >= third)
        operator_chain = ">="
    else:
        amount_pass = bool(first <= second <= third)
        operator_chain = "<="
    return {
        "status": "passed",
        "amount_pass": amount_pass,
        "amount_rule": FORMAL_AMOUNT_RULE,
        "amount_chain_fields": list(fields),
        "amount_chain_values": trace_values,
        "amount_chain_value_sources": trace_sources,
        "amount_chain_alias_values": alias_values,
        "amount_chain_alias_value_sources": alias_sources,
        "operator_chain": operator_chain,
        "unit_conversion_policy": unit_proof["unit_conversion_policy"],
        "allowed_unit_conversion_policies": unit_proof["allowed_unit_conversion_policies"],
        "amount_unit": unit_proof["amount_unit"],
        "amount_rule_proof": unit_proof["amount_rule_proof"],
        "amount_rule_implicit_by_schema": unit_proof["amount_rule_implicit_by_schema"],
    }


def trigger_amount_chain_pass_for_period(period: str, amount_chain: Mapping[str, Any]) -> bool | None:
    if period == "Y" and amount_chain.get("status") == "not_applicable":
        return None
    return bool(amount_chain.get("amount_pass"))


def n3_amount_source_ready(metric: Mapping[str, Any], period: str) -> tuple[bool, str | None, str | None, Mapping[str, Any]]:
    proof = n3_formal_amount_proof_for_period(metric, period)
    source_kind = str(
        proof.get("current_amount_source_kind")
        or proof.get("source_kind")
        or proof.get("period_amount_source_kind")
        or ""
    )
    unit = str(proof.get("current_amount_unit") or proof.get("amount_unit") or "")
    return source_kind == FORMAL_AMOUNT_SOURCE_KIND and unit == FORMAL_AMOUNT_UNIT, source_kind or None, unit or None, proof


def baseline_amount_unit_status(baseline: Mapping[str, Any]) -> tuple[bool, str, str | None]:
    unit = str(
        baseline.get("trigger_previous_amount_baseline_unit")
        or baseline.get("trigger_previous_amount_unit")
        or baseline.get("amount_unit")
        or ""
    )
    if not unit:
        return True, FORMAL_AMOUNT_UNIT, BASELINE_AMOUNT_UNIT_COMPAT_POLICY
    return unit == FORMAL_AMOUNT_UNIT, unit, None


def proof_missing_detail(
    *,
    period: str,
    direction: str,
    reason: str,
    baseline: Mapping[str, Any],
    metric: Mapping[str, Any],
    amount_source_kind: str | None = None,
    amount_unit: str | None = None,
) -> dict[str, Any]:
    db_period = period.lower()
    return {
        "period": period,
        "direction": direction,
        "status": "missing",
        "reason": reason,
        "baseline_entity_high_field": "trigger_previous_entity_high",
        "baseline_entity_low_field": "trigger_previous_entity_low",
        "baseline_amount_field": "trigger_previous_amount_baseline",
        "current_price_field": "current_price",
        "amount_rule": FORMAL_AMOUNT_RULE,
        "trigger_previous_entity_high": baseline.get("trigger_previous_entity_high"),
        "trigger_previous_entity_low": baseline.get("trigger_previous_entity_low"),
        "trigger_previous_amount_baseline": baseline.get("trigger_previous_amount_baseline"),
        "current_body_high_field": f"current_{db_period}_body_high",
        "current_body_low_field": f"current_{db_period}_body_low",
        "current_amount_field": "formal_amount_chain",
        "current_body_high": metric.get(f"current_{db_period}_body_high"),
        "current_body_low": metric.get(f"current_{db_period}_body_low"),
        "current_amount": metric.get(f"current_{db_period}_virtual_amount"),
        "current_price": metric.get("current_price"),
        "current_amount_source_kind": amount_source_kind,
        "amount_unit": amount_unit,
    }


def evaluate_formal_period_from_baseline(
    *,
    row: Mapping[str, Any],
    metric: Mapping[str, Any],
    signal_type: str,
    period: str,
) -> dict[str, Any]:
    baseline = period_baseline(row, period)
    db_period = period.lower()
    direction = "buy" if signal_type == "B_BUY" else "sell"
    ready, source_kind, amount_unit, amount_proof = n3_amount_source_ready(metric, period)
    if not ready:
        return proof_missing_detail(
            period=period,
            direction=direction,
            reason="n3_current_amount_source_or_unit_missing",
            baseline=baseline,
            metric=metric,
            amount_source_kind=source_kind,
            amount_unit=amount_unit,
        )
    baseline_unit_ready, baseline_unit, baseline_unit_policy = baseline_amount_unit_status(baseline)
    if not baseline_unit_ready:
        return proof_missing_detail(
            period=period,
            direction=direction,
            reason="n2_trigger_amount_unit_not_compatible",
            baseline=baseline,
            metric=metric,
            amount_source_kind=source_kind,
            amount_unit=amount_unit,
        )
    previous_high = decimal_or_none(baseline.get("trigger_previous_entity_high"))
    previous_low = decimal_or_none(baseline.get("trigger_previous_entity_low"))
    previous_amount = decimal_or_none(baseline.get("trigger_previous_amount_baseline"))
    current_price = decimal_or_none(metric.get("current_price"))
    current_high = decimal_or_none(metric.get(f"current_{db_period}_body_high"))
    current_low = decimal_or_none(metric.get(f"current_{db_period}_body_low"))
    current_amount = decimal_or_none(metric.get(f"current_{db_period}_virtual_amount"))
    amount_chain = evaluate_formal_amount_chain(metric=metric, period=period, direction=direction)
    transition_gate = evaluate_formal_transition_gate(
        row=row,
        baseline=baseline,
        metric=metric,
        amount_proof=amount_proof,
        period=period,
        direction=direction,
        current_price=current_price,
        previous_high=previous_high,
        previous_low=previous_low,
    )
    missing_fields = [
        name
        for name, value in (
            ("trigger_previous_entity_high", previous_high),
            ("trigger_previous_entity_low", previous_low),
            ("current_price", current_price),
        )
        if value is None
    ]
    if amount_chain.get("status") == "missing":
        missing_fields.extend(str(field) for field in amount_chain.get("missing_fields") or ["formal_amount_chain"])
    if transition_gate.get("status") == "missing":
        missing_fields.extend(str(field) for field in transition_gate.get("missing_fields") or ["formal_transition_gate"])
    if missing_fields:
        detail = proof_missing_detail(
            period=period,
            direction=direction,
            reason="formal_period_required_field_missing",
            baseline=baseline,
            metric=metric,
            amount_source_kind=source_kind,
            amount_unit=amount_unit,
        )
        detail.update(amount_chain)
        for key, value in transition_gate.items():
            if key not in {"status", "reason", "missing_fields"}:
                detail[key] = value
        detail["status"] = "missing"
        detail["reason"] = amount_chain.get("reason") or "formal_period_required_field_missing"
        detail["missing_fields"] = list(dict.fromkeys(missing_fields))
        detail["trigger_amount_chain_pass"] = trigger_amount_chain_pass_for_period(period, amount_chain)
        detail["trigger_amount_chain_status"] = amount_chain.get("status")
        detail["trigger_amount_chain_gate"] = amount_chain.get("trigger_amount_chain_gate")
        detail["trigger_amount_chain_fields"] = amount_chain.get("amount_chain_fields") or []
        detail["trigger_amount_chain_values"] = amount_chain.get("amount_chain_values") or {}
        detail["trigger_amount_chain_alias_values"] = amount_chain.get("amount_chain_alias_values") or {}
        detail["trigger_amount_chain_alias_value_sources"] = amount_chain.get("amount_chain_alias_value_sources") or {}
        return detail
    if signal_type == "B_BUY":
        price_pass = current_price > previous_high
    else:
        price_pass = current_price < previous_low
    trigger_amount_chain_pass = trigger_amount_chain_pass_for_period(period, amount_chain)
    transition_upgrade_pass = bool(transition_gate.get("transition_upgrade_pass"))
    if period == "Y" and amount_chain.get("status") == "not_applicable":
        amount_pass = bool(transition_upgrade_pass)
    else:
        amount_pass = bool(transition_upgrade_pass and trigger_amount_chain_pass)
    return {
        "period": period,
        "direction": direction,
        "status": "triggered" if price_pass and amount_pass else "not_triggered",
        "price_pass": bool(price_pass),
        "amount_pass": bool(amount_pass),
        "baseline_entity_high_field": "trigger_previous_entity_high",
        "baseline_entity_low_field": "trigger_previous_entity_low",
        "baseline_amount_field": "trigger_previous_amount_baseline",
        "current_price_field": "current_price",
        "trigger_previous_entity_high": decimal_json(previous_high),
        "trigger_previous_entity_low": decimal_json(previous_low),
        "trigger_previous_amount_baseline": decimal_json(previous_amount),
        "baseline_amount_unit": baseline_unit,
        "baseline_unit_policy": baseline_unit_policy,
        "current_body_high_field": f"current_{db_period}_body_high",
        "current_body_low_field": f"current_{db_period}_body_low",
        "current_amount_field": "formal_amount_chain",
        "current_price": decimal_json(current_price),
        "current_body_high": decimal_json(current_high),
        "current_body_low": decimal_json(current_low),
        "current_amount": decimal_json(current_amount),
        "current_amount_source_kind": source_kind,
        "amount_unit": amount_unit,
        "amount_source_trace": dict(amount_proof),
        "amount_rule": amount_chain.get("amount_rule"),
        "reason": amount_chain.get("reason"),
        "unit_conversion_policy": amount_chain.get("unit_conversion_policy"),
        "allowed_unit_conversion_policies": amount_chain.get("allowed_unit_conversion_policies") or [],
        "amount_rule_proof": amount_chain.get("amount_rule_proof"),
        "amount_rule_implicit_by_schema": bool(amount_chain.get("amount_rule_implicit_by_schema")),
        "amount_chain_status": amount_chain.get("status"),
        "amount_chain_fields": amount_chain.get("amount_chain_fields") or [],
        "amount_chain_values": amount_chain.get("amount_chain_values") or {},
        "amount_chain_value_sources": amount_chain.get("amount_chain_value_sources") or {},
        "amount_chain_alias_values": amount_chain.get("amount_chain_alias_values") or {},
        "amount_chain_alias_value_sources": amount_chain.get("amount_chain_alias_value_sources") or {},
        "operator_chain": amount_chain.get("operator_chain"),
        "previous_transition": transition_gate.get("previous_transition"),
        "current_transition": transition_gate.get("current_transition"),
        "target_transition": transition_gate.get("target_transition"),
        "transition_price_pass": transition_gate.get("transition_price_pass"),
        "transition_amount_pass": transition_gate.get("transition_amount_pass"),
        "transition_upgrade_pass": transition_upgrade_pass,
        "transition_amount_fields": transition_gate.get("transition_amount_fields") or [],
        "transition_amount_values": transition_gate.get("transition_amount_values") or {},
        "transition_amount_value_sources": transition_gate.get("transition_amount_value_sources") or {},
        "transition_amount_alias_values": transition_gate.get("transition_amount_alias_values") or {},
        "transition_amount_alias_value_sources": transition_gate.get("transition_amount_alias_value_sources") or {},
        "transition_previous_amount_trace": transition_gate.get("transition_previous_amount_trace") or {},
        "trigger_amount_chain_pass": trigger_amount_chain_pass,
        "trigger_amount_chain_status": amount_chain.get("status"),
        "trigger_amount_chain_gate": amount_chain.get("trigger_amount_chain_gate"),
        "trigger_amount_chain_fields": amount_chain.get("amount_chain_fields") or [],
        "trigger_amount_chain_values": amount_chain.get("amount_chain_values") or {},
        "trigger_amount_chain_value_sources": amount_chain.get("amount_chain_value_sources") or {},
        "trigger_amount_chain_alias_values": amount_chain.get("amount_chain_alias_values") or {},
        "trigger_amount_chain_alias_value_sources": amount_chain.get("amount_chain_alias_value_sources") or {},
    }


def build_formal_trigger_period_proof_from_baseline(*, row: Mapping[str, Any], metric: Mapping[str, Any]) -> dict[str, Any]:
    signal_type = "B_BUY" if str(row.get("direction") or "") == "buy" else "S_SELL"
    requested = requested_formal_periods(row)
    if not requested:
        return {"status": "missing", "triggered_periods": [], "triggered_period_details": []}
    details = [
        evaluate_formal_period_from_baseline(row=row, metric=metric, signal_type=signal_type, period=period)
        for period in requested
    ]
    triggered = [
        detail["period"]
        for detail in details
        if detail.get("status") == "triggered" and detail.get("period") in FORMAL_PERIOD_PRIORITY
    ]
    if triggered:
        return {
            "status": "passed",
            "triggered_periods": triggered,
            "triggered_period_details": details,
        }
    if any(detail.get("status") == "missing" for detail in details):
        return {"status": "missing", "triggered_periods": [], "triggered_period_details": details}
    return {"status": "empty", "triggered_periods": [], "triggered_period_details": details}


def formal_trigger_period_proof(*, row: Mapping[str, Any], metric: Mapping[str, Any]) -> dict[str, Any]:
    """Return formal N4 period proof for ordinary BUY/SELL candidates.

    Explicit historical proof envelopes are still accepted for compatibility.
    The canonical 20260615+ path builds proof inside N4 from N2 trigger baselines
    plus N3 standard D/W/M/Q/Y action-confirmation metric fields.  N4 does not
    infer periods from condition_key; it evaluates only requested periods with
    trigger_previous_* thresholds and N3-standard amount source proof.
    """

    raw_json = metric.get("raw_json") if isinstance(metric.get("raw_json"), Mapping) else {}
    proof = metric.get("n4_formal_trigger_period_proof")
    if not isinstance(proof, Mapping):
        proof = raw_json.get("n4_formal_trigger_period_proof") if isinstance(raw_json.get("n4_formal_trigger_period_proof"), Mapping) else {}
    baseline_result = build_formal_trigger_period_proof_from_baseline(row=row, metric=metric)
    if baseline_result["status"] != "missing":
        return baseline_result
    allowed_sources = {"rule_v4_matcher", "trigger_previous_baseline", "n4_formal_trigger_period_proof"}
    source = str(proof.get("source") or proof.get("baseline_source") or "")
    if source not in allowed_sources:
        return baseline_result
    requested = set(requested_formal_periods(row))
    raw_periods = proof.get("triggered_periods") or proof.get("formal_triggered_periods") or []
    if isinstance(raw_periods, str):
        raw_periods = [part.strip() for part in raw_periods.split(",")]
    periods = [
        period
        for period in FORMAL_PERIOD_PRIORITY
        if period in requested
        and period in {str(item).strip() for item in raw_periods}
        and period != "Y"
    ]
    details = proof.get("triggered_period_details")
    if not isinstance(details, Sequence) or isinstance(details, (str, bytes, bytearray)):
        details = []
    explicit_result = {
        "status": "passed" if periods else "empty",
        "triggered_periods": periods,
        "triggered_period_details": [dict(item) for item in details if isinstance(item, Mapping)],
    }
    if explicit_result["triggered_periods"]:
        return explicit_result
    return explicit_result


def projection_30m_type_for_metric_candidate(legacy_signal_type: str, metric: Mapping[str, Any]) -> str:
    if legacy_signal_type == "BUY_HINT":
        if (
            hint_30m_calibrated_proof_status(legacy_signal_type=legacy_signal_type, metric=metric).get("status")
            == "passed"
            and same_window_30m_amount_pass(direction="buy", metric=metric)
        ):
            return "volume_up"
    if legacy_signal_type in {"B_BUY", "B_BUY_30M_VOL"}:
        if metric.get("buy_30m_price_pass") is True and same_window_30m_amount_pass(direction="buy", metric=metric):
            return "volume_up"
    if legacy_signal_type == "SELL_HINT":
        if (
            hint_30m_calibrated_proof_status(legacy_signal_type=legacy_signal_type, metric=metric).get("status")
            == "passed"
            and same_window_30m_amount_pass(direction="sell", metric=metric)
        ):
            return "shrink_down"
    if legacy_signal_type in {"S_SELL", "S_SELL_30M_SHRINK"}:
        if metric.get("sell_30m_price_pass") is True and same_window_30m_amount_pass(direction="sell", metric=metric):
            return "shrink_down"
    return "none"


def build_metric_plan(
    *,
    row: Mapping[str, Any],
    metric: Mapping[str, Any],
    legacy_signal_type: str,
    projection_run_id: str,
    plan_status: str,
    output_event_type: str | None,
    data_quality_status: str,
    projection_30m_type: str,
    not_ready_reason: str | None,
    dry_run_reason: str,
    formal_triggered_periods: Sequence[str] | None = None,
    formal_triggered_period_details: Sequence[Mapping[str, Any]] | None = None,
    formal_proof_status: str | None = None,
) -> dict[str, Any]:
    asset_kind = str(row.get("asset_kind") or "")
    identity_key = str(row.get("identity_key") or "")
    direction = str(row.get("direction") or "")
    condition_key = str(row.get("condition_key") or "")
    candidate_signal_type = None if legacy_signal_type in ORDINARY_RUNTIME_SIGNALS else legacy_signal_type
    mapping = canonicalize_trigger_candidate(
        condition_key,
        candidate_signal_type=candidate_signal_type,
        projection_30m_type=projection_30m_type,
    )
    trigger_mark_candidate = mapping.trigger_mark_candidate
    canonical_signal_type = mapping.signal_type
    projection_flag = projection_30m_type in {"volume_up", "shrink_down"}
    trigger_kind = "hint" if condition_key_is_hint(condition_key) else "trigger"
    formal_periods = [
        period
        for period in FORMAL_PERIOD_PRIORITY
        if period in {str(item).strip() for item in (formal_triggered_periods or [])}
    ]
    requested_periods = requested_formal_periods(row)
    if trigger_kind == "hint":
        trigger_period = TRIGGER_PERIOD
        primary_trigger_period = None
        all_trigger_periods: list[str] = []
        triggered_periods: list[str] = []
    else:
        trigger_period = formal_periods[0] if formal_periods and output_event_type == "TriggerMatched" else primary_requested_formal_period(row)
        primary_trigger_period = formal_periods[0] if formal_periods and output_event_type == "TriggerMatched" else None
        all_trigger_periods = list(formal_periods) if output_event_type == "TriggerMatched" else []
        triggered_periods = list(formal_periods) if output_event_type == "TriggerMatched" else []
    trigger_live = output_event_type == "TriggerMatched"
    writes_common_trigger_match = trigger_live
    current_status = "matched" if trigger_live else "pending_market_data"
    trigger_price = metric.get("current_price") if trigger_live else None
    trigger_price_source = "n3_action_confirmation_metric.current_price" if trigger_price is not None else None
    defer_heavy_trace = bool(metric.get(_DEFER_HEAVY_TRACE_KEY))
    source_event_id = str(
        metric.get("source_snapshot_event_id")
        or f"metric_missing:{projection_run_id}:{asset_kind}:{identity_key}:{canonical_signal_type}:{trigger_mark_candidate}"
    )
    metric_id = metric.get("action_confirmation_metric_id")
    raw_id = "|".join(
        [
            projection_run_id,
            source_event_id,
            str(metric_id or "metric_missing"),
            asset_kind,
            identity_key,
            direction,
            canonical_signal_type,
            trigger_mark_candidate,
            legacy_signal_type,
            condition_key,
            plan_status,
        ]
    )
    plan = {
        "plan_id": stable_hash(raw_id, length=32),
        "plan_status": plan_status,
        "output_event_type": output_event_type,
        "would_write_db": False,
        "would_consume_outbox": False,
        "writes_common_trigger_match": writes_common_trigger_match,
        "is_n5_action_entry": writes_common_trigger_match,
        "source_event_id": source_event_id,
        "source_event_type": SOURCE_EVENT_TYPE,
        "source_action_confirmation_metric_id": metric_id,
        "source_projection_run_id": projection_run_id,
        "for_trade_date": row.get("for_trade_date") or metric.get("for_trade_date"),
        "projection_schema_version": metric.get("projection_schema_version") or ACTION_CONFIRMATION_SCHEMA_VERSION,
        "source_snapshot_run_id": metric.get("source_snapshot_run_id"),
        "source_snapshot_event_id": metric.get("source_snapshot_event_id"),
        "source_today_minute_run_id": metric.get("source_today_minute_run_id"),
        "source_previous_day_minute_run_id": metric.get("source_previous_day_minute_run_id"),
        "asset_kind": asset_kind,
        "identity_key": identity_key,
        "direction": direction,
        "signal_type": canonical_signal_type,
        "trigger_mark_candidate": trigger_mark_candidate,
        "condition_key": condition_key,
        "original_condition_key": mapping.original_condition_key,
        "legacy_signal_type": legacy_signal_type,
        "match_basis": "n3_action_confirmation_metric",
        "trigger_price": trigger_price,
        "trigger_price_source": trigger_price_source,
        "trigger_kind": trigger_kind,
        "requested_periods": requested_periods,
        "triggered_periods": triggered_periods,
        "triggered_period_details": [dict(item) for item in (formal_triggered_period_details or [])],
        "formal_triggered_period_details": [dict(item) for item in (formal_triggered_period_details or [])],
        "formal_trigger_period_proof_status": formal_proof_status,
        "trigger_period": trigger_period,
        "trigger_bucket": str(metric.get("metric_minute_label") or "metric_missing"),
        "trigger_live": trigger_live,
        "n5_entry_allowed": bool(trigger_live),
        "previous_trigger_live": False,
        "current_status": current_status,
        "previous_status": "inactive",
        "primary_trigger_period": primary_trigger_period,
        "previous_primary_trigger_period": None,
        "all_trigger_periods": all_trigger_periods,
        "previous_all_trigger_periods": [],
        "projection_30m_flag": projection_flag,
        "projection_30m_type": projection_30m_type,
        "previous_projection_30m_flag": False,
        "previous_projection_30m_type": "none",
        "previous_trigger_mark_candidate": None,
        "state_change_reason": "activated" if trigger_live else "status_changed",
        "data_quality_status": data_quality_status,
        "metric_quality_status": metric.get("metric_quality_status") or "missing",
        "metric_ready": bool(metric.get("metric_ready")),
        "not_ready_reason": not_ready_reason,
        "context_snapshot_id": row.get("trigger_context_id"),
        "source_condition_run_id": row.get("source_condition_run_id"),
        "source_condition_pool_id": row.get("source_condition_pool_id"),
        "source_condition_basis_id": row.get("source_condition_basis_id"),
        "source_minute_target_scope_id": row.get("source_minute_target_scope_id"),
        "source_market_subscription_id": row.get("source_market_subscription_id"),
        "context_hash": row.get("context_hash"),
        "metric_trace": (
            {"deferred": True, "action_confirmation_metric_id": metric_id}
            if defer_heavy_trace
            else build_metric_trace(metric, legacy_signal_type=legacy_signal_type)
        ),
        "period_trigger_baseline_trace": (
            {"deferred": True}
            if defer_heavy_trace
            else build_period_trigger_baseline_trace(row, condition_key, trigger_period)
        ),
        "dry_run_reason": dry_run_reason,
        "lifecycle_state_key_version": LIFECYCLE_STATE_KEY_VERSION,
    }
    plan["lifecycle_state_key"] = lifecycle_state_key(plan)
    return plan


def build_metric_trace(metric: Mapping[str, Any], *, legacy_signal_type: str | None = None) -> dict[str, Any]:
    raw_json = metric.get("raw_json") if isinstance(metric.get("raw_json"), Mapping) else {}
    trace_json = metric.get("trace_json") if isinstance(metric.get("trace_json"), Mapping) else {}
    historical_source_run_id = (
        raw_json.get("historical_closed_minute_source_run_id")
        or trace_json.get("historical_closed_minute_source_run_id")
        or (
            metric.get("source_today_minute_run_id")
            if metric_allows_multiple_source_snapshot_run_ids(metric)
            else None
        )
    )
    return {
        "action_confirmation_metric_id": metric.get("action_confirmation_metric_id"),
        "projection_run_id": metric.get("projection_run_id"),
        "projection_schema_version": metric.get("projection_schema_version"),
        "declared_condition_keys": sorted(metric_declared_condition_scope(metric)[0]),
        "declared_signal_types": sorted(metric_declared_condition_scope(metric)[1]),
        "source_snapshot_run_id": metric.get("source_snapshot_run_id"),
        "source_snapshot_event_id": metric.get("source_snapshot_event_id"),
        "historical_closed_minute_source_run_id": historical_source_run_id,
        "source_today_minute_run_id": metric.get("source_today_minute_run_id"),
        "source_previous_day_minute_run_id": metric.get("source_previous_day_minute_run_id"),
        "fake_realtime_snapshot": bool(raw_json.get("fake_realtime_snapshot") or trace_json.get("fake_realtime_snapshot")),
        "stale_v1_b1_c1_reused": bool(raw_json.get("stale_v1_b1_c1_reused") or trace_json.get("stale_v1_b1_c1_reused")),
        "metric_time": metric.get("metric_time"),
        "metric_minute_label": metric.get("metric_minute_label"),
        "current_price": metric.get("current_price"),
        "current_price_source": metric.get("current_price_source"),
        "current_price_time": metric.get("current_price_time"),
        "previous_120m_body_high": metric.get("previous_120m_body_high"),
        "previous_120m_body_low": metric.get("previous_120m_body_low"),
        "previous_30m_body_high": metric.get("previous_30m_body_high"),
        "previous_30m_body_low": metric.get("previous_30m_body_low"),
        "previous_5m_body_high": metric.get("previous_5m_body_high"),
        "previous_5m_body_low": metric.get("previous_5m_body_low"),
        "previous_1m_body_high": metric.get("previous_1m_body_high"),
        "previous_1m_body_low": metric.get("previous_1m_body_low"),
        "current_1m_amount": metric.get("current_1m_amount"),
        "previous_1m_amount": metric.get("previous_1m_amount"),
        "current_5m_virtual_amount": metric.get("current_5m_virtual_amount"),
        "previous_5m_full_amount": metric.get("previous_5m_full_amount"),
        "current_30m_virtual_amount": metric.get("current_30m_virtual_amount"),
        "previous_day_same_window_amount": metric.get("previous_day_same_window_amount"),
        "previous_30m_full_amount": metric.get("previous_30m_full_amount"),
        "projection_30m_amount_basis": "previous_day_same_window_amount",
        "is_first_1m_of_day": metric.get("is_first_1m_of_day"),
        "is_first_5m_of_day": metric.get("is_first_5m_of_day"),
        "is_first_30m_of_day": metric.get("is_first_30m_of_day"),
        "is_first_120m_of_day": metric.get("is_first_120m_of_day"),
        "first_1m_amount_default_pass": metric.get("first_1m_amount_default_pass"),
        "first_5m_amount_default_pass": metric.get("first_5m_amount_default_pass"),
        "previous_1m_period_source": metric.get("previous_1m_period_source"),
        "previous_5m_period_source": metric.get("previous_5m_period_source"),
        "previous_30m_period_source": metric.get("previous_30m_period_source"),
        "previous_120m_period_source": metric.get("previous_120m_period_source"),
        "boundary_policy_version": metric.get("boundary_policy_version"),
        "buy_120m_price_pass": metric.get("buy_120m_price_pass"),
        "buy_30m_price_pass": metric.get("buy_30m_price_pass"),
        "buy_5m_price_pass": metric.get("buy_5m_price_pass"),
        "buy_5m_amount_pass": metric.get("buy_5m_amount_pass"),
        "buy_1m_price_pass": metric.get("buy_1m_price_pass"),
        "buy_1m_amount_pass": metric.get("buy_1m_amount_pass"),
        "sell_120m_price_pass": metric.get("sell_120m_price_pass"),
        "sell_30m_price_pass": metric.get("sell_30m_price_pass"),
        "sell_5m_price_pass": metric.get("sell_5m_price_pass"),
        "sell_5m_amount_pass": metric.get("sell_5m_amount_pass"),
        "sell_1m_price_pass": metric.get("sell_1m_price_pass"),
        "sell_1m_amount_pass": metric.get("sell_1m_amount_pass"),
        "metric_quality_status": metric.get("metric_quality_status"),
        "metric_ready": metric.get("metric_ready"),
        "source_fact_ids": metric.get("source_fact_ids"),
        "source_minute_refs": metric.get("source_minute_refs"),
        "previous_day_minute_refs": metric.get("previous_day_minute_refs"),
        "formal_period_amount_proof": metric_json_block(metric, "formal_period_amount_proof"),
        "virtual_amount_policy_30m": dict(virtual_amount_policy_for_period(metric, "30m")),
        "hint_30m_calibrated_proof": hint_30m_calibrated_proof_status(
            legacy_signal_type=str(legacy_signal_type or ""),
            metric=metric,
        ),
    }


def summarize_action_confirmation_metric_plans(plans: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    would_trigger = [row for row in plans if row.get("plan_status") == "would_trigger"]
    would_pending = [row for row in plans if row.get("plan_status") == "would_pending"]
    quality_only = [row for row in plans if row.get("plan_status") == "quality_only"]
    state_change_plan_count = sum(1 for row in plans if plan_has_material_trigger_state_change(row))
    by_output_event_type = count_by(plans, "output_event_type")
    planned_output_event_types = dict(by_output_event_type)
    planned_output_event_types["TriggerPendingMarketData"] = 0
    planned_output_event_types.setdefault("TriggerMatched", 0)
    planned_output_event_types.setdefault(STATE_CHANGE_EVENT_TYPE, state_change_plan_count)
    planned_common_event_outbox = int(planned_output_event_types.get("TriggerMatched") or 0) + int(
        planned_output_event_types.get(STATE_CHANGE_EVENT_TYPE) or 0
    )
    lifecycle_state_keys = {
        lifecycle_state_key_tuple(row)
        for row in plans
        if str(row.get("output_event_type") or "") in ALLOWED_OUTPUT_EVENT_TYPES
    }
    return {
        "candidate_count": len(plans),
        "would_trigger_count": len(would_trigger),
        "would_pending_count": len(would_pending),
        "quality_only_count": len(quality_only),
        "by_asset_kind": count_by(plans, "asset_kind"),
        "would_trigger_by_asset_kind": count_by(would_trigger, "asset_kind"),
        "would_pending_by_asset_kind": count_by(would_pending, "asset_kind"),
        "by_signal_type": count_by(plans, "signal_type"),
        "would_trigger_by_signal_type": count_by(would_trigger, "signal_type"),
        "would_pending_by_signal_type": count_by(would_pending, "signal_type"),
        "by_trigger_mark_candidate": count_by(plans, "trigger_mark_candidate"),
        "would_trigger_by_trigger_mark_candidate": count_by(would_trigger, "trigger_mark_candidate"),
        "would_pending_by_trigger_mark_candidate": count_by(would_pending, "trigger_mark_candidate"),
        "by_legacy_signal_type": count_by(plans, "legacy_signal_type"),
        "would_trigger_by_legacy_signal_type": count_by(would_trigger, "legacy_signal_type"),
        "would_pending_by_legacy_signal_type": count_by(would_pending, "legacy_signal_type"),
        "by_output_event_type": by_output_event_type,
        "state_change_plan_count": state_change_plan_count,
        "planned_output_event_types": planned_output_event_types,
        "planned_common_event_outbox": planned_common_event_outbox,
        "planned_common_trigger_state": len(lifecycle_state_keys),
        "dropped_pending_candidate_count": len(would_pending),
        "by_not_ready_reason": count_by(plans, "not_ready_reason"),
        "metric_ready_candidate_count": sum(1 for row in plans if row.get("metric_ready") is True),
        "metric_missing_or_not_ready_candidate_count": sum(
            1 for row in plans if row.get("not_ready_reason") in {"metric_row_missing", "metric_not_ready"}
        ),
        "trigger_live_true_count": sum(1 for row in plans if row.get("trigger_live") is True),
        "pending_trigger_live_false_count": sum(
            1 for row in plans if row.get("current_status") == "pending_market_data" and row.get("trigger_live") is False
        ),
        "canonical_payload_invalid_count": sum(1 for row in plans if canonical_payload_errors(row)),
        "opaque_action_confirmation_payload_count": sum(
            1 for row in plans if "action_confirmation" in (row.get("metric_trace") or {})
        ),
    }


def plan_has_material_trigger_state_change(plan: Mapping[str, Any]) -> bool:
    """Return whether the plan should broadcast a TriggerStateChanged event."""

    return str(plan.get("output_event_type") or "") == STATE_CHANGE_EVENT_TYPE


def normalize_periods_for_state_change(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(str(item) for item in value if str(item))
    return (str(value),)


def build_action_confirmation_metric_quality_items(
    *,
    trigger_context_run_id: str,
    projection_run_id: str,
    source_condition_run_id: str,
    source_subscription_run_id: str,
    source_snapshot_run_id: str,
    for_trade_date: str,
    trigger_run: Mapping[str, Any],
    context_rows: Sequence[Mapping[str, Any]],
    metric_rows: Sequence[Mapping[str, Any]],
    plans: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    before_row_counts: Mapping[str, Mapping[str, Any]] | None,
    after_row_counts: Mapping[str, Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    row_counts_unchanged = True
    if before_row_counts is not None and after_row_counts is not None:
        row_counts_unchanged = before_row_counts == after_row_counts
    forbidden_read_overlap = sorted(
        set(ACTION_CONFIRMATION_METRIC_READ_TABLES) & set(FORBIDDEN_ACTION_CONFIRMATION_METRIC_READ_TABLES)
    )
    stream_counts = summary.get("quality_stream_counts") if isinstance(summary.get("quality_stream_counts"), Mapping) else {}
    if stream_counts:
        matched_unready_count = int(stream_counts.get("matched_unready_count") or 0)
        invalid_canonical_payload_count = int(stream_counts.get("invalid_canonical_payload_count") or 0)
        year_auto_amount_operator_count = int(stream_counts.get("year_auto_amount_operator_count") or 0)
        ordinary_formal_count = int(stream_counts.get("ordinary_formal_count") or 0)
        ordinary_formal_matched_count = int(stream_counts.get("ordinary_formal_matched_count") or 0)
        ordinary_formal_proof_missing_count = int(stream_counts.get("ordinary_formal_proof_missing_count") or 0)
        legacy_runtime_signals = sorted(str(item) for item in (stream_counts.get("legacy_runtime_signals") or []))
    else:
        matched_unready = [row for row in plans if row.get("plan_status") == "would_trigger" and row.get("metric_ready") is not True]
        invalid_canonical_payloads = [row for row in plans if canonical_payload_errors(row)]
        year_auto_amount_operator_plans = [row for row in plans if plan_uses_year_auto_amount_operator(row)]
        ordinary_formal_plans = [row for row in plans if is_ordinary_formal_plan(row)]
        ordinary_formal_matched = [
            row for row in ordinary_formal_plans if str(row.get("output_event_type") or "") == "TriggerMatched"
        ]
        ordinary_formal_proof_missing = [
            row
            for row in ordinary_formal_plans
            if str(row.get("not_ready_reason") or "") == "formal_trigger_period_proof_missing"
        ]
        matched_unready_count = len(matched_unready)
        invalid_canonical_payload_count = len(invalid_canonical_payloads)
        year_auto_amount_operator_count = len(year_auto_amount_operator_plans)
        ordinary_formal_count = len(ordinary_formal_plans)
        ordinary_formal_matched_count = len(ordinary_formal_matched)
        ordinary_formal_proof_missing_count = len(ordinary_formal_proof_missing)
        legacy_runtime_signals = sorted(
            {
                str(row.get("signal_type") or "")
                for row in plans
                if str(row.get("signal_type") or "") not in CANONICAL_SIGNAL_TYPES
            }
        )
    ordinary_formal_all_blocked_by_missing_proof = bool(
        ordinary_formal_count
        and not ordinary_formal_matched_count
        and ordinary_formal_proof_missing_count == ordinary_formal_count
    )
    metric_row_count = int(summary.get("metric_row_count") or len(metric_rows))
    if "metric_lineage_mismatch_count" in summary:
        metric_lineage_mismatch_count = int(summary.get("metric_lineage_mismatch_count") or 0)
    else:
        metric_lineage_mismatch_count = len(
            [
                row for row in metric_rows
                if metric_lineage_errors(
                    row,
                    projection_run_id=projection_run_id,
                    source_condition_run_id=source_condition_run_id,
                    source_subscription_run_id=source_subscription_run_id,
                    source_snapshot_run_id=source_snapshot_run_id,
                    for_trade_date=for_trade_date,
                )
            ]
        )
    return [
        quality_item(
            "P0",
            "passed" if trigger_run.get("run_id") == trigger_context_run_id and trigger_run.get("status") == "passed" else "failed",
            "n4_action_confirmation_metric_context_run_passed",
            "N4 metric dry-run must bind a passed current trigger context run",
            expected=f"{trigger_context_run_id}:passed",
            actual=f"{trigger_run.get('run_id')}:{trigger_run.get('status')}",
        ),
        quality_item(
            "P0",
            "passed" if context_rows else "failed",
            "n4_action_confirmation_metric_context_rows_available",
            "N4 metric dry-run must read local trigger context rows",
            expected=">0",
            actual=str(len(context_rows)),
        ),
        quality_item(
            "P0",
            "passed" if metric_row_count else "failed",
            "n4_action_confirmation_metric_rows_available",
            "N4 metric dry-run must read N3 action-confirmation metric facts",
            expected=">0",
            actual=str(metric_row_count),
        ),
        quality_item(
            "P0",
            "passed" if metric_lineage_mismatch_count == 0 else "failed",
            "n4_action_confirmation_metric_lineage_allowlist",
            "N4 must consume only allowlisted N3 metric lineage",
            expected="0 lineage mismatches",
            actual=str(metric_lineage_mismatch_count),
        ),
        quality_item(
            "P0",
            "passed" if matched_unready_count == 0 else "failed",
            "n4_action_confirmation_metric_ready_only_trigger",
            "Only metric_ready=true and metric_quality_status=passed rows may produce would-trigger plans",
            expected="0 would-trigger unready rows",
            actual=str(matched_unready_count),
        ),
        quality_item(
            "P0",
            "passed" if not forbidden_read_overlap else "failed",
            "n4_action_confirmation_metric_no_forbidden_read_tables",
            "N4 metric dry-run must not read raw minute or old realtime projection tables",
            expected="no forbidden read table overlap",
            actual=",".join(forbidden_read_overlap),
        ),
        quality_item(
            "P0",
            "passed" if row_counts_unchanged else "failed",
            "n4_action_confirmation_metric_no_database_writes",
            "N4 metric dry-run must not write database rows",
            expected="before row counts equal after row counts",
            actual="unchanged" if row_counts_unchanged else "changed",
        ),
        quality_item(
            "P0",
            "passed" if invalid_canonical_payload_count == 0 and not legacy_runtime_signals else "failed",
            "n4_action_confirmation_metric_canonical_payload",
            "Plans must use canonical B_BUY/S_SELL signal_type and trigger_mark_candidate",
            expected="canonical payload errors=0",
            actual=f"errors={invalid_canonical_payload_count} legacy_signal_types={','.join(legacy_runtime_signals)}",
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("opaque_action_confirmation_payload_count") or 0) == 0 else "failed",
            "n4_action_confirmation_metric_no_opaque_payload_proof",
            "N4 must not trust opaque action_confirmation payload proof",
            expected="0 opaque payload proof fields",
            actual=str(summary.get("opaque_action_confirmation_payload_count")),
        ),
        quality_item(
            "P0",
            "passed" if year_auto_amount_operator_count == 0 else "failed",
            "n4_action_confirmation_metric_no_year_auto_amount_operator",
            "Y period has no upper amount chain and must not use always_true_for_Y",
            expected="0 plans with always_true_for_Y",
            actual=str(year_auto_amount_operator_count),
        ),
        quality_item(
            "P0",
            "failed" if ordinary_formal_all_blocked_by_missing_proof else "passed",
            "n4_action_confirmation_metric_ordinary_formal_not_all_missing_proof",
            "Ordinary BUY/SELL/FULL candidates must not all be blocked by formal_trigger_period_proof_missing",
            expected="not all ordinary formal candidates blocked by missing proof",
            actual=(
                f"ordinary_formal={ordinary_formal_count};"
                f"ordinary_formal_matched={ordinary_formal_matched_count};"
                f"formal_proof_missing={ordinary_formal_proof_missing_count}"
            ),
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("planned_common_event_outbox") or 0) <= MAX_LIFECYCLE_EVENT_OUTBOX_COUNT else "failed",
            "n4_action_confirmation_metric_lifecycle_outbox_cap",
            "N4 lifecycle-only replay must cap planned common_event_outbox writes",
            expected=f"<= {MAX_LIFECYCLE_EVENT_OUTBOX_COUNT}",
            actual=str(summary.get("planned_common_event_outbox")),
        ),
        quality_item(
            "P0",
            "passed" if int(summary.get("planned_common_trigger_state") or 0) <= len(context_rows) else "failed",
            "n4_action_confirmation_metric_lifecycle_state_key_cap",
            "N4 lifecycle state rows must not exceed localized context lifecycle keys",
            expected=f"<= context_rows({len(context_rows)})",
            actual=str(summary.get("planned_common_trigger_state")),
        ),
        quality_item(
            "P0",
            "passed",
            "n4_action_confirmation_metric_no_outbox_consumption",
            "Dry-run does not consume N3 outbox or write N4 outbox",
        ),
        quality_item(
            "P0",
            "passed",
            "n4_action_confirmation_metric_no_n5_n6",
            "Dry-run does not enter N5/N6 or decide final action_mark",
        ),
        quality_item(
            "P1",
            "warning" if int(summary.get("would_pending_count") or 0) else "passed",
            "n4_action_confirmation_metric_pending_candidates_dropped",
            "Pending/no-match candidates are audit-only and must not be planned as new runtime outbox events",
            expected="TriggerPendingMarketData planned writes=0",
            actual=(
                f"pending_candidates={summary.get('would_pending_count')};"
                f"planned_trigger_pending={summary.get('planned_output_event_types', {}).get('TriggerPendingMarketData')}"
            ),
        ),
    ]


def is_ordinary_formal_plan(plan: Mapping[str, Any]) -> bool:
    return (
        str(plan.get("signal_type") or "") in ORDINARY_RUNTIME_SIGNALS
        and not condition_key_is_hint(str(plan.get("condition_key") or ""))
    )


def plan_uses_year_auto_amount_operator(plan: Mapping[str, Any]) -> bool:
    for detail in formal_period_details_for_plan(plan):
        if str(detail.get("period") or "") == "Y" and str(detail.get("operator_chain") or "") == "always_true_for_Y":
            return True
    return False


def formal_period_details_for_plan(plan: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    details: list[Mapping[str, Any]] = []
    for key in ("formal_triggered_period_details", "triggered_period_details"):
        raw = plan.get(key)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
            details.extend(item for item in raw if isinstance(item, Mapping))
    return details


def build_action_confirmation_metric_preflight_report(report: Mapping[str, Any]) -> dict[str, Any]:
    quality = report.get("quality") or {}
    summary = report.get("summary") or {}
    p0_count = int(quality.get("p0_count") or 0)
    return {
        "stage": "N4 action-confirmation metric execute preflight",
        "result": "PREFLIGHT_PASS" if p0_count == 0 else "PREFLIGHT_BLOCKED",
        "layer_role": "N4_trigger",
        "execute_authorized": False,
        "execute_authorized_reason": "business execute requires a separate final gate; this runner is dry-run/preflight only",
        "runner_readiness": {
            "ready": p0_count == 0,
            "runner": "scripts/plan_trigger_action_confirmation_metric_dry_run.py",
            "supports_action_confirmation_metric_tables": True,
            "rejects_execute_flag": True,
            "writes_database": False,
        },
        "replay_mode": report.get("replay_mode"),
        "trigger_context_run_id": report.get("trigger_context_run_id"),
        "projection_run_id": report.get("projection_run_id"),
        "source_condition_run_id": report.get("source_condition_run_id"),
        "source_subscription_run_id": report.get("source_subscription_run_id"),
        "source_snapshot_run_id": report.get("source_snapshot_run_id"),
        "for_trade_date": report.get("for_trade_date"),
        "planned_counts": {
            "would_trigger": summary.get("would_trigger_count", 0),
            "would_pending": summary.get("would_pending_count", 0),
            "quality_only": summary.get("quality_only_count", 0),
            "dropped_pending_candidate_count": summary.get("dropped_pending_candidate_count", 0),
            "TriggerMatched": summary.get("planned_output_event_types", {}).get("TriggerMatched", 0),
            "TriggerPendingMarketData": 0,
            "TriggerStateChanged": summary.get("planned_output_event_types", {}).get("TriggerStateChanged", 0),
            "common_trigger_state": summary.get("planned_common_trigger_state", 0),
            "common_event_outbox": summary.get("planned_common_event_outbox", 0),
        },
        "boundary": {
            "reads_only_n3_metric_facts": True,
            "reads_raw_minute_tables": False,
            "assembles_raw_minute_indicators": False,
            "trusts_opaque_action_confirmation_payload": False,
            "writes_common_trigger_run": False,
            "writes_common_trigger_state": False,
            "writes_common_trigger_match": False,
            "writes_common_event_outbox": False,
            "writes_common_event_inbox_or_checkpoint": False,
            "n5_n6_entered": False,
            "worker_started": False,
            "market_data_pulled": False,
            "real_trade": False,
        },
        "quality": quality,
        "summary": summary,
        "next_gate": {
            "allow_final_gate_review": p0_count == 0,
            "allow_business_execute": False,
            "required_before_execute": [
                "separate N4 execute contract/preflight",
                "rollback SQL",
                "user final execute confirmation",
            ],
            "n5_action_execute_allowed": False,
        },
    }


def build_action_confirmation_metric_business_execute_contract(
    report: Mapping[str, Any],
    preflight: Mapping[str, Any],
    *,
    execute_run_id: str = DEFAULT_EXECUTE_RUN_ID,
    rollback_sql_path: str = DEFAULT_EXECUTE_ROLLBACK_SQL_PATH,
    business_execute_runner_ready: bool = False,
    business_execute_runner: str = "",
) -> dict[str, Any]:
    quality = report.get("quality") or {}
    summary = report.get("summary") or {}
    planned = preflight.get("planned_counts") or {}
    p0_count = int(quality.get("p0_count") or 0)
    would_trigger_count = int(summary.get("would_trigger_count") or 0)
    would_pending_count = int(summary.get("would_pending_count") or 0)
    state_change_plan_count = int(summary.get("state_change_plan_count") or 0)
    planned_trigger_matched = int((summary.get("planned_output_event_types") or {}).get("TriggerMatched") or 0)
    planned_state_changed = int((summary.get("planned_output_event_types") or {}).get("TriggerStateChanged") or 0)
    planned_state_count = int(summary.get("planned_common_trigger_state") or 0)
    planned_outbox_count = int(summary.get("planned_common_event_outbox") or 0)
    blockers: list[str] = []
    if report.get("result") != "DRY_RUN_PASS":
        blockers.append("dry_run_not_passed")
    if preflight.get("result") != "PREFLIGHT_PASS":
        blockers.append("dry_run_preflight_not_passed")
    if p0_count != 0:
        blockers.append("dry_run_p0_nonzero")
    if int(planned.get("TriggerMatched") or 0) != planned_trigger_matched:
        blockers.append("trigger_matched_count_mismatch")
    if int(planned.get("TriggerPendingMarketData") or 0) != 0:
        blockers.append("trigger_pending_legacy_event_must_not_write")
    if planned_outbox_count > MAX_LIFECYCLE_EVENT_OUTBOX_COUNT:
        blockers.append("lifecycle_event_outbox_cap_exceeded")
    return {
        "stage": "N4 action-confirmation metric business execute contract",
        "result": "CONTRACT_PASS" if not blockers else "CONTRACT_BLOCKED",
        "layer_role": "N4_trigger",
        "event_schema_version": "v2-canonical-trigger-action-runtime",
        "execution_mode": "n3_action_confirmation_metric_local_context_trigger_execute",
        "execute_run_id": execute_run_id,
        "trigger_context_run_id": report.get("trigger_context_run_id"),
        "projection_run_id": report.get("projection_run_id"),
        "projection_schema_version": report.get("projection_schema_version") or ACTION_CONFIRMATION_SCHEMA_VERSION,
        "source_condition_run_id": report.get("source_condition_run_id"),
        "source_subscription_run_id": report.get("source_subscription_run_id"),
        "source_snapshot_run_id": report.get("source_snapshot_run_id"),
        "for_trade_date": report.get("for_trade_date"),
        "blockers": blockers,
        "input_semantics": {
            "reads_local_n4_context": True,
            "reads_n3_action_confirmation_metric_facts": True,
            "consumes_n3_outbox": False,
            "reads_raw_minute_tables": False,
            "assembles_raw_minute_indicators": False,
            "trusts_opaque_action_confirmation_payload": False,
            "writes_inbox": False,
            "writes_checkpoint": False,
            "pulls_market_data": False,
        },
        "allowed_write_tables_after_final_confirmation": list(ALLOWED_ACTION_CONFIRMATION_METRIC_EXECUTE_WRITE_TABLES),
        "forbidden_write_tables": list(FORBIDDEN_ACTION_CONFIRMATION_METRIC_EXECUTE_WRITE_TABLES),
        "requires_execute_flag": True,
        "requires_user_confirmed_flag": True,
        "expected_writes": {
            "common_trigger_run": 1,
            "common_trigger_quality_item": "execute_quality_rows_only",
            "common_trigger_state": planned_state_count,
            "common_trigger_match": would_trigger_count,
            "common_event_outbox": planned_outbox_count,
            "TriggerMatched": planned_trigger_matched,
            "TriggerPendingMarketData": 0,
            "TriggerStateChanged": planned_state_changed,
        },
        "would_write_by_output_event_type": {
            "TriggerMatched": planned_trigger_matched,
            "TriggerPendingMarketData": 0,
            "TriggerStateChanged": planned_state_changed,
        },
        "canonical_payload_contract": {
            "runtime_signal_type_only": ["B_BUY", "S_SELL"],
            "trigger_mark_candidate_required": True,
            "final_action_mark_written_by_n4": False,
            "pending_market_data_legacy_only": True,
            "matched_trigger_live": True,
            "condition_key_trace_only": True,
        },
        "metric_contract": {
            "metric_ready_false_or_missing": "dropped/no-op unless previous live state can be closed by metric_ready formal no-trigger evidence",
            "n4_decides_final_action_mark": False,
            "n5_final_confirmation_deferred": True,
        },
        "idempotency_gate": {
            "block_if_execute_run_exists": True,
            "block_if_outbox_exists": True,
            "block_if_trigger_match_or_state_exists": True,
            "block_if_inbox_or_checkpoint_refs_exist": True,
            "stable_event_id_required": True,
            "stable_dedup_key_required": True,
        },
        "rollback": {
            "rollback_sql_path": rollback_sql_path,
            "delete_scope": "execute_run_id only",
            "delete_tables": list(ALLOWED_ACTION_CONFIRMATION_METRIC_EXECUTE_WRITE_TABLES),
            "block_if_n5_n6_consumed": True,
            "block_if_outbox_delivering_or_delivered": True,
            "does_not_touch_n2": True,
            "does_not_touch_n3_metric_or_snapshot_or_minute_facts": True,
            "does_not_touch_inbox_or_checkpoint_rows": True,
        },
        "runner_readiness": {
            "dry_run_runner": "scripts/plan_trigger_action_confirmation_metric_dry_run.py",
            "dry_run_runner_rejects_execute": True,
            "business_execute_runner_ready": business_execute_runner_ready,
            "business_execute_runner": business_execute_runner,
            "execute_runner_guarded_by_double_confirmation": business_execute_runner_ready,
            "blocker": "" if business_execute_runner_ready else "dedicated business execute runner is not implemented in this gate",
        },
    }


def build_action_confirmation_metric_execute_final_preflight(
    report: Mapping[str, Any],
    dry_run_preflight: Mapping[str, Any],
    contract: Mapping[str, Any],
    *,
    baseline_summary: Mapping[str, int],
    rollback_sql_exists: bool,
) -> dict[str, Any]:
    quality = report.get("quality") or {}
    p1_count = int(quality.get("p1_count") or 0)
    p2_count = int(quality.get("p2_count") or 0)
    failed_gates: list[str] = []
    if report.get("result") != "DRY_RUN_PASS":
        failed_gates.append("n4_action_confirmation_metric_dry_run_passed")
    if dry_run_preflight.get("result") != "PREFLIGHT_PASS":
        failed_gates.append("n4_action_confirmation_metric_dry_run_preflight_passed")
    if contract.get("result") != "CONTRACT_PASS":
        failed_gates.append("n4_action_confirmation_metric_business_execute_contract_passed")
    if not rollback_sql_exists:
        failed_gates.append("n4_action_confirmation_metric_business_rollback_sql_exists")
    if not target_execute_baseline_is_zero(baseline_summary):
        failed_gates.append("n4_action_confirmation_metric_target_baseline_zero")
    if not bool((contract.get("runner_readiness") or {}).get("business_execute_runner_ready")):
        failed_gates.append("n4_action_confirmation_metric_business_execute_runner_ready")
    quality_items = build_action_confirmation_metric_execute_final_quality_items(
        failed_gates=failed_gates,
        baseline_summary=baseline_summary,
        rollback_sql_exists=rollback_sql_exists,
        contract=contract,
    )
    quality_items.extend(carried_non_blocking_quality_items(report))
    p0_count = sum(1 for item in quality_items if item.get("severity") == "P0" and item.get("status") == "failed")
    return {
        "stage": "N4 action-confirmation metric business execute final preflight",
        "result": "PREFLIGHT_PASS" if p0_count == 0 else "PREFLIGHT_BLOCKED",
        "layer_role": "N4_trigger",
        "execute_authorized": False,
        "execute_authorized_reason": "requires separate explicit user confirmation after all P0 blockers are cleared",
        "execute_run_id": contract.get("execute_run_id"),
        "trigger_context_run_id": report.get("trigger_context_run_id"),
        "projection_run_id": report.get("projection_run_id"),
        "source_condition_run_id": report.get("source_condition_run_id"),
        "source_subscription_run_id": report.get("source_subscription_run_id"),
        "source_snapshot_run_id": report.get("source_snapshot_run_id"),
        "for_trade_date": report.get("for_trade_date"),
        "blockers": failed_gates,
        "planned_writes": contract.get("expected_writes") or {},
        "allowed_write_tables_after_final_confirmation": contract.get("allowed_write_tables_after_final_confirmation") or [],
        "forbidden_write_tables": contract.get("forbidden_write_tables") or [],
        "baseline_summary": dict(baseline_summary),
        "rollback_safety": {
            "rollback_sql_path": (contract.get("rollback") or {}).get("rollback_sql_path"),
            "rollback_sql_exists": rollback_sql_exists,
            "rollback_safe_before_execute": target_execute_baseline_is_zero(baseline_summary),
            "blocks_if_outbox_delivering_or_delivered": True,
            "blocks_after_n5_n6_consumption": True,
            "does_not_touch_n3_facts": True,
        },
        "runner_readiness": contract.get("runner_readiness") or {},
        "quality": {
            "p0_count": p0_count,
            "p1_count": p1_count,
            "p2_count": p2_count,
        },
        "quality_items": quality_items,
        "side_effects": {
            "execute_performed": False,
            "writes_performed": False,
            "event_outbox_written": False,
            "trigger_match_written": False,
            "trigger_state_written": False,
            "common_event_inbox_written": False,
            "checkpoint_written": False,
            "n3_outbox_consumed": False,
            "n5_n6_touched": False,
            "worker_started": False,
            "market_data_pulled": False,
            "real_trade_touched": False,
        },
        "next_gate": {
            "allow_business_execute_user_confirmation": p0_count == 0,
            "required_before_execute": required_before_action_confirmation_metric_execute(p0_count),
            "n5_remains_blocked": True,
        },
    }


def build_action_confirmation_metric_execute_final_quality_items(
    *,
    failed_gates: Sequence[str],
    baseline_summary: Mapping[str, int],
    rollback_sql_exists: bool,
    contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    failed = set(failed_gates)
    return [
        quality_item(
            "P0",
            "failed" if "n4_action_confirmation_metric_dry_run_passed" in failed else "passed",
            "n4_action_confirmation_metric_dry_run_passed",
            "Action-confirmation metric business execute must be based on a passed dry-run",
            expected="DRY_RUN_PASS",
            actual="blocked" if "n4_action_confirmation_metric_dry_run_passed" in failed else "DRY_RUN_PASS",
        ),
        quality_item(
            "P0",
            "failed" if "n4_action_confirmation_metric_dry_run_preflight_passed" in failed else "passed",
            "n4_action_confirmation_metric_dry_run_preflight_passed",
            "Action-confirmation metric dry-run preflight must pass",
            expected="PREFLIGHT_PASS",
            actual="blocked" if "n4_action_confirmation_metric_dry_run_preflight_passed" in failed else "PREFLIGHT_PASS",
        ),
        quality_item(
            "P0",
            "failed" if "n4_action_confirmation_metric_business_execute_contract_passed" in failed else "passed",
            "n4_action_confirmation_metric_business_execute_contract_passed",
            "Business execute contract must pass before final execute gate",
            expected="CONTRACT_PASS",
            actual=str(contract.get("result")),
        ),
        quality_item(
            "P0",
            "failed" if "n4_action_confirmation_metric_target_baseline_zero" in failed else "passed",
            "n4_action_confirmation_metric_target_baseline_zero",
            "Target execute_run_id must have no existing N4 output/inbox/checkpoint/downstream refs",
            expected="all scoped baseline refs=0",
            actual=str(dict(baseline_summary)),
        ),
        quality_item(
            "P0",
            "failed" if "n4_action_confirmation_metric_business_rollback_sql_exists" in failed else "passed",
            "n4_action_confirmation_metric_business_rollback_sql_exists",
            "Business execute rollback SQL must exist before final gate",
            expected="exists",
            actual="exists" if rollback_sql_exists else "missing",
        ),
        quality_item(
            "P0",
            "failed" if "n4_action_confirmation_metric_business_execute_runner_ready" in failed else "passed",
            "n4_action_confirmation_metric_business_execute_runner_ready",
            "Dedicated business execute runner must be implemented and double-confirmation guarded",
            expected="business_execute_runner_ready=true",
            actual=str((contract.get("runner_readiness") or {}).get("business_execute_runner_ready")),
        ),
        quality_item(
            "P0",
            "passed",
            "n4_action_confirmation_metric_no_db_write_in_preflight",
            "Final preflight refresh does not write database rows",
        ),
        quality_item(
            "P0",
            "passed",
            "n4_action_confirmation_metric_no_inbox_checkpoint",
            "Final preflight does not write inbox/checkpoint and does not consume N3 outbox",
        ),
        quality_item(
            "P0",
            "passed",
            "n4_action_confirmation_metric_no_n5_n6",
            "N5/N6 remain blocked and untouched",
        ),
    ]


def carried_non_blocking_quality_items(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    quality = report.get("quality") or {}
    items = quality.get("items") or []
    carried: list[dict[str, Any]] = []
    for item in items:
        severity = str(item.get("severity") or "")
        status = str(item.get("status") or "")
        if severity in {"P1", "P2"} and status in {"warning", "failed"}:
            copied = dict(item)
            copied["details"] = {
                **dict(copied.get("details") or {}),
                "carried_from": "N4 action-confirmation metric dry-run",
                "execute_blocker": False,
            }
            carried.append(copied)
    return carried


def required_before_action_confirmation_metric_execute(p0_count: int) -> list[str]:
    if p0_count == 0:
        return [
            "explicit user confirmation for N4 action-confirmation metric business execute",
            "run scripts/run_trigger_action_confirmation_metric_once.py with --execute --user-confirmed",
            "recheck target execute_run_id baseline remains zero immediately before execute",
            "keep N5/N6 workers stopped and downstream consumption blocked",
        ]
    return [
        "clear all P0 blockers",
        "re-run this final preflight and confirm target baseline is still zero",
        "runner must require --execute and --user-confirmed",
    ]


def target_execute_baseline_is_zero(baseline_summary: Mapping[str, int]) -> bool:
    guarded_keys = (
        "execute_run_common_trigger_run",
        "execute_run_quality",
        "execute_run_state",
        "execute_run_match",
        "execute_run_outbox",
        "execute_run_outbox_delivered_or_delivering",
        "execute_run_inbox",
        "execute_run_checkpoint_refs",
        "downstream_inbox_for_execute_run",
        "downstream_checkpoint_refs",
        "n5_action_run_refs",
    )
    return all(int(baseline_summary.get(key) or 0) == 0 for key in guarded_keys)


def build_action_confirmation_metric_execute_rollback_sql(execute_run_id: str) -> str:
    return f"""-- N4 action-confirmation metric business execute rollback.
-- Scope: execute_run_id={execute_run_id}
-- Use only before downstream N5/N6 consumption. Does not touch N2/N3 facts,
-- N3 action-confirmation metric rows, N3 outbox, or N4 context snapshots.

BEGIN;

DO $$
DECLARE
  v_run_id TEXT := '{execute_run_id}';
  v_count BIGINT;
  v_table TEXT;
BEGIN
  IF current_setting('ashare_v3.allow_n4_action_confirmation_metric_rollback_run_id', true) <> v_run_id THEN
    RAISE EXCEPTION 'hard-fail: set ashare_v3.allow_n4_action_confirmation_metric_rollback_run_id=% before DELETE', v_run_id;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_outbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id
    AND status IN ('delivering', 'delivered');
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 action-confirmation metric rollback blocked: outbox delivered/delivering refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_inbox
  WHERE source_layer = 'N4_trigger'
    AND source_run_id = v_run_id;
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 action-confirmation metric rollback blocked: downstream inbox refs = %', v_count;
  END IF;

  SELECT count(*) INTO v_count
  FROM common_event_consumer_checkpoint
  WHERE source_layer = 'N4_trigger'
    AND checkpoint_payload::text LIKE '%' || v_run_id || '%';
  IF v_count <> 0 THEN
    RAISE EXCEPTION 'N4 action-confirmation metric rollback blocked: downstream checkpoint refs = %', v_count;
  END IF;

  IF to_regclass('public.common_action_run') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_run WHERE source_trigger_run_id = $1'
    INTO v_count
    USING v_run_id;
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 action-confirmation metric rollback blocked: N5 action run refs = %', v_count;
    END IF;
  END IF;

  IF to_regclass('public.common_action_event') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM common_action_event WHERE source_trigger_run_id = $1 OR to_jsonb(common_action_event)::TEXT LIKE $2'
    INTO v_count
    USING v_run_id, '%' || v_run_id || '%';
    IF v_count <> 0 THEN
      RAISE EXCEPTION 'N4 action-confirmation metric rollback blocked: N5 action event refs = %', v_count;
    END IF;
  END IF;

  FOREACH v_table IN ARRAY ARRAY[
    'stock_action_fact',
    'index_action_fact',
    'board_action_fact',
    'user_projection_run',
    'user_signal_projection',
    'user_signal_card',
    'user_notification_queue',
    'user_sim_order',
    'user_sim_position',
    'user_sim_trade',
    'common_position_state',
    'common_position_event',
    'n6_virtual_order',
    'n6_virtual_position',
    'n6_virtual_trade'
  ]
  LOOP
    IF to_regclass('public.' || v_table) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %I WHERE to_jsonb(%I)::TEXT LIKE $1', v_table, v_table)
      INTO v_count
      USING '%' || v_run_id || '%';
      IF v_count <> 0 THEN
        RAISE EXCEPTION 'N4 action-confirmation metric rollback blocked: downstream refs in % = %', v_table, v_count;
      END IF;
    END IF;
  END LOOP;
END $$;

DELETE FROM common_event_outbox
WHERE source_layer = 'N4_trigger'
  AND source_run_id = '{execute_run_id}';

DELETE FROM common_trigger_match
WHERE run_id = '{execute_run_id}';

DELETE FROM common_trigger_state
WHERE run_id = '{execute_run_id}';

DELETE FROM common_trigger_quality_item
WHERE run_id = '{execute_run_id}';

DELETE FROM common_trigger_run
WHERE run_id = '{execute_run_id}';

COMMIT;
"""


def capture_action_confirmation_metric_execute_baseline(dsn: str, execute_run_id: str) -> dict[str, int]:
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_action_confirmation_metric_capture_baseline",
        source_run_id=execute_run_id,
        readonly_expected=True,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        baseline = {
            "execute_run_common_trigger_run": query_count(cur, "common_trigger_run", "run_id = %s", (execute_run_id,)),
            "execute_run_quality": query_count(cur, "common_trigger_quality_item", "run_id = %s", (execute_run_id,)),
            "execute_run_state": query_count(cur, "common_trigger_state", "run_id = %s", (execute_run_id,)),
            "execute_run_match": query_count(cur, "common_trigger_match", "run_id = %s", (execute_run_id,)),
            "execute_run_outbox": query_count(
                cur,
                "common_event_outbox",
                "source_layer = 'N4_trigger' AND source_run_id = %s",
                (execute_run_id,),
            ),
            "execute_run_outbox_delivered_or_delivering": query_count(
                cur,
                "common_event_outbox",
                "source_layer = 'N4_trigger' AND source_run_id = %s AND status IN ('delivering', 'delivered')",
                (execute_run_id,),
            ),
            "execute_run_inbox": query_count(cur, "common_event_inbox", "source_run_id = %s", (execute_run_id,)),
            "execute_run_checkpoint_refs": query_count(
                cur,
                "common_event_consumer_checkpoint",
                "source_layer = 'N4_trigger' AND checkpoint_payload::text LIKE %s",
                (f"%{execute_run_id}%",),
            ),
            "downstream_inbox_for_execute_run": query_count(
                cur,
                "common_event_inbox",
                "source_layer = 'N4_trigger' AND source_run_id = %s",
                (execute_run_id,),
            ),
            "downstream_checkpoint_refs": query_count(
                cur,
                "common_event_consumer_checkpoint",
                "source_layer = 'N4_trigger' AND checkpoint_payload::text LIKE %s",
                (f"%{execute_run_id}%",),
            ),
        }
        if table_exists(cur, "common_action_run"):
            baseline["n5_action_run_refs"] = query_count(
                cur,
                "common_action_run",
                "source_trigger_run_id = %s",
                (execute_run_id,),
            )
        else:
            baseline["n5_action_run_refs"] = 0
        return baseline


def query_count(cur: psycopg.Cursor[dict[str, Any]], table_name: str, where_sql: str, params: Sequence[Any]) -> int:
    if not table_exists(cur, table_name):
        return 0
    cur.execute(f"SELECT count(*) AS row_count FROM {table_name} WHERE {where_sql}", params)
    return int(cur.fetchone()["row_count"])


def table_exists(cur: psycopg.Cursor[dict[str, Any]], table_name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (f"public.{table_name}",))
    return bool(cur.fetchone()["exists"])


def capture_row_counts(dsn: str) -> dict[str, dict[str, Any]]:
    with audited_n4_trigger_connect(
        dsn,
        stage_id="n4_action_confirmation_metric_capture_row_counts",
        source_run_id="action_confirmation_metric_matcher_row_counts",
        readonly_expected=True,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
        row_factory=dict_row,
    ) as conn, conn.cursor() as cur:
        output: dict[str, dict[str, Any]] = {}
        for table_name in ROW_COUNT_GUARD_TABLES:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (f"public.{table_name}",))
            exists = bool(cur.fetchone()["exists"])
            if exists:
                cur.execute(f"SELECT count(*) AS row_count FROM {table_name}")
                row_count = int(cur.fetchone()["row_count"])
            else:
                row_count = 0
            output[table_name] = {
                "exists": exists,
                "row_count": row_count,
                "status": "present" if exists else "missing",
            }
        return output


def count_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = row.get(key)
        if value is None:
            value = "<null>"
        counter[str(value)] += 1
    return dict(sorted(counter.items()))


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    from pathlib import Path
    import json

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_text(path: str, text: str) -> None:
    from pathlib import Path

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def format_action_confirmation_metric_report(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    quality = report.get("quality") or {}
    side_effects = report.get("side_effects") or {}
    return "\n".join(
        [
            "# N4 Action-Confirmation Metric Dry-Run Report",
            "",
            f"- result: {report.get('result')}",
            f"- projection_run_id: {report.get('projection_run_id')}",
            f"- trigger_context_run_id: {report.get('trigger_context_run_id')}",
            f"- source_condition_run_id: {report.get('source_condition_run_id')}",
            f"- for_trade_date: {report.get('for_trade_date')}",
            f"- candidate_count: {summary.get('candidate_count', 0)}",
            f"- would_trigger_count: {summary.get('would_trigger_count', 0)}",
            f"- would_pending_count: {summary.get('would_pending_count', 0)}",
            f"- quality_only_count: {summary.get('quality_only_count', 0)}",
            f"- by_output_event_type: {summary.get('by_output_event_type', {})}",
            f"- by_signal_type: {summary.get('by_signal_type', {})}",
            f"- by_trigger_mark_candidate: {summary.get('by_trigger_mark_candidate', {})}",
            f"- metric_ready_candidate_count: {summary.get('metric_ready_candidate_count', 0)}",
            f"- pending_trigger_live_false_count: {summary.get('pending_trigger_live_false_count', 0)}",
            f"- canonical_payload_invalid_count: {summary.get('canonical_payload_invalid_count', 0)}",
            f"- P0/P1/P2: {quality.get('p0_count', 0)}/{quality.get('p1_count', 0)}/{quality.get('p2_count', 0)}",
            "",
            "## Boundary",
            "",
            f"- writes_database: {side_effects.get('event_outbox_written') or side_effects.get('trigger_match_written') or side_effects.get('trigger_state_written')}",
            f"- consumes_outbox: {side_effects.get('common_event_outbox_consumed')}",
            f"- raw_minute_tables_read: {side_effects.get('raw_minute_tables_read')}",
            f"- market_data_pulled: {side_effects.get('market_data_pulled')}",
            f"- worker_started: {side_effects.get('worker_started')}",
            f"- downstream_layers_touched: {side_effects.get('downstream_layers_touched')}",
            "",
        ]
    )


def format_action_confirmation_metric_preflight(preflight: Mapping[str, Any]) -> str:
    quality = preflight.get("quality") or {}
    planned = preflight.get("planned_counts") or {}
    return "\n".join(
        [
            "# N4 Action-Confirmation Metric Execute Preflight",
            "",
            f"- result: {preflight.get('result')}",
            f"- execute_authorized: {preflight.get('execute_authorized')}",
            f"- projection_run_id: {preflight.get('projection_run_id')}",
            f"- trigger_context_run_id: {preflight.get('trigger_context_run_id')}",
            f"- would_trigger: {planned.get('would_trigger', 0)}",
            f"- would_pending: {planned.get('would_pending', 0)}",
            f"- quality_only: {planned.get('quality_only', 0)}",
            f"- TriggerMatched: {planned.get('TriggerMatched', 0)}",
            f"- TriggerPendingMarketData: {planned.get('TriggerPendingMarketData', 0)}",
            f"- TriggerStateChanged: {planned.get('TriggerStateChanged', 0)}",
            f"- P0/P1/P2: {quality.get('p0_count', 0)}/{quality.get('p1_count', 0)}/{quality.get('p2_count', 0)}",
            "",
            "Business execute remains blocked until a separate final gate.",
            "",
        ]
    )


def format_action_confirmation_metric_business_execute_contract(contract: Mapping[str, Any]) -> str:
    expected = contract.get("expected_writes") or {}
    rollback = contract.get("rollback") or {}
    runner = contract.get("runner_readiness") or {}
    return "\n".join(
        [
            "# N4 Action-Confirmation Metric Business Execute Contract",
            "",
            f"- result: {contract.get('result')}",
            f"- execute_run_id: {contract.get('execute_run_id')}",
            f"- projection_run_id: {contract.get('projection_run_id')}",
            f"- trigger_context_run_id: {contract.get('trigger_context_run_id')}",
            f"- source_condition_run_id: {contract.get('source_condition_run_id')}",
            f"- for_trade_date: {contract.get('for_trade_date')}",
            f"- TriggerMatched: {expected.get('TriggerMatched', 0)}",
            f"- TriggerPendingMarketData: {expected.get('TriggerPendingMarketData', 0)}",
            f"- common_trigger_state: {expected.get('common_trigger_state', 0)}",
            f"- common_trigger_match: {expected.get('common_trigger_match', 0)}",
            f"- common_event_outbox: {expected.get('common_event_outbox', 0)}",
            f"- allowed_write_tables: {contract.get('allowed_write_tables_after_final_confirmation')}",
            f"- forbidden_write_tables: {contract.get('forbidden_write_tables')}",
            f"- consumes_n3_outbox: {(contract.get('input_semantics') or {}).get('consumes_n3_outbox')}",
            f"- writes_inbox: {(contract.get('input_semantics') or {}).get('writes_inbox')}",
            f"- writes_checkpoint: {(contract.get('input_semantics') or {}).get('writes_checkpoint')}",
            f"- rollback_sql_path: {rollback.get('rollback_sql_path')}",
            f"- business_execute_runner_ready: {runner.get('business_execute_runner_ready')}",
            f"- runner_blocker: {runner.get('blocker')}",
            "",
            "This contract does not execute N4 business writes. A separate business execute runner and explicit final confirmation are still required.",
            "",
        ]
    )


def format_action_confirmation_metric_execute_final_preflight(preflight: Mapping[str, Any]) -> str:
    planned = preflight.get("planned_writes") or {}
    quality = preflight.get("quality") or {}
    rollback = preflight.get("rollback_safety") or {}
    runner = preflight.get("runner_readiness") or {}
    return "\n".join(
        [
            "# N4 Action-Confirmation Metric Business Execute Final Preflight",
            "",
            f"- result: {preflight.get('result')}",
            f"- execute_authorized: {preflight.get('execute_authorized')}",
            f"- execute_run_id: {preflight.get('execute_run_id')}",
            f"- projection_run_id: {preflight.get('projection_run_id')}",
            f"- trigger_context_run_id: {preflight.get('trigger_context_run_id')}",
            f"- TriggerMatched: {planned.get('TriggerMatched', 0)}",
            f"- TriggerPendingMarketData: {planned.get('TriggerPendingMarketData', 0)}",
            f"- common_trigger_state: {planned.get('common_trigger_state', 0)}",
            f"- common_trigger_match: {planned.get('common_trigger_match', 0)}",
            f"- common_event_outbox: {planned.get('common_event_outbox', 0)}",
            f"- P0/P1/P2: {quality.get('p0_count', 0)}/{quality.get('p1_count', 0)}/{quality.get('p2_count', 0)}",
            f"- blockers: {preflight.get('blockers')}",
            f"- rollback_sql_path: {rollback.get('rollback_sql_path')}",
            f"- rollback_sql_exists: {rollback.get('rollback_sql_exists')}",
            f"- business_execute_runner_ready: {runner.get('business_execute_runner_ready')}",
            f"- allow_business_execute_user_confirmation: {(preflight.get('next_gate') or {}).get('allow_business_execute_user_confirmation')}",
            "",
            "No database writes are performed by this final preflight.",
            "",
        ]
    )
