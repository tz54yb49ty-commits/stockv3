"""Execute runner support for N1 condition source activation 20260527.

The module reuses the already verified 20260526 v2 activation mechanics, but
binds them to the 20260527 contract, manifests, source versions, and rollback
scope. PostgreSQL writes only happen through the explicit run-once CLI final
gate.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from ashare_v3.ingestion import condition_source_activation_20260526_v2_execute as base


TRADE_DATE = "20260527"
BATCH_ID = "condition_source_activation_20260527_v1"
TDX_ROOT = Path("/Volumes/MacRaid/tdxdata/tdx")
SOURCE_VERSIONS = {
    "stock_daily_basic": "stock_daily_basic_20260527_v1",
    "stock_financial": "stock_financial_20260527_v1",
    "index_membership": "index_membership_20260527_v1",
    "board_membership": "board_membership_20260527_v1",
}
ACTIVE_SCOPES = {
    "stock_daily_basic": "20260527",
    "stock_financial": "20260527",
    "index_membership": "TDX:20260527",
    "board_membership": "TDX:20260527",
}
DATA_DOMAINS = {
    "stock_daily_basic": "stock",
    "stock_financial": "stock",
    "index_membership": "index",
    "board_membership": "board",
}
EXPECTED_REFERENCE_ROWS = {
    "stock_daily_basic": 5506,
    "stock_financial": 5506,
    "index_membership": 12841,
    "board_membership": 56958,
}
RECENT_ACTIVE_REFERENCE_ROWS = {
    "board_membership": 56872,
}
OFFICIAL_NO_TRADE_IDENTITIES = (
    "stock:BJ:920305",
    "stock:SH:600193",
    "stock:SH:600421",
    "stock:SH:600599",
    "stock:SH:600608",
    "stock:SH:600636",
    "stock:SH:600696",
    "stock:SH:605081",
    "stock:SH:688121",
    "stock:SZ:000004",
    "stock:SZ:000638",
    "stock:SZ:002731",
    "stock:SZ:002808",
    "stock:SZ:002898",
    "stock:SZ:300029",
    "stock:SZ:300550",
    "stock:SZ:300561",
    "stock:SZ:301096",
)
OFFICIAL_NO_TRADE_TS_CODES = {
    "stock:BJ:920305": "920305.BJ",
    "stock:SH:600193": "600193.SH",
    "stock:SH:600421": "600421.SH",
    "stock:SH:600599": "600599.SH",
    "stock:SH:600608": "600608.SH",
    "stock:SH:600636": "600636.SH",
    "stock:SH:600696": "600696.SH",
    "stock:SH:605081": "605081.SH",
    "stock:SH:688121": "688121.SH",
    "stock:SZ:000004": "000004.SZ",
    "stock:SZ:000638": "000638.SZ",
    "stock:SZ:002731": "002731.SZ",
    "stock:SZ:002808": "002808.SZ",
    "stock:SZ:002898": "002898.SZ",
    "stock:SZ:300029": "300029.SZ",
    "stock:SZ:300550": "300550.SZ",
    "stock:SZ:300561": "300561.SZ",
    "stock:SZ:301096": "301096.SZ",
}
STALE_IDENTITY_MANIFEST = (
    {
        "identity_key": "stock:SZ:300114",
        "ts_code": "300114.SZ",
        "superseded_by_identity_key": "stock:SZ:302132",
        "action": "manifest_only_do_not_modify_identity",
        "severity": "P1",
    },
)
ALLOWED_FUTURE_WRITE_TABLES = (
    "common_ingest_batch",
    "common_quality_gate_result",
    "common_active_source_version",
    "stock_daily_basic",
    "stock_financial_metrics_fact",
    "index_membership_fact",
    "board_membership_fact",
)
DEFAULT_PATHS = {
    "contract_json": Path("docs/N1_condition_source_20260527_activation_execute_contract.json"),
    "contract_md": Path("docs/N1_CONDITION_SOURCE_20260527_ACTIVATION_EXECUTE_CONTRACT.md"),
    "preflight_json": Path("docs/N1_condition_source_20260527_activation_execute_preflight.json"),
    "preflight_md": Path("docs/N1_CONDITION_SOURCE_20260527_ACTIVATION_EXECUTE_PREFLIGHT.md"),
    "rollback_sql": Path("sql/N1_condition_source_20260527_activation_rollback.sql"),
}

ConditionSourceActivation20260527Blocked = base.ConditionSourceActivation20260526V2Blocked


@contextmanager
def patched_base() -> Iterator[None]:
    overrides = {
        "TRADE_DATE": TRADE_DATE,
        "BATCH_ID": BATCH_ID,
        "TDX_ROOT": TDX_ROOT,
        "SOURCE_VERSIONS": SOURCE_VERSIONS,
        "ACTIVE_SCOPES": ACTIVE_SCOPES,
        "DATA_DOMAINS": DATA_DOMAINS,
        "EXPECTED_REFERENCE_ROWS": EXPECTED_REFERENCE_ROWS,
        "CONDITION_SOURCE_GAP_IDENTITIES": OFFICIAL_NO_TRADE_IDENTITIES,
        "CONDITION_SOURCE_GAP_TS_CODES": OFFICIAL_NO_TRADE_TS_CODES,
        "ALLOWED_FUTURE_WRITE_TABLES": ALLOWED_FUTURE_WRITE_TABLES,
        "DEFAULT_PATHS": DEFAULT_PATHS,
    }
    previous = {name: getattr(base, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(base, name, value)
        yield
    finally:
        for name, value in previous.items():
            setattr(base, name, value)


def now_iso() -> str:
    return base.now_iso()


def sample_pass_snapshot() -> dict[str, Any]:
    with patched_base():
        snapshot = base.sample_pass_snapshot()
    snapshot["trade_date"] = TRADE_DATE
    snapshot["source_batch_id"] = BATCH_ID
    snapshot["upstream_daily"] = {
        "stock_daily": {"active_source_version": "stock_daily_20260527_v1", "row_count": 5506},
        "index_daily": {"active_source_version": "index_daily_20260527_v1", "row_count": 83},
        "board_daily": {"active_source_version": "board_daily_20260527_v1", "row_count": 428},
    }
    snapshot["stock_scope"] = {
        "active_stock_identity_rows": 5525,
        "official_daily_stock_rows": 5506,
        "condition_stock_rows": 5506,
        "condition_source_gap_manifest_rows": 0,
        "condition_source_gap_manifest": official_no_trade_manifest(),
        "official_no_trade_manifest": official_no_trade_manifest(),
        "stale_identity_manifest": list(STALE_IDENTITY_MANIFEST),
    }
    snapshot["membership_tdx"]["index_membership"].update(
        {
            "raw_rows": 12841,
            "filtered_rows": 12841,
            "missing_index_identity": 0,
            "missing_stock_identity": 0,
            "unmapped_raw_count": 0,
            "unmapped_unique_identity_count": 0,
            "duplicate_rows": 0,
        }
    )
    snapshot["membership_tdx"]["board_membership"].update(
        {
            "raw_rows": 56970,
            "filtered_rows": 56958,
            "missing_board_identity": 0,
            "missing_stock_identity": 8,
            "unmapped_raw_count": 12,
            "unmapped_unique_identity_count": 8,
            "duplicate_rows": 0,
        }
    )
    snapshot["current_target_fact_rows"] = {
        "stock_daily_basic": 0,
        "stock_financial": 0,
        "index_membership": 0,
        "board_membership": 0,
    }
    snapshot["target_source_version_conflicts"] = dict(snapshot["current_target_fact_rows"])
    snapshot["active_target_source_versions"] = []
    snapshot["contract_batch_exists"] = False
    return snapshot


def build_snapshot_from_db(
    *,
    dsn: str,
    trade_date: str = TRADE_DATE,
    tdx_root: str | Path = TDX_ROOT,
) -> dict[str, Any]:
    with patched_base():
        snapshot = base.build_snapshot_from_db(dsn=dsn, trade_date=trade_date, tdx_root=tdx_root)
    stock_scope = snapshot.setdefault("stock_scope", {})
    stock_scope["official_no_trade_manifest"] = official_no_trade_manifest()
    stock_scope["stale_identity_manifest"] = list(STALE_IDENTITY_MANIFEST)
    return base.normalize_jsonable(snapshot)


def official_no_trade_manifest() -> list[dict[str, Any]]:
    return [
        {
            "identity_key": identity_key,
            "ts_code": OFFICIAL_NO_TRADE_TS_CODES[identity_key],
            "reason": "official_no_trade_suspend_d_bak_daily_zero_volume",
            "daily_bar_available": False,
            "condition_source_available": False,
            "tushare_suspend_d_present": True,
            "bak_daily_zero_volume_present": True,
            "action": "exclude_from_condition_universe",
            "severity": "P1",
        }
        for identity_key in OFFICIAL_NO_TRADE_IDENTITIES
    ]


def build_expected_rows(snapshot: Mapping[str, Any]) -> dict[str, int]:
    with patched_base():
        return base.build_expected_rows(snapshot)


def _quality_with_20260527_manifests(items: list[dict[str, Any]], snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    adjusted: list[dict[str, Any]] = []
    for item in items:
        item = dict(item)
        if item.get("gate_name") == "condition_source_gap_manifest":
            item["gate_name"] = "official_no_trade_excluded_from_condition_universe"
            item["expected_value"] = "0 official no-trade rows required in condition source"
            item["actual_value"] = str(len(official_no_trade_manifest()))
            item["details"] = {"manifest": official_no_trade_manifest(), "writes_target_fact": False}
        elif item.get("gate_name") == "target_fact_already_exists":
            item["expected_value"] = "0 existing 20260527 target fact rows"
        adjusted.append(item)

    adjusted.append(
        base.plain_quality_item(
            "stale_identity_manifest_only",
            "P1",
            "warning",
            0,
            len(STALE_IDENTITY_MANIFEST),
            {"manifest": list(STALE_IDENTITY_MANIFEST), "writes_identity": False},
        )
    )
    board_rows = int(((snapshot.get("membership_tdx") or {}).get("board_membership") or {}).get("filtered_rows") or 0)
    if board_rows != RECENT_ACTIVE_REFERENCE_ROWS["board_membership"]:
        adjusted.append(
            base.plain_quality_item(
                "board_membership_row_count_changed_from_recent_active",
                "P1",
                "warning",
                RECENT_ACTIVE_REFERENCE_ROWS["board_membership"],
                board_rows,
                {"action": "reviewed_against_current_local_tdx_txt", "blocking": False},
            )
        )
    return adjusted


def build_quality_items(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    with patched_base():
        items = base.build_quality_items(snapshot)
    return base.normalize_jsonable(_quality_with_20260527_manifests(items, snapshot))


def summarize_quality(items: list[Mapping[str, Any]]) -> dict[str, int]:
    return base.summarize_quality(items)


def build_blockers(quality_items: list[Mapping[str, Any]]) -> list[str]:
    return base.build_blockers(quality_items)


def build_execute_preflight_report(
    snapshot: Mapping[str, Any],
    *,
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    quality_items = build_quality_items(snapshot)
    quality = summarize_quality(quality_items)
    blockers = build_blockers(quality_items)
    if execute_requested and not user_confirmed:
        blockers.append("missing_user_confirmed")
    if execute_requested and user_confirmed and not postgres_commit_enabled:
        blockers.append("postgres_commit_disabled")
    blockers = sorted(dict.fromkeys(blockers))
    return base.normalize_jsonable(
        {
            "stage": "N1 condition source activation 20260527 execute preflight",
            "layer_role": "N1_ingestion",
            "result": "PREFLIGHT_BLOCKED" if blockers else "PREFLIGHT_PASS",
            "blocked": bool(blockers),
            "blockers": blockers,
            "trade_date": TRADE_DATE,
            "source_batch_id": BATCH_ID,
            "source_versions": dict(SOURCE_VERSIONS),
            "expected_rows": build_expected_rows(snapshot),
            "baseline": {
                "current_target_fact_rows": snapshot.get("current_target_fact_rows") or {},
                "active_target_source_versions": snapshot.get("active_target_source_versions") or [],
                "target_source_version_conflicts": snapshot.get("target_source_version_conflicts") or {},
                "contract_batch_exists": bool(snapshot.get("contract_batch_exists")),
                "event_counts": snapshot.get("event_counts") or {},
            },
            "quality": quality,
            "quality_items": quality_items,
            "runner_readiness": "blocked" if blockers else "ready_for_final_gate",
            "execute_authorized": False,
            "final_gate_required": True,
            "final_execute_gate_allowed": not bool(blockers),
            "execute_runner_implemented": True,
            "postgres_commit_implemented": True,
            "execute_flags_seen": {
                "execute": bool(execute_requested),
                "user_confirmed": bool(user_confirmed),
                "postgres_commit_enabled": bool(postgres_commit_enabled),
            },
            "expected_future_writes": {
                "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
                "writes_postgres": True,
                "writes_parquet": False,
                "updates_active_source_version": True,
                "writes_outbox": False,
                "enters_n2_n3_n4_n5_n6": False,
            },
            "execute_command_template": (
                "PYTHONPATH=src python3 scripts/run_condition_source_activation_20260527_once.py "
                "--execute --user-confirmed --postgres-commit-enabled"
            ),
            "side_effects": base.no_side_effects(),
            "rollback_sql_path": str(DEFAULT_PATHS["rollback_sql"]),
            "generated_at": now_iso(),
        }
    )


def build_execute_contract(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    quality_items = build_quality_items(snapshot)
    quality = summarize_quality(quality_items)
    blockers = build_blockers(quality_items)
    return base.normalize_jsonable(
        {
            "stage": "N1 condition source activation 20260527 execute contract",
            "layer_role": "N1_ingestion",
            "result": "BLOCKED" if blockers else "DESIGN_PASS",
            "trade_date": TRADE_DATE,
            "source_batch_id": BATCH_ID,
            "source_versions": dict(SOURCE_VERSIONS),
            "active_scopes": dict(ACTIVE_SCOPES),
            "expected_rows": build_expected_rows(snapshot),
            "official_no_trade_manifest": official_no_trade_manifest(),
            "stale_identity_manifest": list(STALE_IDENTITY_MANIFEST),
            "future_write_scope": {
                "allowed_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
                "forbidden_scope": [
                    "stock_daily_bar_fact",
                    "index_daily_bar_fact",
                    "board_daily_bar_fact",
                    "Parquet",
                    "common_event_outbox",
                    "common_event_inbox",
                    "common_event_consumer_checkpoint",
                    "N2/N3/N4/N5/N6",
                    "worker",
                    "old_system",
                    "real_trading",
                ],
            },
            "execute_flags": ["--execute", "--user-confirmed", "--postgres-commit-enabled"],
            "implementation_status": {
                "execute_runner_implemented": True,
                "source_row_builder": True,
                "source_bundle_validation": True,
                "postgres_commit_transaction": True,
                "cli_execute_pipeline_wired": True,
                "execute_authorized": False,
                "final_execute_gate_allowed": not bool(blockers),
            },
            "quality": quality,
            "quality_items": quality_items,
            "rollback": {
                "rollback_safe": True,
                "rollback_sql_path": str(DEFAULT_PATHS["rollback_sql"]),
            },
            "generated_at": now_iso(),
        }
    )


class DefaultConditionSourceActivation20260527SourceBuilder:
    def __init__(self, *, tdx_root: str | Path = TDX_ROOT, tushare_token: str | None = None) -> None:
        self._builder = base.DefaultConditionSourceActivation20260526V2SourceBuilder(
            tdx_root=tdx_root,
            tushare_token=tushare_token,
        )

    def build_source_bundle(self, *, dsn: str, trade_date: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        with patched_base():
            bundle = self._builder.build_source_bundle(dsn=dsn, trade_date=trade_date, snapshot=snapshot)
        manifests = dict(bundle.get("manifests") or {})
        manifests["official_no_trade_manifest"] = official_no_trade_manifest()
        manifests["stale_identity_manifest"] = list(STALE_IDENTITY_MANIFEST)
        bundle["manifests"] = manifests
        return base.normalize_jsonable(bundle)


def validate_execute_request(
    *,
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> None:
    base.validate_execute_request(
        execute_requested=execute_requested,
        user_confirmed=user_confirmed,
        postgres_commit_enabled=postgres_commit_enabled,
    )


def validate_source_bundle(*, bundle: Mapping[str, Any], snapshot: Mapping[str, Any]) -> dict[str, Any]:
    with patched_base():
        report = base.validate_source_bundle(bundle=bundle, snapshot=snapshot)
    quality_items = _quality_with_20260527_manifests(list(report.get("quality_items") or []), snapshot)
    quality = summarize_quality(quality_items)
    report = dict(report)
    report["quality_items"] = quality_items
    report["quality"] = quality
    report["p0_count"] = quality["p0_count"]
    report["result"] = "VALIDATION_PASS" if quality["p0_count"] == 0 else "VALIDATION_BLOCKED"
    return base.normalize_jsonable(report)


def validate_commit_preconditions(
    *,
    snapshot: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    postgres_commit_enabled: bool,
) -> None:
    blockers = build_blockers(build_quality_items(snapshot))
    if not postgres_commit_enabled:
        blockers.append("postgres_commit_disabled")
    if int(validation_report.get("p0_count") or 0) != 0:
        blockers.extend(str(blocker) for blocker in validation_report.get("blockers") or ["source_validation_p0"])
    if blockers:
        raise ConditionSourceActivation20260527Blocked(", ".join(sorted(dict.fromkeys(blockers))))


def build_commit_plan(
    *,
    bundle: Mapping[str, Any],
    validation_report: Mapping[str, Any],
    baseline: Mapping[str, Any],
) -> dict[str, Any]:
    with patched_base():
        plan = base.build_commit_plan(bundle=bundle, validation_report=validation_report, baseline=baseline)
    for row in plan.get("active_source_version_rows") or []:
        row["activated_by"] = "n1_condition_source_activation_20260527_execute_runner"
    plan["manifests"] = {
        **(plan.get("manifests") or {}),
        "official_no_trade_manifest": official_no_trade_manifest(),
        "stale_identity_manifest": list(STALE_IDENTITY_MANIFEST),
    }
    return base.normalize_jsonable(plan)


def execute_commit_transaction(
    conn: Any,
    *,
    commit_plan: Mapping[str, Any],
    execute_requested: bool,
    user_confirmed: bool,
    postgres_commit_enabled: bool,
) -> dict[str, Any]:
    validate_execute_request(
        execute_requested=execute_requested,
        user_confirmed=user_confirmed,
        postgres_commit_enabled=postgres_commit_enabled,
    )
    unexpected_tables = sorted(set(commit_plan.get("allowed_tables") or []) - set(ALLOWED_FUTURE_WRITE_TABLES))
    if unexpected_tables:
        raise ConditionSourceActivation20260527Blocked(f"unexpected write tables: {unexpected_tables}")
    cur = conn.cursor()
    try:
        insert_ingest_batch(cur, commit_plan)
        base.insert_stock_daily_basic_rows(cur, (commit_plan.get("rows") or {}).get("stock_daily_basic") or [])
        base.insert_stock_financial_rows(cur, (commit_plan.get("rows") or {}).get("stock_financial") or [])
        base.insert_index_membership_rows(cur, (commit_plan.get("rows") or {}).get("index_membership") or [])
        base.insert_board_membership_rows(cur, (commit_plan.get("rows") or {}).get("board_membership") or [])
        base.insert_quality_rows(cur, commit_plan.get("quality_rows") or [])
        base.insert_active_source_version_rows(cur, commit_plan.get("active_source_version_rows") or [])
        with patched_base():
            base.update_ingest_batch_passed(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return base.normalize_jsonable(
        {
            "committed": True,
            "batch_id": commit_plan.get("batch_id"),
            "written_tables": list(ALLOWED_FUTURE_WRITE_TABLES),
            "row_counts": commit_plan.get("row_counts") or {},
            "rollback_safe": True,
            "rollback_sql_path": str(DEFAULT_PATHS["rollback_sql"]),
        }
    )


def insert_ingest_batch(cur: Any, commit_plan: Mapping[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO common_ingest_batch (
          batch_id, trade_date, data_domain, data_type, source, source_version,
          source_path, source_params, raw_hash, row_count, error_count,
          quality_gate_summary, error_summary, rollback_strategy, status, started_at
        )
        VALUES (
          %(batch_id)s, %(trade_date)s, 'common', 'condition_source_activation',
          'n1.condition_source_activation.20260527.v1', %(source_version)s,
          NULL, %(source_params)s, NULL, %(row_count)s, 0,
          %(quality_gate_summary)s, NULL, %(rollback_strategy)s, 'running', now()
        )
        """,
        {
            "batch_id": BATCH_ID,
            "trade_date": TRADE_DATE,
            "source_version": BATCH_ID,
            "source_params": base.jsonb_payload(
                {"source_versions": SOURCE_VERSIONS, "active_scopes": ACTIVE_SCOPES},
                context="common_ingest_batch.source_params",
            ),
            "row_count": int((commit_plan.get("row_counts") or {}).get("total") or 0),
            "quality_gate_summary": base.jsonb_payload(
                {
                    "expected_rows": commit_plan.get("row_counts") or {},
                    "official_no_trade_manifest_rows": len(official_no_trade_manifest()),
                    "stale_identity_manifest_rows": len(STALE_IDENTITY_MANIFEST),
                    "board_unmapped_raw_count": (commit_plan.get("manifests") or {}).get("board_unmapped_raw_count"),
                },
                context="common_ingest_batch.quality_gate_summary",
            ),
            "rollback_strategy": str(DEFAULT_PATHS["rollback_sql"]),
        },
    )


def write_preflight_files(report: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    Path(json_path).write_text(
        base.json.dumps(base.normalize_jsonable(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    Path(markdown_path).write_text(render_preflight_markdown(report), encoding="utf-8")


def write_contract_files(contract: Mapping[str, Any], *, json_path: str | Path, markdown_path: str | Path) -> None:
    Path(json_path).write_text(
        base.json.dumps(base.normalize_jsonable(contract), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    Path(markdown_path).write_text(render_contract_markdown(contract), encoding="utf-8")


def render_preflight_markdown(report: Mapping[str, Any]) -> str:
    return f"""# N1 Condition Source 20260527 Activation Preflight

Result: `{report["result"]}`

- runner_readiness: `{report["runner_readiness"]}`
- execute_runner_implemented: `{report["execute_runner_implemented"]}`
- postgres_commit_implemented: `{report["postgres_commit_implemented"]}`
- execute_authorized: `{report["execute_authorized"]}`
- final_execute_gate_allowed: `{report["final_execute_gate_allowed"]}`
- P0/P1/P2: `{report["quality"]["p0_count"]}/{report["quality"]["p1_count"]}/{report["quality"]["p2_count"]}`

Expected rows:

```json
{base.json.dumps(report["expected_rows"], ensure_ascii=False, indent=2)}
```

Rollback SQL: `{DEFAULT_PATHS["rollback_sql"]}`
"""


def render_contract_markdown(contract: Mapping[str, Any]) -> str:
    return f"""# N1 Condition Source 20260527 Activation Contract

Result: `{contract["result"]}`

- layer_role: `N1_ingestion`
- trade_date: `{TRADE_DATE}`
- source_batch_id: `{BATCH_ID}`
- source_versions: `{base.json.dumps(SOURCE_VERSIONS, ensure_ascii=False)}`
- execute runner implemented: `{contract.get("implementation_status", {}).get("execute_runner_implemented")}`
- final execute gate allowed: `{contract.get("implementation_status", {}).get("final_execute_gate_allowed")}`
- allowed tables: `{", ".join(ALLOWED_FUTURE_WRITE_TABLES)}`
- forbidden: daily bar fact, Parquet, outbox/inbox/checkpoint, N2-N6, worker, old system, real trading

Expected rows:

```json
{base.json.dumps(contract["expected_rows"], ensure_ascii=False, indent=2)}
```

Rollback SQL: `{DEFAULT_PATHS["rollback_sql"]}`
"""


sanitize_json_value = base.sanitize_json_value
assert_json_compatible = base.assert_json_compatible
jsonb_row = base.jsonb_row
