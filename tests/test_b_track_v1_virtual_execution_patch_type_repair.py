import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql" / "B_TRACK_V1_virtual_execution_patch_type_repair.sql"
ROLLBACK = ROOT / "sql" / "B_TRACK_V1_virtual_execution_patch_type_repair_rollback.sql"
THIS_FILE = Path(__file__)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.lower())


def _assert_no_forbidden_sql(sql: str) -> None:
    for token in ("DELETE", "UPDATE", "INSERT", "TRUNCATE", "CASCADE"):
        assert not re.search(rf"\b{token}\b", sql, flags=re.IGNORECASE)


def _altered_tables(sql: str) -> set[str]:
    return set(
        re.findall(
            r"\balter\s+table\s+(?:public\.)?([a-z0-9_]+)",
            sql,
            flags=re.IGNORECASE,
        )
    )


def test_type_repair_files_exist():
    assert MIGRATION.exists()
    assert ROLLBACK.exists()
    assert THIS_FILE.exists()


def test_migration_only_alters_virtual_order_and_position_event():
    assert _altered_tables(_read(MIGRATION)) == {
        "n6_virtual_order",
        "n6_virtual_position_event",
    }


def test_migration_contains_old_type_preflight():
    sql = _normalized(_read(MIGRATION))

    assert "old type preflight" in sql
    assert "('n6_virtual_order', 'source_for_trade_date', 'text')" in sql
    assert "('n6_virtual_position_event', 'trade_date', 'int4')" in sql
    assert "('n6_virtual_position_event', 'available_date', 'int4')" in sql
    assert "c.udt_name <> e.expected_udt_name" in sql


def test_migration_contains_empty_business_value_guard():
    sql = _normalized(_read(MIGRATION))

    assert "business value guard" in sql
    assert "source_for_trade_date is not null" in sql
    assert "trade_date is not null" in sql
    assert "available_date is not null" in sql
    assert "raise exception" in sql


def test_migration_contains_dependency_guard():
    sql = _normalized(_read(MIGRATION))

    assert "dependency guard" in sql
    assert "pg_catalog.pg_index" in sql
    assert "pg_catalog.pg_constraint" in sql
    assert "pg_catalog.pg_depend" in sql
    assert "pg_catalog.pg_rewrite" in sql
    assert "pg_catalog.pg_trigger" in sql
    assert "pg_catalog.pg_proc" in sql


def test_migration_uses_drop_column_then_add_column_date():
    sql = _normalized(_read(MIGRATION))

    expected_sequence = [
        "alter table public.n6_virtual_order drop column source_for_trade_date",
        "alter table public.n6_virtual_order add column source_for_trade_date date",
        "alter table public.n6_virtual_position_event drop column trade_date",
        "alter table public.n6_virtual_position_event add column trade_date date",
        "alter table public.n6_virtual_position_event drop column available_date",
        "alter table public.n6_virtual_position_event add column available_date date",
    ]
    for statement in expected_sequence:
        assert statement in sql


def test_migration_forbids_casting_and_data_mutation_sql():
    sql = _read(MIGRATION)

    assert "ALTER COLUMN TYPE" not in sql.upper()
    _assert_no_forbidden_sql(sql)


def test_rollback_contains_date_type_preflight():
    sql = _normalized(_read(ROLLBACK))

    assert "date type preflight" in sql
    assert "('n6_virtual_order', 'source_for_trade_date', 'date')" in sql
    assert "('n6_virtual_position_event', 'trade_date', 'date')" in sql
    assert "('n6_virtual_position_event', 'available_date', 'date')" in sql
    assert "c.udt_name <> e.expected_udt_name" in sql


def test_rollback_contains_empty_business_value_guard():
    sql = _normalized(_read(ROLLBACK))

    assert "business value guard" in sql
    assert "source_for_trade_date is not null" in sql
    assert "trade_date is not null" in sql
    assert "available_date is not null" in sql
    assert "raise exception" in sql


def test_rollback_contains_dependency_guard():
    sql = _normalized(_read(ROLLBACK))

    assert "dependency guard" in sql
    assert "pg_catalog.pg_index" in sql
    assert "pg_catalog.pg_constraint" in sql
    assert "pg_catalog.pg_depend" in sql
    assert "pg_catalog.pg_rewrite" in sql
    assert "pg_catalog.pg_trigger" in sql
    assert "pg_catalog.pg_proc" in sql


def test_rollback_uses_drop_column_then_restores_old_types():
    sql = _normalized(_read(ROLLBACK))

    expected_sequence = [
        "alter table public.n6_virtual_order drop column source_for_trade_date",
        "alter table public.n6_virtual_order add column source_for_trade_date text",
        "alter table public.n6_virtual_position_event drop column trade_date",
        "alter table public.n6_virtual_position_event add column trade_date integer",
        "alter table public.n6_virtual_position_event drop column available_date",
        "alter table public.n6_virtual_position_event add column available_date integer",
    ]
    for statement in expected_sequence:
        assert statement in sql


def test_rollback_forbids_casting_and_data_mutation_sql():
    sql = _read(ROLLBACK)

    assert "ALTER COLUMN TYPE" not in sql.upper()
    _assert_no_forbidden_sql(sql)


def test_test_file_uses_only_current_track_files():
    source = THIS_FILE.read_text(encoding="utf-8")
    legacy_marker = "B_TRACK_" + "V2"

    assert legacy_marker not in source
    assert legacy_marker not in str(MIGRATION)
    assert legacy_marker not in str(ROLLBACK)
