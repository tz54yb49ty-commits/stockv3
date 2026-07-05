import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql" / "B_TRACK_V1_virtual_execution_patch_schema.sql"
ROLLBACK = ROOT / "sql" / "B_TRACK_V1_virtual_execution_patch_schema_rollback.sql"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.lower())


def _assert_no_forbidden_sql(sql: str) -> None:
    for token in ("DELETE", "UPDATE", "TRUNCATE", "CASCADE"):
        assert not re.search(rf"\b{token}\b", sql, flags=re.IGNORECASE)


def test_migration_and_rollback_files_exist():
    assert MIGRATION.exists()
    assert ROLLBACK.exists()


def test_migration_only_alters_virtual_order_and_position_event_tables():
    sql = _read(MIGRATION)

    altered_tables = set(
        re.findall(
            r"\balter\s+table\s+(?:if\s+exists\s+)?(?:public\.)?([a-z0-9_]+)",
            sql,
            flags=re.IGNORECASE,
        )
    )

    assert altered_tables == {"n6_virtual_order", "n6_virtual_position_event"}


def test_migration_and_rollback_do_not_use_forbidden_data_mutation_sql():
    _assert_no_forbidden_sql(_read(MIGRATION))
    _assert_no_forbidden_sql(_read(ROLLBACK))


def test_migration_contains_all_v1_virtual_order_patch_columns():
    sql = _normalized(_read(MIGRATION))

    expected_columns = {
        "idempotency_key": "text",
        "source_message_key": "text",
        "source_signal_identity_key": "text",
        "source_condition_key": "text",
        "source_event_time": "timestamptz",
        "source_for_trade_date": "date",
        "source_trade_date": "date",
        "source_monitor_id": "bigint",
        "source_strategy_id": "bigint",
        "source_action_state": "text",
        "source_blocked_reason": "text",
        "source_json": "jsonb default '{}'::jsonb not null",
    }
    for column, column_type in expected_columns.items():
        assert f"add column if not exists {column} {column_type}" in sql


def test_migration_contains_all_v1_virtual_position_event_patch_columns():
    sql = _normalized(_read(MIGRATION))

    expected_columns = {
        "available_quantity_delta": "numeric(24,4) default 0 not null",
        "locked_quantity_delta": "numeric(24,4) default 0 not null",
        "price": "numeric(24,6)",
        "trade_date": "date",
        "available_date": "date",
        "source_order_side": "text",
        "source_for_trade_date": "date",
        "source_trade_date": "date",
        "source_json": "jsonb default '{}'::jsonb not null",
    }
    for column, column_type in expected_columns.items():
        assert f"add column if not exists {column} {column_type}" in sql


def test_migration_uses_date_types_and_rejects_wrong_date_type_text():
    sql = _read(MIGRATION)

    for column in (
        "source_for_trade_date",
        "source_trade_date",
        "trade_date",
        "available_date",
    ):
        assert re.search(rf"\b{column}\s+DATE\b", sql, flags=re.IGNORECASE)

    assert not re.search(r"\bsource_for_trade_date\s+TEXT\b", sql, flags=re.IGNORECASE)
    assert not re.search(r"\btrade_date\s+INTEGER\b", sql, flags=re.IGNORECASE)
    assert not re.search(r"\bavailable_date\s+INTEGER\b", sql, flags=re.IGNORECASE)


def test_migration_contains_principal_account_idempotency_unique_partial_index():
    sql = _normalized(_read(MIGRATION))

    assert "create unique index if not exists ux_b_track_v1_n6_virtual_order_principal_account_idempotency" in sql
    assert "on public.n6_virtual_order (principal_id, virtual_account_id, idempotency_key)" in sql
    assert "where idempotency_key is not null" in sql


def test_migration_contains_catalog_type_preflight():
    sql = _normalized(_read(MIGRATION))

    assert "catalog type preflight" in sql
    assert "information_schema.columns" in sql
    assert "udt_name" in sql
    assert "raise exception" in sql
    for column in (
        "source_for_trade_date",
        "source_trade_date",
        "trade_date",
        "available_date",
        "source_json",
        "available_quantity_delta",
        "locked_quantity_delta",
        "price",
    ):
        assert column in sql


def test_migration_contains_duplicate_idempotency_preflight():
    sql = _normalized(_read(MIGRATION))

    assert "duplicate preflight" in sql
    assert "idempotency_key is not null" in sql
    assert "group by principal_id, virtual_account_id, idempotency_key" in sql
    assert "having count(*) > 1" in sql
    assert "raise exception" in sql


def test_migration_contains_required_check_constraints():
    sql = _normalized(_read(MIGRATION))

    assert "ck_b_track_v1_n6_virtual_order_source_json_object" in sql
    assert "jsonb_typeof(source_json) = 'object'" in sql
    assert "ck_b_track_v1_n6_virtual_order_source_action_state" in sql
    assert "source_action_state in ('eligible','executed','blocked','skipped','expired')" in sql
    assert "ck_b_track_v1_n6_virtual_position_event_source_json_object" in sql
    assert "ck_b_track_v1_n6_virtual_position_event_source_order_side" in sql
    assert "source_order_side in ('buy','sell')" in sql


def test_rollback_contains_business_value_guards():
    sql = _normalized(_read(ROLLBACK))

    for predicate in (
        "idempotency_key is not null",
        "source_message_key is not null",
        "source_signal_identity_key is not null",
        "source_condition_key is not null",
        "source_event_time is not null",
        "source_for_trade_date is not null",
        "source_trade_date is not null",
        "source_monitor_id is not null",
        "source_strategy_id is not null",
        "source_action_state is not null",
        "source_blocked_reason is not null",
        "source_json <> '{}'::jsonb",
        "available_quantity_delta <> 0",
        "locked_quantity_delta <> 0",
        "price is not null",
        "trade_date is not null",
        "available_date is not null",
        "source_order_side is not null",
    ):
        assert predicate in sql


def test_rollback_drops_index_before_constraints_before_columns():
    sql = _normalized(_read(ROLLBACK))

    drop_index_at = sql.index("drop index if exists")
    drop_constraint_at = sql.index("drop constraint if exists")
    drop_column_at = sql.index("drop column if exists")

    assert drop_index_at < drop_constraint_at < drop_column_at


def test_tests_do_not_reference_legacy_b_track_files():
    source = Path(__file__).read_text(encoding="utf-8")
    legacy_marker = "B_TRACK_" + "V2"

    assert legacy_marker not in source
    assert legacy_marker not in str(MIGRATION)
    assert legacy_marker not in str(ROLLBACK)
