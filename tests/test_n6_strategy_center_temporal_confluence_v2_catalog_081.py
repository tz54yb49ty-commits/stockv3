from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import unittest

from tests.test_n6_strategy_worker_canonical_acl_079 import (
    _temporary_postgres,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql/081_n6_strategy_center_temporal_confluence_v2_catalog.sql"
ROLLBACK = (
    ROOT
    / "sql/081_n6_strategy_center_temporal_confluence_v2_catalog_rollback.sql"
)
EXPECTED_POLICY_HASHES = {
    "package_1": "0030c7218da533704a69405bc74682d22d318ee127837c42b6a40dc9a5185d58",
    "package_2": "12d6d2da725b1496a451cd6e02b9403b633ee33eee900b58870ed4b116fa52bb",
}


def _function_definition(sql: str, function_name: str) -> str:
    marker = f"CREATE OR REPLACE FUNCTION public.{function_name}"
    start = sql.index(marker)
    end = sql.index("$function$;", start) + len("$function$;")
    return sql[start:end]


class TemporalConfluenceV2Catalog081Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.migration = MIGRATION.read_text(encoding="utf-8")
        cls.rollback = ROLLBACK.read_text(encoding="utf-8")

    def test_schema_gate_is_additive_and_does_not_create_user_revision(self) -> None:
        self.assertIn("V1 remains active", self.migration)
        self.assertIn("V2 is registered as selectable", self.migration)
        self.assertIn("false, 'selectable'", self.migration)
        self.assertNotIn("$single_scope_revision$", self.migration)
        self.assertNotIn("ashare_v3.n6_sc_v2_", self.migration)
        self.assertNotIn("n6-sc-temporal-confluence-v2-20260723", self.migration)
        postflight = self.migration.split("DO $postflight$", 1)[1]
        self.assertIn("unexpectedly created a v2 user selection", postflight)
        self.assertRegex(
            postflight,
            r"(?s)package_version = 'v1'.*?package_status = 'active'",
        )
        self.assertNotRegex(
            self.migration,
            r"(?s)UPDATE public\.n6_strategy_package_catalog.*?"
            r"package_version = 'v1'",
        )

    def test_v2_catalog_json_and_hashes_match_runtime_authority(self) -> None:
        payloads = re.findall(
            r"\$json\$(\{.*?\})\$json\$::jsonb",
            self.migration,
            flags=re.DOTALL,
        )
        self.assertEqual(len(payloads), 2)
        rebuilt = {}
        for encoded in payloads:
            payload = json.loads(encoded)
            rebuilt[payload["package_key"]] = payload
        hashes = {
            key: sha256(
                json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            for key, value in rebuilt.items()
        }
        self.assertEqual(hashes, EXPECTED_POLICY_HASHES)
        for package_key, payload in rebuilt.items():
            self.assertEqual(payload["package_key"], package_key)
            self.assertEqual(payload["package_version"], "v2")
            rules = payload["rules"]
            self.assertEqual(
                rules["event_selection"],
                "first_confirmation_then_minimum_span",
            )
            self.assertEqual(
                rules["event_time_authority"],
                "n5_standard_event_time_only",
            )
            self.assertEqual(
                rules["invalid_or_midday_event_time_policy"],
                "fail_closed",
            )
            self.assertEqual(rules["freshness_statuses"], ["fresh", "stale"])
            self.assertEqual(
                rules["observation_reasons"],
                ["weak_span", "stale_after_confirmation"],
            )
            self.assertEqual(
                rules["observation_retention"], "same_trade_date_close"
            )
        for value in hashes.values():
            self.assertIn(value, self.migration)

    def test_match_projection_is_v1_compatible_and_v2_fail_closed(self) -> None:
        for required in (
            "ADD COLUMN strategy_version text NOT NULL DEFAULT 'v1'",
            "ADD COLUMN coherence_episode_key text",
            "ADD COLUMN direction text",
            "ADD COLUMN coherence_level text",
            "ADD COLUMN freshness_status text",
            "ADD COLUMN confluence_json jsonb",
            "ADD COLUMN package_evidence_json jsonb",
            "strategy_version = 'v1'\n    OR (",
            "direction IN ('buy', 'sell')",
            "coherence_level IN ('STRONG', 'MEDIUM')",
            "freshness_status = 'fresh'",
            "NOT signal_json ? 'strategy_center_temporal_confluence'",
            "confluence_json->'package_evidence' = package_evidence_json",
            "confluence_json->>'evaluator_policy_hash' = evaluator_policy_hash",
            "idx_081_n6_strategy_match_v1_grain",
            "idx_081_n6_strategy_match_v2_grain",
        ):
            self.assertIn(required, self.migration)

    def test_general_observation_surface_covers_weak_and_stale(self) -> None:
        table = self.migration.split(
            "CREATE TABLE public.n6_strategy_observation_projection (", 1
        )[1].split("CREATE INDEX idx_081_n6_strategy_observation_user_date", 1)[0]
        for required in (
            "strategy_observation_projection_id",
            "coherence_episode_key text NOT NULL",
            "observation_kind text NOT NULL",
            "qualification_status text NOT NULL DEFAULT 'observation_only'",
            "observation_kind = 'weak_span'",
            "observation_kind = 'stale_after_confirmation'",
            "coherence_level IN ('STRONG', 'MEDIUM', 'WEAK')",
            "freshness_status IN ('fresh', 'stale')",
            "NOT signal_json ? 'strategy_center_temporal_confluence'",
            "confluence_json->>'evaluator_policy_hash' = evaluator_policy_hash",
        ):
            self.assertIn(required, table)
        self.assertNotIn("n6_strategy_weak_observation_projection", self.migration)

    def test_shared_change_ledger_has_unambiguous_surface_identity(self) -> None:
        for required in (
            "ADD COLUMN surface_kind text NOT NULL DEFAULT 'qualified_match'",
            "ADD COLUMN strategy_observation_projection_id bigint",
            "surface_kind IN ('qualified_match', 'observation')",
            "surface_kind = 'qualified_match'",
            "surface_kind = 'observation'",
        ):
            self.assertIn(required, self.migration)
        changes = _function_definition(
            self.migration, "n6_btrack_strategy_center_changes"
        )
        self.assertIn("'surface_kind', row.surface_kind", changes)
        self.assertIn(
            "'strategy_observation_projection_id',", changes
        )
        self.assertIn("'watermark'", changes)
        self.assertIn("'has_more'", changes)

    def test_state_keeps_signal_canonical_and_returns_separate_confluence(self) -> None:
        state = _function_definition(
            self.migration, "n6_btrack_strategy_center_state"
        )
        for required in (
            "'matches'",
            "'observations'",
            "'surface_counts'",
            "'qualified_match_count'",
            "'weak_count'",
            "'stale_count'",
            "'signal', row.signal_json",
            "'confluence', row.confluence_json",
            "'package_evidence', row.package_evidence_json",
            "'coherence_episode_key', row.coherence_episode_key",
            "'evaluator_policy_hash', row.evaluator_policy_hash",
            "'watermarks'",
            "'qualified_match'",
            "'observation'",
            "'quality'",
            "'market_heat_rank'",
            "row.matched_at",
            "row.observed_at",
        ):
            self.assertIn(required, state)
        self.assertNotIn("jsonb_set(row.signal_json", state)
        self.assertNotIn("signal_json ||", state)

    def test_selection_targets_selectable_v2_but_new_principal_default_stays_v1(self) -> None:
        default_function = _function_definition(
            self.migration,
            "n6_strategy_default_selection_on_principal_insert",
        )
        selection = _function_definition(
            self.migration, "n6_btrack_strategy_selection_put"
        )
        self.assertIn("catalog.package_status = 'active'", default_function)
        self.assertNotIn("package_status = 'selectable'", default_function)
        self.assertIn("default_package.package_version", default_function)
        self.assertIn("target_package_version", selection)
        self.assertIn("target_package_status", selection)
        self.assertIn("item.package_version", selection)
        self.assertIn(
            "catalog.package_status IN ('selectable', 'active')", selection
        )
        self.assertIn("WHEN 'selectable' THEN 0", selection)
        self.assertIn(
            "catalog.package_status = target_package_status", selection
        )
        self.assertNotIn("package_version = 'v2'", selection)

    def test_acl_is_web_function_only_and_worker_projection_only(self) -> None:
        self.assertIn(
            "REVOKE ALL ON TABLE public.n6_strategy_observation_projection\n"
            "FROM PUBLIC, n6_btrack_web, n6_strategy_worker, "
            "n6_virtual_executor,",
            self.migration,
        )
        self.assertIn(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE\n"
            "  public.n6_strategy_observation_projection\n"
            "TO n6_strategy_worker;",
            self.migration,
        )
        self.assertIn(
            "GRANT EXECUTE ON FUNCTION\n"
            "  public.n6_btrack_strategy_center_state(text)",
            self.migration,
        )
        grant_section = self.migration.split("GRANT EXECUTE ON FUNCTION", 1)[1]
        self.assertIn("TO n6_btrack_web;", grant_section)
        for forbidden in (
            "GRANT SELECT ON TABLE public.common_action",
            "GRANT SELECT ON TABLE public.common_trigger",
            "GRANT INSERT ON TABLE public.n6_virtual_trade",
            "GRANT UPDATE ON TABLE public.n6_virtual_position",
            "GRANT DELETE ON TABLE public.n6_virtual_cash",
        ):
            self.assertNotIn(forbidden, self.migration)

    def test_rollback_is_logical_fail_closed_and_preserves_history(self) -> None:
        self.assertIn("blocked by live V2 user revision", self.rollback)
        self.assertIn("package_status = 'retired'", self.rollback)
        self.assertIn("package_version = 'v1'", self.rollback)
        for forbidden in (
            "DROP TABLE",
            "DROP FUNCTION",
            "ALTER TABLE",
            "DELETE FROM",
            "TRUNCATE",
        ):
            self.assertNotIn(forbidden, self.rollback.upper())
        for preserved in (
            "n6_strategy_observation_projection",
            "n6_strategy_match_projection",
            "n6_strategy_match_change",
        ):
            self.assertIn(preserved, self.rollback)


POSTGRES_FIXTURE_SQL = r"""
DROP VIEW IF EXISTS v_n6_stock_condition_display_basis;
DROP VIEW IF EXISTS v_n6_index_condition_display_basis;
DROP VIEW IF EXISTS v_n6_board_condition_display_basis;
DROP TABLE IF EXISTS stock_condition_display_basis;
DROP TABLE IF EXISTS index_condition_display_basis;
DROP TABLE IF EXISTS board_condition_display_basis;

CREATE TABLE user_account (
  user_id bigint PRIMARY KEY,
  status text NOT NULL
);
CREATE TABLE n6_principal (
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  owner_user_id bigint NOT NULL,
  principal_status text NOT NULL,
  PRIMARY KEY (principal_id, principal_type)
);
CREATE TABLE common_trade_calendar (
  trade_date text NOT NULL,
  is_open boolean NOT NULL
);
CREATE TABLE user_signal_projection (
  user_signal_projection_id bigint PRIMARY KEY
);
CREATE TABLE user_monitor_stock (
  principal_id bigint, principal_type text, user_id bigint,
  identity_key text, asset_kind text, status text,
  valid_source_trade_date text, valid_for_trade_date text,
  valid_source_run_id text, source_run_id text
);
CREATE TABLE user_realtime_monitor_scope (
  principal_id bigint, principal_type text, user_id bigint,
  identity_key text, asset_kind text, status text
);
CREATE TABLE n6_virtual_account (
  virtual_account_id bigint PRIMARY KEY,
  principal_id bigint, principal_type text,
  virtual_account_status text
);
CREATE TABLE n6_virtual_position (
  virtual_account_id bigint, principal_id bigint, principal_type text,
  identity_key text, asset_kind text, position_status text,
  quantity numeric
);
CREATE TABLE stock_condition_display_basis (
  identity_key text, source_trade_date text,
  for_trade_date text, run_id text
);
CREATE VIEW v_n6_stock_condition_display_basis AS
SELECT * FROM stock_condition_display_basis;

CREATE TABLE n6_strategy_package_catalog (
  package_key text NOT NULL,
  package_version text NOT NULL,
  display_name text NOT NULL,
  rule_kind text NOT NULL,
  allowed_board_types text[] NOT NULL,
  default_selected boolean NOT NULL DEFAULT false,
  package_status text NOT NULL DEFAULT 'active',
  rule_json jsonb NOT NULL,
  policy_hash text NOT NULL,
  effective_from_trade_date date NOT NULL,
  retired_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (package_key, package_version),
  CHECK (package_key IN ('package_1', 'package_2')),
  CHECK (package_version ~ '^v[1-9][0-9]*$'),
  CHECK (display_name <> ''),
  CHECK (rule_kind IN ('index_and_board_executed', 'board_executed')),
  CHECK (allowed_board_types = ARRAY[
    'tdx_industry', 'tdx_concept', 'tdx_region'
  ]::text[]),
  CHECK (package_status IN ('active', 'retired')),
  CHECK (jsonb_typeof(rule_json) = 'object'),
  CHECK (policy_hash ~ '^[0-9a-f]{64}$'),
  CHECK (
    (package_status = 'active' AND retired_at IS NULL)
    OR (package_status = 'retired' AND retired_at IS NOT NULL)
  ),
  CHECK (updated_at >= created_at)
);
CREATE UNIQUE INDEX idx_073_n6_strategy_package_active_key
ON n6_strategy_package_catalog(package_key)
WHERE package_status = 'active';
CREATE UNIQUE INDEX idx_073_n6_strategy_package_one_default
ON n6_strategy_package_catalog(default_selected)
WHERE package_status = 'active' AND default_selected = true;

CREATE TABLE n6_user_strategy_selection_revision (
  selection_revision_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  user_id bigint NOT NULL REFERENCES user_account(user_id),
  revision_no bigint NOT NULL,
  selection_status text NOT NULL,
  replay_status text NOT NULL,
  request_id text NOT NULL,
  effective_trade_date date NOT NULL,
  previous_revision_id bigint,
  selection_policy_hash text NOT NULL,
  created_by_user_id bigint NOT NULL REFERENCES user_account(user_id),
  selection_metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  activated_at timestamptz,
  superseded_at timestamptz,
  UNIQUE (principal_id, principal_type, user_id, revision_no),
  UNIQUE (principal_id, principal_type, user_id, request_id),
  UNIQUE (previous_revision_id),
  UNIQUE (selection_revision_id, principal_id, principal_type, user_id),
  CHECK (selection_status IN ('pending', 'active', 'superseded')),
  CHECK (
    (selection_status = 'pending'
     AND activated_at IS NULL
     AND superseded_at IS NULL)
    OR (selection_status = 'active'
        AND activated_at IS NOT NULL
        AND superseded_at IS NULL)
    OR (selection_status = 'superseded'
        AND activated_at IS NOT NULL
        AND superseded_at IS NOT NULL
        AND superseded_at >= activated_at)
  )
);
CREATE TABLE n6_user_strategy_selection_item (
  selection_revision_id bigint NOT NULL REFERENCES
    n6_user_strategy_selection_revision(selection_revision_id),
  package_key text NOT NULL,
  package_version text NOT NULL,
  selected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (selection_revision_id, package_key),
  FOREIGN KEY (package_key, package_version) REFERENCES
    n6_strategy_package_catalog(package_key, package_version)
);

CREATE TABLE n6_strategy_match_projection (
  strategy_match_projection_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  selection_revision_id bigint NOT NULL,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  user_id bigint NOT NULL REFERENCES user_account(user_id),
  trade_date date NOT NULL,
  stock_identity_key text NOT NULL,
  action_episode_key text NOT NULL,
  action_state text NOT NULL,
  source_signal_projection_id bigint NOT NULL REFERENCES
    user_signal_projection(user_signal_projection_id),
  source_event_ids text[] NOT NULL,
  matched_packages text[] NOT NULL,
  scope_sources text[] NOT NULL,
  indices_json jsonb NOT NULL,
  matched_boards_json jsonb NOT NULL,
  signal_json jsonb NOT NULL,
  state_timeline_json jsonb NOT NULL,
  mapping_quality text NOT NULL,
  membership_source_trade_date date NOT NULL,
  evaluator_policy_hash text NOT NULL,
  projection_hash text NOT NULL,
  matched_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY (
    selection_revision_id, principal_id, principal_type, user_id
  ) REFERENCES n6_user_strategy_selection_revision(
    selection_revision_id, principal_id, principal_type, user_id
  ),
  UNIQUE (
    principal_id, principal_type, user_id, trade_date,
    stock_identity_key, action_episode_key, selection_revision_id
  ),
  UNIQUE (
    strategy_match_projection_id, principal_id, principal_type, user_id
  )
);
CREATE TABLE n6_strategy_match_change (
  strategy_match_change_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  strategy_match_projection_id bigint,
  selection_revision_id bigint NOT NULL,
  principal_id bigint NOT NULL,
  principal_type text NOT NULL,
  user_id bigint NOT NULL REFERENCES user_account(user_id),
  trade_date date NOT NULL,
  change_type text NOT NULL,
  dedup_key text NOT NULL,
  source_event_id text,
  payload_json jsonb NOT NULL,
  payload_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY (
    selection_revision_id, principal_id, principal_type, user_id
  ) REFERENCES n6_user_strategy_selection_revision(
    selection_revision_id, principal_id, principal_type, user_id
  ),
  UNIQUE (principal_id, principal_type, user_id, dedup_key),
  CHECK (principal_type IN ('admin', 'human_user')),
  CHECK (change_type IN ('upsert', 'remove', 'reset')),
  CHECK (dedup_key <> ''),
  CHECK (source_event_id IS NULL OR source_event_id <> ''),
  CHECK (jsonb_typeof(payload_json) = 'object'),
  CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
  CHECK (
    (change_type IN ('upsert', 'remove')
     AND strategy_match_projection_id IS NOT NULL)
    OR (change_type = 'reset'
        AND strategy_match_projection_id IS NULL)
  )
);

CREATE FUNCTION n6_btrack_resolve_authority(text)
RETURNS jsonb LANGUAGE sql STABLE AS $$ SELECT NULL::jsonb $$;
CREATE FUNCTION n6_strategy_default_selection_on_principal_insert()
RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$;
CREATE FUNCTION n6_btrack_strategy_center_state(text)
RETURNS jsonb LANGUAGE sql STABLE AS $$ SELECT NULL::jsonb $$;
CREATE FUNCTION n6_btrack_strategy_center_changes(text,bigint,integer)
RETURNS jsonb LANGUAGE sql STABLE AS $$ SELECT NULL::jsonb $$;
CREATE FUNCTION n6_btrack_strategy_selection_put(text,text[],bigint,text)
RETURNS jsonb LANGUAGE sql AS $$ SELECT NULL::jsonb $$;

INSERT INTO common_trade_calendar VALUES
  ('20260723', true),
  (
    pg_catalog.to_char(
      pg_catalog.clock_timestamp() AT TIME ZONE 'Asia/Shanghai',
      'YYYYMMDD'
    ),
    true
  );
INSERT INTO n6_strategy_package_catalog (
  package_key, package_version, display_name, rule_kind,
  allowed_board_types, default_selected, package_status, rule_json,
  policy_hash, effective_from_trade_date
) VALUES
  (
    'package_1', 'v1', 'P1', 'index_and_board_executed',
    ARRAY['tdx_industry','tdx_concept','tdx_region'], true, 'active',
    '{}'::jsonb, repeat('a', 64), DATE '2026-07-23'
  ),
  (
    'package_2', 'v1', 'P2', 'board_executed',
    ARRAY['tdx_industry','tdx_concept','tdx_region'], false, 'active',
    '{}'::jsonb, repeat('b', 64), DATE '2026-07-23'
  );
"""


class TemporalConfluenceV2Catalog081PostgresTest(unittest.TestCase):
    def test_forward_and_logical_rollback(self) -> None:
        with _temporary_postgres() as postgres:
            for role in (
                "n6_btrack_web",
                "n6_virtual_executor",
                "n6_quote_writer",
                "n6_ai_agent",
            ):
                postgres.sql(
                    f"CREATE ROLE {role} LOGIN NOINHERIT;",
                    database="postgres",
                    user="cluster_admin",
                )
            postgres.sql(POSTGRES_FIXTURE_SQL)
            forward = postgres.file(MIGRATION, check=False)
            self.assertEqual(forward.returncode, 0, forward.stderr)
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT string_agg(
                      package_version || ':' || package_status,
                      ',' ORDER BY package_version, package_key
                    ) FROM n6_strategy_package_catalog;
                    """
                ),
                "v1:active,v1:active,v2:selectable,v2:selectable",
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT count(*) FROM n6_user_strategy_selection_item "
                    "WHERE package_version = 'v2';"
                ),
                "0",
            )
            postgres.sql(
                """
                INSERT INTO user_account VALUES (1, 'active');
                INSERT INTO user_signal_projection VALUES (10);
                INSERT INTO n6_user_strategy_selection_revision (
                  principal_id, principal_type, user_id, revision_no,
                  selection_status, replay_status, request_id,
                  effective_trade_date, selection_policy_hash,
                  created_by_user_id, activated_at
                ) VALUES (
                  1, 'human_user', 1, 1, 'active', 'passed',
                  'grandfathered-v1', DATE '2026-07-23', repeat('a', 64),
                  1, clock_timestamp()
                );
                INSERT INTO n6_user_strategy_selection_item
                  (selection_revision_id, package_key, package_version)
                VALUES (1, 'package_1', 'v1');
                INSERT INTO n6_strategy_match_projection (
                  selection_revision_id, principal_id, principal_type,
                  user_id, trade_date, stock_identity_key,
                  action_episode_key, action_state,
                  source_signal_projection_id, source_event_ids,
                  matched_packages, scope_sources, indices_json,
                  matched_boards_json, signal_json, state_timeline_json,
                  mapping_quality, membership_source_trade_date,
                  evaluator_policy_hash, projection_hash, matched_at
                ) VALUES (
                  1, 1, 'human_user', 1, DATE '2026-07-23',
                  'stock:SH:600000', 'episode-v1', 'eligible', 10,
                  ARRAY['event-v1'], ARRAY['package_1'], ARRAY['monitor'],
                  '[]', '[]', '{}', '[]', 'passed', DATE '2026-07-23',
                  repeat('a', 64), repeat('b', 64), clock_timestamp()
                );
                INSERT INTO n6_strategy_match_change (
                  strategy_match_projection_id, selection_revision_id,
                  principal_id, principal_type, user_id, trade_date,
                  change_type, dedup_key, payload_json, payload_hash
                ) VALUES (
                  1, 1, 1, 'human_user', 1, DATE '2026-07-23',
                  'upsert', 'v1-change', '{}', repeat('c', 64)
                );
                """
            )
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT concat_ws('|', strategy_version,
                      coherence_episode_key IS NULL,
                      confluence_json IS NULL)
                    FROM n6_strategy_match_projection;
                    """
                ),
                "v1|t|t",
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT surface_kind FROM n6_strategy_match_change;"
                ),
                "qualified_match",
            )
            postgres.sql(
                """
                INSERT INTO n6_user_strategy_selection_revision (
                  principal_id, principal_type, user_id, revision_no,
                  selection_status, replay_status, request_id,
                  effective_trade_date, previous_revision_id,
                  selection_policy_hash, created_by_user_id,
                  activated_at, superseded_at
                ) VALUES (
                  1, 'human_user', 1, 2, 'superseded', 'passed',
                  'historical-v2', DATE '2026-07-23', 1,
                  repeat('d', 64), 1,
                  clock_timestamp() - interval '1 second', clock_timestamp()
                );
                INSERT INTO n6_user_strategy_selection_item
                  (selection_revision_id, package_key, package_version)
                VALUES (2, 'package_1', 'v2');
                INSERT INTO n6_strategy_match_projection (
                  selection_revision_id, principal_id, principal_type,
                  user_id, trade_date, stock_identity_key,
                  action_episode_key, action_state,
                  source_signal_projection_id, source_event_ids,
                  matched_packages, scope_sources, indices_json,
                  matched_boards_json, signal_json, state_timeline_json,
                  mapping_quality, membership_source_trade_date,
                  evaluator_policy_hash, projection_hash, matched_at,
                  strategy_version, coherence_episode_key, direction,
                  coherence_level, freshness_status, confluence_json,
                  package_evidence_json
                ) VALUES (
                  2, 1, 'human_user', 1, DATE '2026-07-23',
                  'stock:SH:600000', 'episode-v2', 'eligible', 10,
                  ARRAY['stock-event','board-event'], ARRAY['package_2'],
                  ARRAY['monitor'], '[]', '[]', '{}', '[]', 'passed',
                  DATE '2026-07-23', repeat('e', 64), repeat('f', 64),
                  clock_timestamp(), 'v2', 'coherence-strong', 'buy',
                  'STRONG', 'fresh',
                  '{"direction":"buy","coherence_level":"STRONG",'
                    '"freshness_status":"fresh","package_evidence":[],'
                    '"evaluator_policy_hash":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
                    'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"}',
                  '[]'
                );
                INSERT INTO n6_strategy_observation_projection (
                  selection_revision_id, principal_id, principal_type,
                  user_id, trade_date, stock_identity_key,
                  action_episode_key, coherence_episode_key, action_state,
                  source_signal_projection_id, source_event_ids,
                  observed_packages, scope_sources, indices_json,
                  observed_boards_json, signal_json, state_timeline_json,
                  mapping_quality, membership_source_trade_date,
                  direction, coherence_level, freshness_status,
                  confluence_json, package_evidence_json,
                  evaluator_policy_hash, observation_hash,
                  observation_kind, observed_at
                ) VALUES (
                  2, 1, 'human_user', 1, DATE '2026-07-23',
                  'stock:SH:600001', 'episode-weak', 'coherence-weak',
                  'eligible', 10, ARRAY['stock-weak','board-weak'],
                  ARRAY['package_2'], ARRAY['monitor'], '[]', '[]', '{}',
                  '[]', 'passed', DATE '2026-07-23', 'buy', 'WEAK',
                  'fresh',
                  '{"direction":"buy","coherence_level":"WEAK",'
                    '"freshness_status":"fresh","package_evidence":[],'
                    '"evaluator_policy_hash":"11111111111111111111111111111111'
                    '11111111111111111111111111111111"}',
                  '[]', repeat('1', 64), repeat('2', 64),
                  'weak_span', clock_timestamp()
                );
                INSERT INTO n6_strategy_match_change (
                  strategy_observation_projection_id,
                  selection_revision_id, principal_id, principal_type,
                  user_id, trade_date, change_type, surface_kind,
                  dedup_key, payload_json, payload_hash
                ) VALUES (
                  1, 2, 1, 'human_user', 1, DATE '2026-07-23',
                  'upsert', 'observation', 'v2-observation-change',
                  '{}', repeat('3', 64)
                );
                """
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT count(*) FROM n6_strategy_match_projection "
                    "WHERE strategy_version='v2' "
                    "AND confluence_json IS NOT NULL;"
                ),
                "1",
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT observation_kind || '|' || freshness_status "
                    "FROM n6_strategy_observation_projection;"
                ),
                "weak_span|fresh",
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT to_regclass("
                    "'public.n6_strategy_observation_projection') IS NOT NULL;"
                ),
                "t",
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT has_table_privilege("
                    "'n6_strategy_worker', "
                    "'n6_strategy_observation_projection', "
                    "'SELECT,INSERT,UPDATE,DELETE');"
                ),
                "t",
            )
            postgres.file(ROLLBACK)
            self.assertEqual(
                postgres.scalar(
                    """
                    SELECT string_agg(
                      package_version || ':' || package_status,
                      ',' ORDER BY package_version, package_key
                    ) FROM n6_strategy_package_catalog;
                    """
                ),
                "v1:active,v1:active,v2:retired,v2:retired",
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT to_regclass("
                    "'public.n6_strategy_observation_projection') IS NOT NULL;"
                ),
                "t",
            )

    def test_rollback_rejects_live_v2_revision_without_partial_retirement(self) -> None:
        with _temporary_postgres() as postgres:
            for role in (
                "n6_btrack_web",
                "n6_virtual_executor",
                "n6_quote_writer",
                "n6_ai_agent",
            ):
                postgres.sql(
                    f"CREATE ROLE {role} LOGIN NOINHERIT;",
                    database="postgres",
                    user="cluster_admin",
                )
            postgres.sql(POSTGRES_FIXTURE_SQL)
            forward = postgres.file(MIGRATION, check=False)
            self.assertEqual(forward.returncode, 0, forward.stderr)
            postgres.sql(
                """
                INSERT INTO user_account VALUES (1, 'active');
                INSERT INTO n6_user_strategy_selection_revision (
                  principal_id, principal_type, user_id, revision_no,
                  selection_status, replay_status, request_id,
                  effective_trade_date, selection_policy_hash,
                  created_by_user_id, activated_at
                ) VALUES (
                  1, 'human_user', 1, 1, 'active', 'passed',
                  'v2-live-revision', DATE '2026-07-23', repeat('a', 64),
                  1, clock_timestamp()
                );
                INSERT INTO n6_user_strategy_selection_item
                  (selection_revision_id, package_key, package_version)
                SELECT selection_revision_id, 'package_1', 'v2'
                FROM n6_user_strategy_selection_revision;
                """
            )
            result = postgres.file(ROLLBACK, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "081 rollback blocked by live V2 user revision",
                result.stderr,
            )
            self.assertEqual(
                postgres.scalar(
                    "SELECT count(*) FROM n6_strategy_package_catalog "
                    "WHERE package_version='v2' "
                    "AND package_status='selectable';"
                ),
                "2",
            )


if __name__ == "__main__":
    unittest.main()
